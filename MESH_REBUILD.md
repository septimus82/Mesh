# Mesh — Rebuild Log

Branch: `redesign/visual-editor` (from `52d43a4`; original preserved as tag `archive/pre-redesign-2026-10`). Not merged to `main`; it awaits review.

## Milestone 1 — the first creation workflow

**Goal:** create a project → open a map → place an NPC → give it dialogue → create another room → connect the rooms → play → save → load → return to editing.

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| A new project opens into a usable visual editor | **Done** | `mesh new` + `mesh edit` opens Mesh Studio: rooms and objects on the left, map in the middle, inspector on the right. |
| The template gives an immediately playable start | **Done** | Starter has a walkable player and a Guide who talks. |
| An object can be placed directly on the map | **Done** | Click "Person" under Objects, then click the map; or right-click an empty spot → "Place Person here". |
| Right-click gives meaningful actions | **Done** | On an object: Rename, Edit what they say, Add behaviour…, Delete. On empty map: Add door to <room>, Add door to a new room…, Place <object> here. |
| "Add behaviour" discovers registered behaviours and shows suitable fields | **Done** | Picker lists all 62 registered behaviours with search. Fields come from the registry: numbers and text as inputs, booleans as On/Off. Lists and objects shown read-only, labelled as such. |
| NPC dialogue is editable and works in play | **Done** | "Says" field in the inspector; verified in game (speaker and text). |
| Creating a room adds it to the project and the editor | **Done** | Registered in the world file, listed under Rooms, gets its own player. |
| A linked door connects both rooms with valid arrivals | **Done** | One action creates a walk-in door in each room plus an arrival spot beside the far door. Held keys are released on arrival, so you don't bounce back. |
| Play-test from the editor | **Done** | F4 or the Play button runs the current documents (saved or not); F4 or Stop returns. Edits are untouched by whatever happened in play. |
| Save/load accessible and restores state | **Done** | Esc → pause menu (Resume, Settings, Save Game, Load Game, Quit). F5 quick save, F9 quick load, with toasts. Quick save is a slot the pause menu lists. |
| Undo/redo for editor changes | **Done** | Ctrl+Z / Ctrl+Y and buttons; whole-document snapshots, so every Studio edit is undoable, including creating rooms and doors. |
| Every visible control works or is visibly disabled | **Done for the Studio** | Save, Undo and Redo disable when there's nothing to do. No inert labels styled as buttons. |

### How it was validated

**Whole-workflow, real window:** `tooling/acceptance_first_workflow.py`.
- A fresh `mesh new` project, driven with OS-level mouse and keyboard input through `tooling/gui_driver.py`.
- Positions and state come from the Studio's opt-in layout dump (`MESH_STUDIO_LAYOUT`), and saved files are checked on disk.
- **15/15 steps pass:** create, open, place, give dialogue, rename, undo/redo, right-click → add behaviour, new room with a door, furnish the second room, save, files valid on disk, play and talk (dialogue text and speaker checked), door round trip (arrival positions checked, and checked again a second later to catch bouncing), F5 → move → F9 restores the exact position, stop returns to unchanged documents.
- Screenshots of every step are written next to the report.

**Headless:** `tests/test_project_ops.py` (9), `tests/test_studio_project.py` (4).

**Full suite on the branch head:** 9 failed, 9,263 passed. These are the same 9 failures as the baseline (headless widget rendering ×5, battle-sprite headless probe, RMMZ fixtures ×2, editor drag-start). None are new. The ruff gate and the mypy island are clean.

**Not validated:**
- **No human has used the Studio yet.** Every check above is automated.
- Only tested at 1280×720 on one Windows machine, with a 125% main monitor.
- Mouse-wheel zoom and middle-drag pan are implemented but not exercised by the acceptance test.

### Bugs found and fixed while building it

Each was found by driving the real window, not by the existing unit tests.
1. Scene validation ran with an empty behaviour registry, so every CLI validator rejected valid scenes (`dcee165`).
2. Behaviour form fields dropped declared params (`dcee165`).
3. Logic-only entities (arrival spots) were drawn as grey squares in play: the draw plan ignored `sprite.visible`.
4. Walking into a door with the key held bounced the player between rooms indefinitely.
5. F9 never loaded (it was claimed by a silent debug pause and by a sprite-batching toggle). Esc opened Settings, making the pause menu unreachable.
6. Loading a save slot crashed the game (scene-schema validation of save metadata), so Load Game in the pause menu had never worked.
7. A failed load during play threw the player back to the start scene.
8. Clicking an `arcade.gui` text field put the caret at the start, so typing went in front of the old text.

## Known limitations (honest list)

- **Placeholder character art.** Still the coloured-square sheet; the owner's decision.
- **One-line dialogue.** "Says" edits the first line only; multi-page dialogue and choices need a better editor.
- **No clipboard in text fields.** Inherited from `arcade.gui`.
- **New rooms are empty floors.** No tile painting in the Studio yet; the legacy editor still has it.
- **Two editors coexist.** Mesh Studio for projects with a world; the legacy editor for the engine repo's own showcase and via `MESH_LEGACY_EDITOR=1`.
- **The legacy editor no longer shows arrival markers.** They are invisible sprites now; the Studio draws its own markers.
- **AI and CLI still use the old operation layers.** `project_ops` is canonical for the Studio only, so far.
- **Monster code and demo content are still in the core** (see `MESH_SALVAGE.md`).

## Trimming done so far

All recorded with restore instructions in `MESH_SALVAGE.md`:
- Root session leftovers and 224 committed test artefacts removed (`154691d`).
- Monster data moved behind an opt-in `monster` template (`f871855`).
- Two dead modules removed (`c14f722`).

## Next slices, in order

1. **AI on the same operations:** MCP `apply_ops` / live ops call `engine/project_ops`, proposals become a thin preview wrapper, and `OP_CATALOG` is generated.
2. **Tiles in the Studio:** paint the floor and walls of a room. Rooms are visually empty today.
3. **Monster code as a plugin** via `PluginManager`; project-scoped `behaviours/` folder for custom scripts.
4. **Archive the legacy editor and Creator Mode** once the Studio covers tiles and lights; archive demo content and its ~62 tests.

## Decisions needing the owner

- **Starter art:** pick or generate a character and NPC sprite. Everything a newcomer sees is coloured squares.
- **Door style:** doors are walk-in (touch to enter), the RPG Maker convention. Press-E doors exist as a behaviour setting (`allow_interact`). Is walk-in the right default?
- **Engine-repo showcase:** keep it, and with it the legacy editor, or archive it with the demo content?
