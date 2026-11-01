# F7: safe hot reload (#422, P1)

## The defect

A hot reload took the running scene down before it read the replacement.

- **Immediate route.** `reload_scene` (`engine/scene_runtime/transitions.py`: Ctrl+R, the console, the editor)
  cleared the layers, the scene's event subscriptions and the queued events first.
- **Queued route.** `handle_pending_scene_load` (`engine/scene_lifecycle_controller.py`: `request_scene_reload`, the
  asset browser) cleared the queued events and, when asked, the texture and sound caches first. It then raised out of
  the update loop.

A missing, malformed or invalid scene therefore destroyed the scene that was running.

**Reproduced at the base `a7514ed`** in a real hidden `GameWindow`:
- **The running scene:** two objects, one tracked scene subscription, one queued event and a game-state value.
- **The break:** the file was cut short (invalid JSON).
- **The reload:** immediate, or queued with the asset caches cleared.

| Route | Result | After |
| --- | --- | --- |
| immediate | `False`, error `JSONDecodeError: Expecting value…` | **objects `[]`**, subscriptions 0, queued events `[]` |
| queued | **raised** `JSONDecodeError` out of the update loop; no error shown | subscriptions 0, queued events `[]`, asset caches cleared |

**Found on the way, also at the base:** a successful immediate reload came back with no objects at all. It cleared the
layers before `load_scene` recorded what the player had removed from the room, so every object looked collected and
none was spawned again. The queued route didn't clear early and wasn't affected.

## The fix

**One check, through the existing loader.** `engine/scene_runtime/reload_check.py` loads the scene with
`SceneLoader.load_scene(path, strict=True)`. That is the same code a reload uses: an open Studio document before the
file, migration, the scene schema and `validate_scene`. `strict` raises `SceneValidationFailed` where a plain load
returns the empty fallback, so there is no second parser and no empty scene. Both routes run the check before
anything is cleared, and a refusal changes nothing.

**Built from what was checked.** The checked scene is handed to `load_scene` (`reload_check.hand_over` and `take`),
so the scene is read once. A file saved again between the check and the build can't slip past it.

**Immediate route no longer clears early.** `load_scene` clears the layers and subscriptions itself, after noting
what was removed from the room. With the early clearing gone, nothing is torn down before the check, and a successful
reload keeps every object.

**One result.** Every attempt leaves `SceneController.last_reload_result`:

| Field | Values |
| --- | --- |
| `ok` | `true` or `false` |
| `reason` | `scene_missing`, `scene_unreadable`, `invalid_json`, `schema_invalid`, `scene_invalid`, `no_scene` or `construction_failed` |
| `stage` | `preflight` or `construction` |
| `route` | `immediate` or `queued` |
| `scene_path`, `message` | the scene, and the explanation people see |
| `previous_scene_preserved` | whether the scene running before the attempt is still running |
| `can_retry` | whether another reload can be attempted |
| `errors`, `errors_total` | up to 10 validation errors, and how many there were |

**Where people and AI agents see it:**
- **People:** the existing hot-reload error (`set_hot_reload_error`: the debug overlay, the toast path in
  `reload_scene_from_disk`) now shows the message, for example: "Scene not reloaded: yard.json isn't valid JSON
  (line 1, column 31: Expecting value). The scene that was running is still running, unchanged; fix it and reload
  again."
- **AI agents:** the existing live read returns it as `last_reload` (`null` before a reload). There is no new
  protocol and no new permission; proposals, revisions and the person's approval are unchanged. Two hosts serve it:
  - **Mesh Studio** (the authoring interface): `StudioAIHost.read_live_scene`, beside `last_save`. Agents read it
    with `mesh author read` or MCP `read_project` while Studio has the project open.
  - **The legacy editor** (the in-game editor overlay): `EditorModeController.read_live_scene`, through the same live
    bridge when that editor hosts the session.

**Queued route on refusal:** the request is consumed, nothing is raised, and the asset caches are not cleared.

**Ordinary scene changes are unchanged.** A queued load of another scene is not a reload. It loads as before, with
the loader's own fallback, and records no reload result.

## What a reload can still lose: failures while the scene is built

| Kind of failure | What happens | Covered |
| --- | --- | --- |
| A file that can't be read, isn't JSON, fails the schema, or fails validation (including the cases the loader would replace with an empty scene) | refused at `preflight`; nothing changes | yes |
| An object whose picture is missing, or whose behaviour fails to start | the object is skipped or given a placeholder (`_create_sprite`, unless `strict_mode`); the reload succeeds | already contained |
| A missing or broken map file (`tilemap.path`) | the map loader warns and skips the map; the reload succeeds without it | existing loader behaviour, not a reload failure |
| A scene-level setup step that raises (lighting, HD-2D, particles, music; probed by injecting a lighting failure) | stage `construction`, reason `construction_failed`, `previous_scene_preserved: false`. The subscriptions and part of the scene's settings were already replaced. The immediate route returns false; the queued route records the result, then raises as it did before. Reloading again works once the cause is gone. | reported, not rolled back |

A rollback of construction failures was not attempted. Rebuilding the previous scene from its document would repeat
the same construction, which can fail the same way, and it would lose the running scene's live state (objects moved,
behaviours' state). It would claim more than it can deliver. Construction failures are reported as such instead of as
a preserved scene.

## Also fixed: closing a closed window

pyglet closes a window again when it is garbage-collected, at any moment. `GameWindow.close()` then handed arcade's
active window to whatever `arcade.get_window()` returned. When that collection happened inside a test that patches
`get_window` (`tests/conftest.py` `mock_arcade_window`), the mock became the active window. Every later test that
built a sprite list then failed with "buffer parameter must be an arcade.gl.Buffer". 12 `slow` tests failed this way
once F7's real-window tests ran before them.

A closed window's `close()` now returns at once. The regression test is
`tests/test_game_window_close_keeps_active.py::test_closing_a_closed_window_again_changes_nothing`, which fails
without the guard.

## Evidence

- **Tests:** `tests/test_hot_reload_preflight.py` (integration, 23 tests, real hidden `GameWindow`s and real scene
  files).
  - **Refusals:** six ways a scene can't be loaded × both routes: missing, invalid JSON, schema, empty fallback, not
    UTF-8, a folder. Each checks that everything is as it was (objects and layers by identity, scene data, scene
    subscriptions, event bus, queued events, game state, camera, lighting), that the asset caches were not cleared,
    and the result and the error shown.
  - **After a refusal:** the corrected scene reloads normally, with no stale objects, one of every subscription and
    behaviour, the player and camera restored, and the error cleared.
  - **Repeated reloads:** three in a row keep every object, and each reads the scene once.
  - **Unsaved Studio document:** checked instead of the file; an invalid one is refused, a valid one reloads while
    the file is broken.
  - **Construction failure:** reported as such, then reloaded once fixed.
  - **AI read:** the legacy editor's live read returns the same result.
  - **Mesh Studio read:** the real live bridge is called the way `mesh author read` and MCP `read_project` call it.
    `last_reload` is `null`, then the refusal, identical to `last_reload_result`. Revision, proposal and "needs the
    person" behaviour are unchanged. Without the field, the test fails.
  - **Ordinary scene change:** not treated as a reload.
  - **Bounded errors:** at most 10 validation errors are kept.
- **Mutation check:** each guard was removed in turn:

  | Guard removed | Tests that fail (of 22; before the Studio read test) |
  | --- | --- |
  | the immediate route's check | 8 |
  | the queued route's check | 7 |
  | strict (the empty fallback allowed) | 3 |
  | the base order (layers cleared before the load) | 5 |
  | the hand-over | 2 |
  | `GameWindow.close` guard | 1 of 2 in its own file |
