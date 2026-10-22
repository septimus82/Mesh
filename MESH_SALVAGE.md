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
| Plugin system (`plugin_system.py`) | **REFACTOR later** | Loads `mods/` only from the engine repo root, only at game runtime; projects can't add behaviours. | Needed for "advanced scripting stays available". |
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

