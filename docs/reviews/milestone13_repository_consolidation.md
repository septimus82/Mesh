# Milestone 13: Repository Health, Architecture Consolidation & Technical Debt

Branch `redesign/visual-editor` (draft PR #344, unmerged), from `db87ab8` (Milestone 12.2).

**No test in this milestone moved the owner's mouse, pressed keys or put a window on the screen.** Everything ran
headless or in hidden windows. Since this milestone, the test session itself keeps every window hidden (see
Stage D).

## Before and after

All figures are measured. Code figures come from the git trees of `db87ab8` and the final commit, so line endings
don't skew them; times are from this machine.

| Metric | Before (`db87ab8`) | After | Change |
|---|---|---|---|
| Tracked production modules (`engine/`, `mesh_cli/`) | 1,048 | 1,047 | −1 |
| Tracked production lines | 258,088 | 257,472 | **−616**, after adding the typing and the window fix |
| Duplicate implementations of the common edits (lights add/change/remove, object removal, behaviour settings, object lookup) | 2 each: `project_ops` and AIOps; lookup in authoring and AIOps | 1 each (`project_ops`) for Studio, authoring, MCP and console | **5 duplicates removed**. The legacy editor's live ops are kept with it. |
| Type errors beyond the baseline | 259 | **0** | −259; no new ignores, 2 removed, baseline unchanged |
| Known slow/e2e failures | 31 | **1** (the wheel: owner decision) | −30 |
| Default headless suite | 9,437 passed (M12.2) | **9,435 passed, 0 failed** (445 s) | −8 test files of the removed path, +7 new tests |
| Fast development check (`test_tiers tier0`) | couldn't complete on this machine (unwritable pytest cache under `-W error`) | **118 s**, 4,326 passed | usable |
| Tracked repository (git tree) | 3,510 files, 33.28 MB | 3,502 files, 33.25 MB | −8 files |
| Windows shown on the desktop by a full test run | ~12 test files' GameWindows | 0 | — |

## Stage A: baseline

- **Repository.** 3,510 tracked files (33.3 MB). Production code is `engine/` and `mesh_cli/`: 1,048 modules,
  258,088 lines. Tests: 1,731 files.
- **Entry points.**
  - Supported: `Mesh Engine.bat`, which opens the launcher and then Mesh Studio (`mesh_cli edit` on a Studio
    project), and `mesh play`.
  - For AI and scripting: the authoring API, `mesh author`, and the MCP server.
  - Legacy, reachable: the legacy editor (`MESH_LEGACY_EDITOR=1`, or the engine repo's own showcase), with Creator
    Mode, and `mesh demo`.
- **Type debt.** 259 errors beyond the accepted 75-entry baseline, 335 in total. Monster data loading alone had 41,
  `studio.py` 39, battle mode 22, Studio inspector and Creator Mode 16 each.
- **Slow/e2e.** The 31 known failures were 30 `verify-all` pipeline tests (blocked by the type gate) and the wheel
  test, as the Milestone 9 audit found.
- **Which slow/e2e tests reach the desktop.**
  - Five files build a real `GameWindow` in the test process. In the default suite, twelve test files did, and
    their windows appeared on screen.
  - The subprocess tests run the CLI's `--help`, `verify-all`, or a windowless runtime smoke
    (`play-runtime --headless-smoke` loads the room data without a window).
  - No slow test runs `release-check`, `mesh demo` or the perf/trace tools, the CLI paths that open a game window.
  - Conclusion: with in-process windows hidden, the slow/e2e set does not touch the desktop.

## Stage B: one implementation for common edits

**How edits flowed before.**

| Caller | Lights | Remove an object | Behaviour settings | Which object |
|---|---|---|---|---|
| Mesh Studio | `project_ops` | `project_ops` | `project_ops` | by id |
| Authoring API, `mesh author`, MCP `propose/apply_changes` | `project_ops` | `project_ops` | `project_ops` | id or unique name (authoring's own resolver) |
| MCP `apply_ops` on a Studio project | **AIOps** (refused while Studio is open) | `project_ops` (M6 adapter) | `project_ops` (M6 adapter) | M6 adapter |
| MCP `apply_ops` on any other scene; the in-game console's AI jobs | **AIOps**: its own normalisation, any key accepted | **AIOps**: by name only | **AIOps**: deep merge, nothing checked | name only |
| MCP's one-call `add_entity_from_prefab` tool | — | — | — | **AIOps, even on a Studio project**, writing files behind an open Studio |

So "set this light's radius to 3" was refused in Studio ("Size" must be at least 8) but written by an MCP client.
And a light added by MCP lacked the validation and colour normalisation Studio applies.

**After.**
- AIOps runs these operations through `project_ops` on any scene file:
  - `add_light`, `set_light`, `remove_light`;
  - `remove_entity`;
  - `add_behaviour` and `set_behaviour_param`.
- **What AIOps keeps is only its request shapes.** A light is still given as `{x, y, radius, color, ...}`, and a
  dialogue patch is still merged into the current dialogue.
- **Objects are resolved by one function,** `project_ops.entity_ref` (id, or a unique name). The authoring API now
  uses it too.
- **On Studio projects, MCP's light operations take the shared authoring path,** like the object operations, so
  they become a proposal while Studio is open. The one-call add tool goes through `apply_ops`, so it no longer
  writes files under an open Studio.
- **`set_light` gained `mode`** (`soft` or `hard`), the one setting AIOps clients could set that the canonical
  operation lacked.
- **Errors are now the same everywhere.** Examples: "Size must be...", "Lights have no setting 'intensity'...",
  "N objects are called 'X'; use an id", "Patrol has no setting called '...'".
- **Undo.** Studio and authoring undo are unchanged. AIOps edits files directly, as before.
- **Compatibility.**
  - Older scenes with objects lacking ids (2 of the repo's 1,544 objects) get ids when AIOps edits them.
  - An unknown light setting, which AIOps used to store silently, is now refused.
- **Proof.** `tests/test_one_editing_path.py`: the same light from Studio's operation, MCP and AIOps is
  byte-identical, and the refusals match.

**Deliberately not migrated, and why.**
- **AIOps `paint_tiles` on older scenes, and the CLI's `scene tilemap` commands:** they edit the legacy tilemap
  format (`tilemap.overrides.layers` / Tiled files), which `project_ops.paint_tiles` (inline Studio layers) doesn't
  model. Studio projects already go through the M6 adapter.
- **CLI `scene add-entity` / `world link`:** prefab overrides and world links on legacy scenes. They are a separate
  data model, too large for this milestone.
- **The legacy editor's live operations** (`editor_live_ops_controller`) edit the running scene's sprites with
  their own undo commands. They stay with the legacy editor until it is retired.

## Stage C: type debt, 259 to 0

Every error was fixed at its source. No new `type: ignore` (two unused ones were removed), no baseline change, no
blanket `Any`.

| Area | Errors | What was wrong / the fix |
|---|---|---|
| Mesh Studio, inspector, launcher, UI | ~60 | Loop lambdas binding the loop variable through default arguments became nested functions or `partial`. The inspector's host contract now declares `menu` and `_focus_after_build` as optional, as the Studio sets them. `StudioAI` refuses a proposal whose changes aren't a list instead of failing inside the dry run. |
| `project_ops`, authoring | 14 | Untyped dialogue graphs; an id typed `object`; the operation registry's dict type. |
| Monster data loading | 41 | The validators returned `None` beside an error the callers always checked first. They now return an empty value, so each field has the type it claims. |
| Monster battles | ~30 | `MonsterInstance.current_hp` and `stats` and `BattleStats.sp_attack` and `sp_defense` are optional at construction but always set afterwards. Read-only `hp`, `battle_stats`, `special_attack` and `special_defense` give the filled values. The companion turn's result is declared optional, as it is. |
| Creator Mode, legacy editor live ops and chat (legacy editor, reachable) | 36 | The click handler's declared result omitted two results it returns. A missing number in a live op is now refused like any other bad number. Payloads are typed. |
| Runtime odds and ends | ~20 | Optional cameras and providers; `MESH_RESIZE_DIAG` tuples; an MCP SDK import that names whichever class the installed version has; `LightManager.base_ambient_color` and `EditorModeController.tile_layer_index` declared where they were set. |
| GUI test tooling | 53 | JSON-backed helpers returning `Any` under a declared type (typed locals); one `.raw` buffer. |

The type gate (`tooling/mypy_gate.py`) passes.

## Stage D: verification

**Failures classified.**

| Test(s) | Before | Classification | Now |
|---|---|---|---|
| 26 `verify-all` pipeline tests | Failed at the type gate | Blocked by real type debt | **Pass** (Stage C) |
| `test_cli_verify_all` success path, `…_schema` | Stale artifact lists | Outdated expectation: the pipeline gained 12–13 artifacts by design (`authoring_trace`, `overlay_perf`, `runtime_smoke`, `web_smoke`, …), and `web-smoke` reports a skip without a web build | **Repaired**: lists updated, `web-smoke`'s skip allowed by name |
| (found while repairing) the swallow-scan step | — | **Genuine defect**: it reported `artifacts/swallow_scan.json` as an artifact even without `--artifacts`, unlike every other step | **Fixed** in `mesh_cli/verify_steps/pipeline.py` |
| `test_cli_verify_all_includes_doctor_assets` | Pipeline exit 1 | Broken fixture: its fake room's object had no x/y. The runtime smoke added later correctly refused the room. | **Repaired** fixture |
| `test_mesh_cli_headless_imports::…verify_all…` | 60 s timeout | Infrastructure: the whole pipeline ran under a quick command's 60 s budget | **Repaired** budget: passes, the real pipeline takes 85 s headless here |
| `test_wheel_includes_pack_data` | Fails | **Owner decision**: the wheel has never contained `packs/`. Either declare pip-installed Mesh unsupported (Mesh runs from a checkout) or package the packs. | **Unchanged**, still failing, not skipped |
| `test_editor_viewport_drag_input_capture_contract` (default suite) | Intermittent ("1 failure in 4 runs"); deterministic after `test_editor_launch_no_menu` | **Genuine defect**: arcade forgets the active window whenever *any* window closes, and pyglet closes windows when they are garbage-collected. A leftover window collected mid-test left the window in use without a context. This can also hit the real program whenever two windows exist. | **Fixed** in `GameWindow.close`; regression test `test_game_window_close_keeps_active.py` |
| XAudio2 "critical error" (`0x80070490`, the audio device went away), raised asynchronously into whichever test was running: `test_mesh_cli_headless_imports` teardown, then `test_macro_audit_ordering_is_deterministic` (which passes alone) | Twice in three slow runs | Environment dependency in the tests | **Fixed**: the test session uses pyglet's silent audio driver (no sound card, nothing played on the owner's speakers). `MESH_TEST_REAL_AUDIO=1` keeps the real one. |

**Desktop safety.**
- **`tests/conftest.py` keeps every window a test creates hidden.** It has a real GL context, but nothing is
  shown and no focus is taken. `MESH_TEST_SHOW_WINDOWS=1` shows them for debugging.
- **The default suite used to put about a dozen game windows on screen.** That was itself a source of the
  intermittent failure, since the owner's clicks could reach them.
- **`tooling/runtime_gate.py` refuses to run without `--owner-present`.**

**Entry points (measured on this machine).**

| Purpose | Command | Measured |
|---|---|---|
| **Fast feedback** while working | `py -3.13 -m tooling.test_tiers tier0` (compile check + `fast` tests) | **118 s**, 4,326 tests. At the start it couldn't complete on this machine: an unwritable `.pytest_cache` failed every tier under `-W error`. Fixed: tiers run without the cache. |
| **Targeted subsystem** | `py -3.13 -m pytest -q -p no:cacheprovider tests -k "<area>"`, e.g. `-k "light or shadow"`: 4,962 tests, 110 s; `-k "monster or battle"`: 624 tests, 18 s | as shown |
| **Full headless** (default suite) | `py -3.13 -m pytest -q -p no:cacheprovider tests` | see Final verification |
| **Slow / e2e** (headless; in-process windows hidden; no desktop input) | `py -3.13 -m pytest -q -p no:cacheprovider -o addopts= -m "slow or e2e" tests` | see Final verification |
| **Hidden-window GPU** (exact pixels; rendering changes) | `py -3.13 -m tooling.test_tiers gpu` (new tier) | **14 s**, 46 tests |
| **Hidden-window real renders** (game and Studio) | `py -3.13 tooling/visual_polish_check.py`, `tooling/scene_snapshot.py` | not re-run (no rendering change since 12.2 except the removed dead path) |
| **Owner-authorised GUI acceptance** (real mouse and keys) | `py -3.13 tooling/runtime_gate.py --owner-present [--only ...]`; refuses without the flag | **Not run** (desktop restriction) |

- **Parallel runs.** `pytest-xdist` isn't installed, and `test_tiers --xdist` falls back to a serial run, so
  parallelism wasn't measured.
- **Splitting into processes isn't safe as the suite stands.** Session-scoped guards (`projects.json`, the shared
  `artifacts/` folder some runner tests write to) and the module-level window state above would conflict between
  workers. Installing xdist and fixing those is a separate, measurable step.

## Stage E: dead code removed

| Removed | Proof it was unused | Tests removed with it | Recover |
|---|---|---|---|
| `LightManager._end_hard_shadows_composite` → `shadow_pipeline.end_hard_shadows_composite`, `draw_hard_shadow_fallback`, the layer draw-compat helpers, and `engine/lighting/hard_shadows_backend.py` | No caller in `engine/`, `mesh_cli/` or `tooling/` (git grep). Milestone 7's inventory: "nothing calls it". Milestone 12's per-light compositor replaced it, including soft shadows. | 8 files (`test_hard_shadows_composite_*`, `…_backend_headless_safe`, `…_fallback_visible_path`, `test_soft_shadows_render_inputs_contract`, `test_ambient_tint_defaults_contract`) that tested only this path | `git show db87ab8:<path>` |
| `shadow_pipeline.draw_pending_shadow_fallback`, `LightManager._draw_pending_shadow_fallback` | No caller; the list it drew was never filled | — | same |
| Repository-root `projects.json` (now ignored) | Not read since Milestone 4: recent projects live in the user folder (`engine/projects.py`). The editor workspace model's `projects_path` field is never read. It held this checkout's local path. | — | same |
| AIOps' own light, removal and behaviour-param code (Stage B) | Replaced by the canonical operations; no other callers | — | same |

- `shadow_pipeline.py` went from 787 to 237 lines.
- **Kept:**
  - the legacy hard-shadow overlay (`MESH_SHADOWS_RENDERER=legacy`: still selectable, used by the M12 before/after
    lab) and `draw_direct_shadows` (live);
  - the 18 importer-less legacy-editor shims, which go with the legacy editor;
  - the legacy editor, Creator Mode, the showcase, monster code and the animation systems, none of which is
    replaced elsewhere.

**Found, not removed (owner decision).** The pause menu's **"Soft Shadows"** toggle (`soft_shadows_enabled`) has
done nothing since Milestone 12; it fed only the composite path above. The room's Sharp / Soft / Softer setting
replaced it. Removing a player-facing setting changes the settings screen and the saved-settings goldens.
Recommendation: remove the row and keep the key accepted (ignored) for old settings files.

## Compatibility

- **Projects from Milestones 10–12.2 load unchanged.** No file format changed, and the optional keys from 12.2
  remain optional.
- **AIOps refuses settings it used to store silently,** for example unknown light keys or unknown behaviour
  parameters. MCP clients get the same messages Studio gives.
- **AIOps gives id-less objects in older scenes an id when it edits them.**
- **The hard-shadow composite path is gone.** It was unreachable, so nothing that ran changes.

## Remaining architectural risks

1. **Several authoring paths remain for legacy data.** CLI `scene`/`room`/`world` commands, AIOps tile painting on
   the legacy tilemap format, and the legacy editor's live ops. One model per data format is the next step.
2. **The duplicate runtime systems from the Milestone 7 plan remain:** three timeline engines, three quest systems,
   two animation systems, three save formats, two parallax systems and two prefab models.
3. **Input-capture import cycle:** behaviour-sensitive, and needs the real-window gate.
4. **The real-window suites now need the owner present.** Only headless and hidden-window checks run unattended.

## Recommendations for the next milestone

1. **Decide on pip-installed Mesh** (the wheel test) and on the dead "Soft Shadows" toggle: two small owner decisions.
2. **Route the CLI's Studio-project commands through `authoring`.** Retire their duplicates for Studio projects,
   leaving the legacy formats where they are.
3. **Install `pytest-xdist`, make the session guards and `artifacts/` writes worker-safe, then measure a parallel
   run.**
4. **Consolidate one duplicate runtime system per milestone,** starting with quests (the plan in the Milestone 7
   report).

## Commits

- `452dc2c` One implementation for lights, object removal and behaviour settings
- `20cd9b0` Type debt: 259 errors beyond the baseline down to 0
- `4dab4d4` Tests never show a window; closing a window keeps the active one
- `57182dd` Retire the unreachable hard-shadow composite path; untrack projects.json
- `f79a530` verify-all tests repaired; the swallow scan honours --artifacts
- `40a239e` Tier marker for the window-close regression test
- The report, MESH_REBUILD / MESH_SALVAGE, and the silent test audio (the commit after these).

## Final verification

Both runs were on the final code, each run once:

| Check | Result |
|---|---|
| Default headless suite (`pytest tests`) | **9,435 passed, 54 skipped, 0 failed**, 445 s |
| Slow / e2e (`-o addopts= -m "slow or e2e"`), with in-process windows hidden, silent audio and no desktop input | **162 passed, 1 failed** (`test_wheel_includes_pack_data`, the owner decision), 1,156 s |
| Type gate (`tooling/mypy_gate.py`) | ok, 0 beyond the baseline |
| Ruff gate, type-ignore ratchet | ok |
| Hidden-window GPU tier (`test_tiers gpu`) | 46 passed, 14 s (after the dead-code removal) |
| Fast tier (`test_tiers tier0`) | 4,326 passed, 118 s |
| Real-window runtime gate | **Not run**: it drives the desktop's mouse and keys, and needs the owner's permission (`--owner-present`). No GUI-facing behaviour changed this milestone except the window-close fix, which the hidden-window test covers. |

These are separate runs, reported as such; there is no combined "PASS".
