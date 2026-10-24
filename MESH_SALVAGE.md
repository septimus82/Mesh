# Mesh — Salvage Audit

Baseline: `main` at `52d43a4`, archived as tag **`archive/pre-redesign-2026-10`** (recover anything with `git checkout -b restore archive/pre-redesign-2026-10`). Full suite at baseline: **9 failed, 9,261 passed, 10 skipped** (known groups: headless widget-overlay rendering ×5, battle-sprite headless probe, RMMZ fixtures ×2, editor drag-start).

Sources: five read-only code audits (runtime; behaviours and content; editor; Creator Mode, operation layers and CLI; monster code and legacy content), the stranger test (`docs/reviews/stranger_test_2026-10.md`), and the redesign's own real-window acceptance runs. "Observed" means seen in code or in the running app; "inferred" means judgement.

## Size, for scale (observed)

- `engine/`: 951 Python files, ~215k lines.
- Editor: 248 files and ~52k lines in `engine/editor/` (37 of them 7-line compatibility shims), 63 controller classes, about 195 methods attached to `EditorModeController` at import time, 141 actions.
- Creator Mode: 34 files, 6,588 lines.
- CLI: 128 top-level commands and 79 subcommands (~26k lines).
- Tests: ~1,700 files, ~9,270 tests.

## Decisions

| Subsystem | Decision | Evidence | Consequence |
|---|---|---|---|
| Behaviour registry + ParamDef (`engine/behaviours/registry.py`) | **KEEP** (fixed) | `list_behaviours()` yields name, description and typed fields with defaults; 57 of 62 behaviours fully declared. Bug: explicit `config_fields` replaced declared params (SceneTransition lost `trigger_on_touch`). | Fixed in `dcee165`. It now drives the Studio's "Add behaviour" picker and field forms. |
| Generic behaviours (~35: PlayerController, Dialogue, SceneTransition, Health, Patrol, Interactable…) | **KEEP** | Used by every template; the interaction layer (`engine/interaction.py`) is generic. | — |
| Overlapping behaviour pairs (SceneExit/SceneTransition, Patrol/PatrolPath, Collectible/PickupCollectible, TriggerZone/TriggerVolume, …) | **ARCHIVE later** | Inferred overlap from descriptions; not yet traced by callers. | Needs per-pair caller checks before removal. |
| Scene loading, schema, migrations (`scene_loader.py`, `schemas/`) | **KEEP** (fixed) | 20 production importers. Bugs: validation ran with an empty behaviour registry (every mesh_cli validator failed); save slots couldn't load as scenes. | Fixed (`dcee165`, save-slot load in this branch). Gained an open-documents map for unsaved edits. |
| Scene runtime (`scene_controller*`, `scene_runtime/`) | **REFACTOR later** | Chains of `sys.modules` aliasing shims; the core imports editor and encounter code. The draw plan ignored `sprite.visible`. | Visibility fixed here. Shim removal deferred: wide import surface. |
| Camera, physics, assets, paths, world controller | **KEEP** | Small and self-contained, or already the right concept. | — |
| `GameWindow` (`engine/game.py`, ~160 attributes) | **REFACTOR later** | God-object; editor, monster, lighting and particles all wired in. | The Studio sits beside it rather than inside. Splitting it is a separate, large slice. |
| Input routing (`input_dispatch.py` + capture router + config bindings) | **REPLACE later** (fixed for play) | Three paths compete for the same keys; Esc opened Settings first, which made the pause menu dead code; F9 was claimed twice; the router ignored return values. | The Studio bypasses all of this while editing. Play fixes landed: Esc pauses, F5/F9 are quick save/load. A single action map is still needed. |
| Save systems (`savegame.py`, `save_manager.py`, `save_runtime/`) | **REFACTOR** (partly done) | Three formats. Slot loads crashed on scene-schema validation, so the pause menu's Load Game never worked, and a failed load mid-game sent the player to the start scene. | `SaveManager` slots are now the single user-facing system: F5/F9 use its `quicksave` slot, which the pause menu lists. `SaveGameV1` (`save_1.json`) and quick snapshots remain for other callers; remove after migrating them. |
| Prefabs (`editor_palette.py` vs `prefabs.py`) | **REFACTOR later** | Two loaders with different validation. | The Studio reads `assets/prefabs.json` directly; unify later. |
| Project templates (`blank`, `starter` / `lighting_playground`, `demo_slice`) | **KEEP** / **REMOVE** | The last two write an invalid format (`layers` as a dict) and fail validation today. | Removal pending (tests reference them). |
| Project scaffold | **REFACTOR** | Every new project receives monster data and sprites. | Starter files (player sheet, door) separated from the monster pack in this branch; decoupling the monster pack is the next step. |
| Legacy editor (`engine/editor/`, `editor_controller.py`, `editor_runtime/`) | **REPLACE** (in progress) | Keyboard-only panels, 14 hand-rolled text buffers, 5 input layers, a 17-step click chain, two undo systems, broken undo branches, playtest that contaminates the edited scene. | Replaced by Mesh Studio for projects with a world. Still used for the engine repo itself, and available with `MESH_LEGACY_EDITOR=1`. Removal once the Studio covers tiles and lights. |
| Creator Mode (`engine/editor/creator_mode/`) | **REPLACE** / **ARCHIVE** | Proposal-staging shell; near-duplicate modules per verb; top bar and tool list are inert labels. | Superseded by the Studio's direct editing. Archive with the legacy editor. Its validation ideas live on in `engine/project_ops.py`. |
| Operation layers (`ai_ops.py`, live ops, plan executor, CLI scene ops) | **REFACTOR** (started) | Four mutation vocabularies; `ai_ops` writes files without validation; `OP_CATALOG` is a hand-kept copy. | New canonical layer `engine/project_ops.py` (pure, validated). The Studio uses it now; MCP/AI/CLI must be ported to it, with proposals as an optional wrapper. |
| MCP server / live bridge | **KEEP** as adapters | 23 tools + 1 resource; stage/accept/reject over loopback. | Point them at `project_ops` next. |
| CLI | **REFACTOR / ARCHIVE** | ~35 user, ~50 dev/CI, ~35 legacy/demo commands; ~22 dead candidates. | Not touched in this pass. |
| Plugin system (`plugin_system.py`) | **KEEP** (corrected in Milestone 7) | First audit said `mods/` loads only from the engine repo. The Milestone 7 lab showed otherwise: `find_repo_root` stops at the folder holding `config.json`, so a game run from a project loads `<project>/mods/`. A lab plugin added a behaviour that ran in play. | Projects *can* add behaviours. Still to do: `mesh new-behaviour` writes into the engine, not the project. |
| Monster game (`engine/monster/`, 20 modules, ~5.7k lines) | **EXTRACT** to an optional plugin | One eager import (`game.py`) plus ~12 call sites; the core depends on monster, not the reverse; `PluginManager` can host it. | Not done yet. Steps listed in the audit (event for walk distance, plugin-registered debug keys and zone behaviours). |
| Demo content (episodes, golden slices, act worlds, campaign/replay tooling, ~62 demo-only tests) | **ARCHIVE** | Hardcoded preset branches in the engine; ~6–9% of tests protect demo content. | Not done yet; large but mechanical. |
| Root session leftovers, committed pytest artefacts (`.pytest-gate-deps/`, 224 files) | **REMOVE** | Nothing references them (grep). | See removal record. |
| Dead modules (`tweens.py`, `entity_view.py`, `sprite_animator.py`, `tilemap_resize.py`, two facades) | **REMOVE** | No non-test importers. | Pending; tests and ratchet baselines need edits. |

## UI framework decision

Arcade (immediate-mode drawing) is kept for the map, where it works well. The panels use **`arcade.gui`**, which was already installed and previously unused.
- **Demonstrated benefit:** real text fields (caret, selection, OS text input, so Shift and non-US layouts work), real buttons and layouts, with mouse-first interaction.
- **Cost:** none in dependencies.
- **Known gaps:** no clipboard, no scroll container. The Studio works around them: an accordion inspector and a search-filtered behaviour picker.
- **Bug worked around:** clicking a field put the caret at position 0.

Switching to another toolkit (Qt, Dear ImGui) was not justified: it brings a new dependency and a rewrite of every panel, and no blocker has appeared that `arcade.gui` can't handle.

## Removal record

| Commit | Removed / changed | Why | Restore |
|---|---|---|---|
| (this branch) | Esc no longer opens Settings directly in play; it opens the pause menu (Settings is inside). Plain F9 no longer toggles a silent debug pause or sprite batching; it is quick load. Sprite batching moved behind debug mode. | The old bindings made save/load unreachable (stranger test B4). | `git show archive/pre-redesign-2026-10:engine/game_runtime/input_dispatch.py` |
| (this branch) | Tests asserting the old Esc→Settings and F9→pause behaviour rewritten to the new contract (`test_game_loop.py`, `test_game_input_capture_regression.py`, `test_authoring_copy_coords_hotkey.py`). Two load-failure tests narrowed from "no toast" to "never a *Loaded* toast". | Behaviour changed deliberately; assertions kept to the same strength. | Archive tag. |
| `154691d` | Root leftovers: `last_implementation.md`, `task_summary*.md` (3), `rathena_packet_table_20190605.txt`, `Act1/Act2_ContentPlan.md`. Untracked and ignored `.pytest-gate-deps/` (224 test-run files). | No references anywhere (git grep). | `git checkout archive/pre-redesign-2026-10 -- <path>` |
| `f871855` | New `blank`/`starter` projects no longer receive the monster game's data, sprites and sounds. New opt-in `monster` template keeps the test game reproducible; the monster boot tests use it. | The monster game is a test project, not the product. | Use `--template monster`; or the archive tag. |
| (Milestone 4) | The pyglet 1.5 `_event_queue` patch in generated `main.py`; the generated file now sets the DPI mode and loads the engine inside `main()` (lint-clean, no suppressions). | The engine runs on pyglet 2.1, so the patch did nothing. Its imports-after-code tripped E402 in every new game. | `git show archive/pre-redesign-2026-10:engine/project_scaffold.py` |
| (Milestone 4) | The recent-projects list moved from `<engine>/projects.json` to the user's profile (`%APPDATA%/Mesh/projects.json`). The tracked `projects.json` is kept but no longer read or written. | Opening a project changed the engine folder; the list belongs to a person, not a checkout. | `MESH_PROJECTS_PATH=<engine>/projects.json` restores the old location. |
| (Milestone 4) | `lighting_playground` and `demo_slice` are no longer offered to beginners (the launcher shows `blank` and `adventure`). Both still exist for `mesh new --template` and their tests. | Older scene layout (`layers.entities`, `type: npc`); Mesh Studio can't edit it. | Unchanged; set `launcher=True` in `engine/project_templates.py`. |
| `c14f722` | `engine/entity_view.py` (never wired in) and `engine/sprite_animator.py` (duplicate of `animation.py`), with their dedicated tests and baseline entries. | No production importers (git grep, string references included). | Archive tag. |

**Checked and kept, contrary to the audit's first pass:** `scene_controller_impl.py` is imported by `scene_controller.py`. `tweens.py` and `tilemap_resize.py` are unused but generic and tested, and likely wanted by tile painting. `editor_controller_core.py` goes with the legacy editor, not piecemeal.

Further removals are listed under "Next" in `MESH_REBUILD.md`.

## Duplicates found in Milestone 4, and what was done

| System | Status | Depends on it |
|---|---|---|
| **Project browser in the game's main menu** (`engine/ui_overlays/main_menu_overlay.py`): recent list, create from template. | **Kept** for the legacy flow. Not duplicated: the new launcher and this browser share one registry (`engine/projects.py`), one scaffold (`create_project`) and one template list (`list_templates`). Retire it with the legacy editor. | Legacy editor workspace (`engine/editor/editor_workspace_controller.py`), `tests/test_project_browser_*`. |
| **`WorkspacePaths.projects_path`** (`engine/editor/editor_workspace_model.py`) | Still reports `<repo>/projects.json`, which is informational only (nothing reads the list through it). | `tests/test_editor_workspace_model_contract.py`, `tests/test_editor_workspace_policy_contract.py`. |
| **Studio look and widgets** (colours, button styles, the text field and its clipboard keys, OS file pickers) | **Consolidated** into `engine/studio_ui.py`, used by both Mesh Studio and the launcher. | — |
| **`mesh.bat`** (CLI shim) vs **`Mesh Engine.bat`** (double-click launcher) | Both kept: different jobs. `mesh.bat` runs `mesh_cli` commands; `Mesh Engine.bat` opens the launcher. | — |


## Milestone 7: capability preservation

Full reports:
- [`docs/reviews/milestone7_capability_inventory.md`](docs/reviews/milestone7_capability_inventory.md)
- [`docs/reviews/milestone7_capability_lab.md`](docs/reviews/milestone7_capability_lab.md)
- [`docs/reviews/milestone7_consolidation_plan.md`](docs/reviews/milestone7_consolidation_plan.md)

**Preservation decisions.**
- Nothing was deleted.
- Kept explicitly, whether or not Studio shows them yet:
  - lighting and shadows (static, dynamic, flicker, occluders, cookies, shafts; soft shadows are kept although unreachable);
  - HD-2D (y-sort, `render_layer`/`depth_z`, shadows, depth tint, outlines);
  - parallax (`background_layers`; `background_planes` until converted);
  - camera (follow, zoom, areas, shake);
  - navigation and AI behaviours;
  - all three timeline engines until merged;
  - particles, audio, prefabs, plugins;
  - asset tooling;
  - save formats until migrated;
  - generic combat.
- Post-processing is unreachable, but is kept until someone wires it or decides to archive it.
- Monster code stays a future plugin; no generic system depends on it.

**Changed in Milestone 7** (bug fixes found by running the engine; each has a regression test):

| Change | Why | Restore |
|---|---|---|
| `LightManager._draw_layer_safe` draws lights through the world camera, then returns to the GUI camera | Light glow ignored the camera (drawn at world coordinates in screen space) while shadows used it | `git show d32e58d:engine/lighting/__init__.py` |
| `configure_scene_lighting` (split out of `load_scene`) clears object lights and resets the room ambient to the project default; new `LightManager.clear_dynamic_lights` | Lights and darkness leaked into later rooms | `git show d32e58d:engine/scene_lifecycle_controller.py` |
| `DayNightCycle` applies its colour at start-up only when enabled | It overwrote the project's ambient while switched off | `git show d32e58d:engine/day_night.py` |
| SequencePlayer `move_to`, Patrol and FollowTarget pass this frame's distance to the mover | They passed a speed and `dt`; the mover ignores `dt` | `git show d32e58d:engine/behaviours/<file>` |
| `SpriteDrawList.build_batches` merges only consecutive draws | Batching broke y-sort order | `git show d32e58d:engine/render_queue.py` |
| Sprite shadows anchor at the feet (`sprite_feet_y`, shared with y-sort; renamed from `_sprite_feet_y`) | Anchored at the centre, opaque sprites hid their own shadow | `git show d32e58d:engine/sprite_shadow_model.py` |
| Projectile velocity converted to arcade's per-frame unit | Shots moved 300 px per frame | `git show d32e58d:engine/behaviours/projectile.py` |
| `engine/editor/hd2d/sprite_outline_model.py` moved to `engine/sprite_outline_model.py`; both old import paths are shims | The render path's only `engine.editor` dependency | Shims keep old imports working |
| Ratchet baselines: lighting exception-envelope line numbers (+2), silent-pass list (3 → 1); fast-marking allowlist (−1 entry) | Same handlers moved; one test file gained a marker | Documented update commands |

## Milestone 8: runtime reliability

Report: [`docs/reviews/milestone8_runtime_reliability.md`](docs/reviews/milestone8_runtime_reliability.md). Nothing was deleted. Restore any file as it was before with `git show da2616b:<path>`.

| Change | Why | Restore / note |
|---|---|---|
| Room memory (`engine/scene_runtime/room_memory.py`; hooks in `load_scene` and `build_slot_payload`): authored objects removed during play stay removed per room, in the game state | Collected objects came back after leaving a room or loading a save | Stored as the game-state variable `room_memory`; a new game clears it. Older saves load unchanged: they simply have no room memory. |
| `SceneController.room_path` and `SceneLoader.last_saved_from`; saves record the real room in `meta.scene_path` | After a load, saves recorded the save file as their room | — |
| SaveManager queues a loaded save's object states for the saved room (`_pending_saved_entities`) | They were applied to the room being left | The immediate apply is unchanged |
| `project_ops._arrival_spot`: door arrivals stay on the map | Arrivals 96 px below a bottom-row door were outside the map | Already-authored arrival spots are not moved |
| Studio resets the game state when play stops | Editing would otherwise hide objects collected in play | `engine/studio.py` |
| Hard-shadow polygons drawn through the world camera | They ignored zoom | `engine/lighting/shadow_pipeline.py` |
| `apply_scene_settings` no longer returns early on a named background colour; a room without day/night keys gets the project's setting; `LightManager.base_ambient_color` | Day/night and `initial_spawn` were skipped in Studio rooms; day/night leaked between rooms | `engine/scene_runtime/scene_load_apply.py`, `engine/game.py` |
| `settings.lighting_enabled` read per room | Documented and used by demo scenes, never read | Rooms without the key keep the project's setting |
| EnemyAI moves every frame, steering every `repath_interval` | It moved only when it steered | `engine/behaviours/enemy_ai.py` |
| NpcSchedule finds its Patrol on its first update | It looked before the behaviours were attached | `engine/behaviours/npc_schedule.py` |
| QuestHook also listens on the live event path when no gameplay bus exists | It subscribed only to a bus the game never creates | **Consolidation:** the live bus is the one path in play. The gameplay bus stays for the episode harness; events go to one or the other, never both. |
| F6 in play loads the SaveManager quick save | It loaded `save_1.json`, which F5 writes only without a SaveManager | **Consolidation:** `SaveGameV1` remains only as the no-SaveManager fallback of F5 and F6 |
| **Deferred:** `background_planes` → `background_layers` | Different coordinate models; layers have no alpha or offset; no content uses planes | The lab reports it as KNOWN |
| **Deferred:** quick snapshot (`quick.json`, Ctrl+F6) into slots | The monster companion's persistence is built on it | Needs a migration of that state |

## Milestone 9: test trustworthiness and repository health

Reports:
- [`docs/reviews/milestone9_test_audit.md`](docs/reviews/milestone9_test_audit.md)
- [`docs/reviews/milestone9_repo_health.md`](docs/reviews/milestone9_repo_health.md)

Restore anything with `git show 05a8d40:<path>`.

| Change | Why | Note |
|---|---|---|
| **Removed** `engine/input_runtime/capture_key_router_model_v2.py`, `capture_key_router_v2.py`, `capture_runtime_v2.py` | Self-described deprecated v2 alias shims; zero references anywhere | The real modules are unchanged |
| **Removed** `engine/tooling/precommit_check.py` | Unreferenced 14-line wrapper of `engine.tooling.check` | `engine.tooling.check` stays |
| **Removed** `engine/editor/confirm_modal_preview_model.py` | Logic model never wired to anything; zero importers | Its two ruff-baseline lines removed too |
| **Removed** `tooling/debug_parser.py` | Imported a non-existent `mesh_cli_v2`; could not run | — |
| **Removed** 14 copies of Creator Mode's "package import doesn't import the renderer" subprocess test; `tests/test_ui_persistence_across_scene_rebuild.py`; `test_camera_follow_shake.py::test_gui_camera_unchanged_by_shake` | Byte-for-byte duplicates (a strict subset, for the file) | One copy of each contract remains |
| `tests/test_assets_reload_is_import_safe.py` restores the modules it removes; `test_editor_keybinds_controller.py` swaps modules only during its own imports | Six "baseline failures" and order-dependent results | — |
| RMMZ passability tests use a generated map | They depended on the owner's mutable project | The owner's map is an optional smoke check |
| `test_editor_input_regression.py` asserts the click point as the drag start | The design changed in `2909190` | — |
| 18 slow/e2e tests repaired (stub signatures, patch targets, fixture prefab fields, facade lookup points); `test_integration.py`'s arcade mock keeps real key constants | Stale harnesses | — |
| `tooling/mypy_gate.py` excludes untracked folders | A project's `main.py` stopped mypy entirely | The baseline is unchanged: the type debt is not hidden |
| Creator Mode rollback swallows use `_log_swallow` (CRMC-001..003) | Bare `except: pass` broke the swallow policy | Same best-effort behaviour |
| **Not deleted, recommended:** `build/web/mesh.apk` (15.2 GB, a broken March web build that swept up `artifacts/`) | Owner's disk, outside git, irreversible | Rebuild with `py -3.13 tooling/build_web.py`. **Deleted in Milestone 10** with the owner's authorisation |

## Milestone 10: Studio lighting, animation verification, targeted cleanup

Report: [`docs/reviews/milestone10_lighting_animation.md`](docs/reviews/milestone10_lighting_animation.md).

| Change | Why | Note |
|---|---|---|
| **Deleted** `build/web/` (`mesh.apk` 15.2 GB, `mesh.tar.gz`, `index.html`, `favicon.png`; untracked, git-ignored) | Owner-authorised; a broken March build. 15.26 GB reclaimed | Rebuild: `py -3.13 tooling/build_web.py`. `build/lib`, `bdist.win-amd64`, `version.txt`, `web-cache` kept |
| Automatic wall occluders also read a scene's inline `tile_layers` | Walls painted in Studio never cast shadows | **Behaviour change:** older Studio rooms with lighting and hard shadows on now get wall shadows |
| Hard-shadow polygons extend past the radius and the corners (5 points, was 4) | Walls reaching past the radius shaded the lit side | The determinism golden was updated to the new shape |
| A room's `lighting_ambient_color` is honoured | A room could only darken the project's ambient | A room without it uses the project's, as before |
| Studio's edit view draws through the lighting layer | No preview of lighting while editing | Only when the room's lighting is on |
| Lighting ops in `project_ops`; the authoring API accepts ops that return a light's index | Studio and AI share one validated path | — |
| `InspectorMixin` declares its host interface (TYPE_CHECKING); callback params typed `-> object`; 12 lambdas → `functools.partial` | ~250 type errors from one pattern | No runtime change |
| GUI driver verifies the cursor after each move and before each press | The recurring Milestone 1 FLAKY | Fails clearly instead of clicking elsewhere |


## Milestone 11: first-time creator experience

Report: [`docs/reviews/milestone11_creator_experience.md`](docs/reviews/milestone11_creator_experience.md).

| Change | Why | Note |
|---|---|---|
| **Project layout:** the player is the prefab `player` in `assets/prefabs.json` (`metadata.shared_player`); rooms keep `{"id", "x", "y", "prefab_id": "player"}` | One player for the whole game | Old projects: Studio shares identical players on open (one undo step) and asks about differing ones. Nothing changes on disk until the creator saves |
| `components.collider: {"kind": "box", "auto": true}`, a feet box sized to the picture; the default for the player and Person | Characters stopped at gaps they visibly fit through | `"auto"` added to the entity schema; explicit boxes, whole picture and circle unchanged |
| `engine/behaviour_guide.py` (labels, categories, settings, problems) over the behaviour registry | Plain-language behaviours | No registry name, stored setting or alias changed; aliases are only hidden |
| `engine/route_check.py` (reuses the nav grid, line of sight and A*) | Route warnings | Read-only checks; Patrol itself unchanged |
| **Toast policy:** every successful save/load says "Game saved"/"Game loaded"; a failed save says why | A repeated save used to say nothing | `test_saved_toast_idempotent.py` and `test_loaded_toast_idempotent.py` now pin the new policy (file names kept) |
| `PlayerHUD.draw` draws toasts on their own | Toasts never showed for a player without health stats (every Studio game) | The controls banner ("F2: Editor...") is skipped in Studio play-tests |
| Pause menu: Quit is "Exit Play-Test" in Studio and stops the play-test; slots have readable labels | Esc menu in play-tests | Outside Studio, Quit still closes the game |
| Starter art `starter_hero.png`, `starter_villager.png`, `starter_sign.png` (generated: `tooling/make_starter_art.py`; `docs/starter_art.md`) | Distinguishable characters, no placeholder squares | `animated_player.png` kept: older projects use it |
| New Person and Sign: `Dialogue.once = false` | "Only once" people went silent after one talk | The `Dialogue` default (true) is unchanged; only the templates' prefabs |
| Animator fits the hit box to each new frame; measures movement when there's no velocity | Shadows and depth sorting used the whole sheet; patrolling NPCs never walked or turned | Same as the frame-list animator already did |
| `project_ops.add_line(link=False)` | "+ Separate line" | Default unchanged |
| Studio layout dump: labels, the game menu and active toasts | The Milestone 11 acceptance test | Test-only (`MESH_STUDIO_LAYOUT`) |

## Milestone 12: shadows that belong to their light

Report: [`docs/reviews/milestone12_shadow_quality.md`](docs/reviews/milestone12_shadow_quality.md).

| Change | Why | Note |
|---|---|---|
| With shadows on, `LightManager` draws through `engine/lighting/light_compositor.py`: per-light occlusion masks, `final = diffuse * (ambient + sum light_i * (1 - occlusion_i))` | The overlay painted black over the room light and every other lamp, from one chosen light | Shadows off: Arcade's `LightLayer.draw()` exactly as before. GPU failure: lit without shadows, `shadows_unavailable` in the stats |
| **Kept for comparison, not deleted:** `end_hard_shadows_overlay` behind `MESH_SHADOWS_RENDERER=legacy` | Before/after measurements | Retire with `end_hard_shadows_composite` (still unreachable), `hard_shadows_backend.py` and `shadow_selection` once the owner has seen the new shadows |
| `shadows.light_shadow_polygons`: back-edge, arc-ended shadows on one shared reach; rectangles cast like polygons | Lit wedges behind long slanted walls, cracks between joined walls, walls shadowing themselves | `build_shadow_polygons` and `build_shadow_polygons_v1` unchanged (legacy path and their tests) |
| Soft edges: `lighting_shadow_softness` (`sharp`, `soft`, `softer`) per room and in the project config; the lamp sampled as a disc | Controlled softness without blurring the scene | **New config key** (schema updated); default `sharp`. The pause menu's "Soft Shadows" runtime toggle still does nothing (it fed only the unreachable composite path) |
| Light `"shadows": false` (schema updated); ops `set_light(shadows=)`, `set_room_lighting(softness=)` | Per-light control | No key means it casts shadows, as before |
| A room without `lighting_shadows_mode` follows the project's | It kept the previous room's: lighting state leaked between rooms | `MESH_SHADOWS_MODE` still overrides |
| `MESH_LIGHTING_PROFILE=1`: GPU timer and CPU time around `lighting.end()`; the runtime snapshot carries `profile` and the renderer's `stats` | Measured performance | Off by default (reading a GPU timer waits for the GPU) |
| `tooling/shadow_bench.py`, `tooling/shadow_lab.py` (in the runtime gate), `tests/test_shadow_*_gpu.py` (`MESH_GL_SMOKE=1`) | Pixel-level verification | The lab runs the GPU tests too |
| `tests/test_pipeline_lighting_no_silent_pass_contract.py`: baseline line numbers moved | The same handlers, shifted by new lines | No handler added or removed |

## Milestone 12.1: character shadows, natural flicker, shadow fine-tuning

Report: [`docs/reviews/milestone12_1_lighting_polish.md`](docs/reviews/milestone12_1_lighting_polish.md).

| Change | Why | Note |
|---|---|---|
| Characters cast shadows from lamps through the per-light compositor: `character_shadows`, `_character_quad`, a 14-float occluder vertex (atlas UV, body rect) | Players and NPCs had only the ellipse under their feet | Players and NPCs cast by default; entity `cast_shadow` (bool or `{enabled, height, strength, length}`) and the existing `shadow_enabled` (schema updated). Op `set_shadows` |
| `flicker_sample` and `FLICKER_PRESETS` (Candle, Torch, Fire, Faulty lamp; Steady, Custom); brightness reaches the light through `set_light_colour` | The old flicker pulsed on a regular beat and only moved the reach; its brightness never reached the screen (Arcade keeps `Light` colour private) | **Kept:** `FlickerNoise` and `apply_light_flicker` (lights without a profile, their tests). New light keys `flicker_preset`, `flicker_strength`, `flicker_brightness`, `flicker_reach`, `flicker_irregularity` (schema updated). Older lights read as Custom from `flicker_amount` / `flicker_speed`, nothing rewritten |
| Studio light panel: preset buttons and Calmer / Livelier replace the Flicker toggle and the amount / speed fields | Presets first, numbers under More settings | `tooling/acceptance_lighting.py` and `tooling/shadow_lab.py` press the preset buttons now |
| Room fine-tuning: `lighting_shadow_edge`, `lighting_shadow_strength`, `lighting_shadow_quality`, `lighting_character_shadows`; `scene_lifecycle_controller.apply_shadow_look` | Tune shadows without losing the presets | Defaults are not stored; each falls back per room. The shadow bench applies settings through the same function |
| User setting `reduced_flicker` ("Calmer Flickering" in the pause menu) | Accessibility | Golden user-settings and pause-menu row tests updated for the new row |
| Lighting stats gain `character_feet`; the runtime snapshot's flicker `clock` to 4 decimals | Diagnostics; the lab checks each flicker sample against the formula | — |
| `tooling/lighting_polish_lab.py` (in the runtime gate), `tests/test_natural_flicker.py`, `tests/test_character_shadows_gpu.py`, `tooling/flicker_plot.py` | Verification | GPU tests need `MESH_GL_SMOKE=1`; the lab runs them |
| `tests/test_pipeline_lighting_no_silent_pass_contract.py`: baseline line numbers moved again | The same handlers, shifted | No handler added or removed |
