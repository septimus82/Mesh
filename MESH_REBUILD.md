# Mesh — Rebuild Log

Branch: `redesign/visual-editor` (from `52d43a4`; original preserved as tag `archive/pre-redesign-2026-10`). Not merged to `main`; it awaits review.

Try it: double-click **`Mesh Engine.bat`** in the engine folder. In the launcher:
1. Click **New Project**, pick **Top-down Adventure** (or **Blank Project**), name it, then **Create & Open**.
2. Mesh Studio opens on your game.

In the Studio:
- **Paint:** under **Map**, choose a layer (Ground / Walls / Above) and a tool (Brush / Rect / Fill), click a tile, and paint. Drag across several tiles for a stamp.
- **Import your own tileset:** **Import...**
- **Make things happen:** click an object; its tabs set how it **Looks** (import a PNG), is **Animated** (4-direction walking from a sheet), **Collides** (footprint and trigger zones, with handles on the map), what it **Says** (lines, choices, flags), and **When** it shows or changes. **Empty object** and **Trigger zone** are in the Objects list; **Flags** lists every flag.
- **Play:** F4. **Flags** (while playing) shows and flips flags.
- **Save:** Ctrl+S.

Next time, your game is under **Recent projects**. From a terminal: `mesh new <name>` and `mesh edit <folder>` still work.

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
- Mouse-wheel zoom and middle-drag pan were not exercised in Milestone 1. They are now (Milestone 2, check x4).

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

## Milestone 2 — visual map building

**Goal:** paint a room's floor and walls in Mesh Studio, with walls that block in play, on top of the Milestone 1 workflow. Detailed results: [`docs/reviews/milestone2_map_building.md`](docs/reviews/milestone2_map_building.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Tile palette from the project's assets | **Done** | The Map section lists the project's tileset (`assets/tilesets/starter.json`), grouped "Ground" and "Walls & obstacles (block)". |
| Select a tile and paint; click-and-drag paints continuously | **Done** | Click a tile, then click or drag on the map. Fast drags fill the gaps between mouse events (line between cells). |
| Erase | **Done** | Eraser tool: removes a wall/obstacle first, bare ground second. |
| Ground and obstacle layers; walls block movement | **Done** | `ground` and `walls` layers; `walls` is the map's collision layer, so the existing tilemap collision blocks the player. Checked in play: the player stops flush at a painted wall. |
| Visible grid, tile preview, zoom and pan while painting | **Done** | Grid and map border are drawn over the map; the hovered cell shows the brush (or a red mark for the eraser). Wheel zooms and middle-drag pans in any tool. |
| Undo/redo; one brush stroke is one action | **Done** | A stroke is applied as one edit when the mouse is released, so Ctrl+Z removes the whole stroke. |
| Save/close/reopen preserves the map exactly | **Done** | Tile layers compared cell by cell after reopening. |
| Existing formats only, edits through `project_ops` | **Done** | Tiles live in the scene's existing inline `tilemap.tile_layers` (already read by the runtime). The map file is a standard Tiled JSON skeleton. New ops: `add_map`, `paint_tiles`, `erase_tiles`, `map_info`, `cell_at`, `cell_center`. |
| Minimal starter tileset | **Done** | 16 tiles, 32 px (`tooling/make_starter_tileset.py` regenerates it). Copied into new projects. |
| New rooms are immediately editable | **Done** | 20×15, wood floor, stone-wall border, map file written at once so the room loads before it is saved. Rooms without a map get an "Add a map" button. |
| Doors keep working; switching rooms never loses unsaved edits | **Done** | Door far-sides and arrivals are placed inside the new room's walls. Checked by walking through. Unsaved paint survives switching rooms. |
| Play/Stop does not modify data | **Done** | After Stop the documents are not dirty and the tiles are identical. |

### How it was validated

**Whole-workflow, real window:** `tooling/acceptance_map_building.py`, on a fresh `mesh new` project, with OS-level mouse and keyboard input only.
- **23/23 pass** on the final run: the owner's 17 steps plus 6 interaction checks (dragging objects never paints; painting never selects or moves objects; typing in a field never triggers shortcuts; zoom and pan, then paint; right-click with a brush; unsaved paint survives switching rooms).
- In two early runs the first clicks after start-up were ignored; not reproduced in 8 later runs and a 32-click probe (see the review doc).

**Headless:** `tests/test_project_ops.py` (13), `tests/test_studio_project.py` (8), `tests/test_tilemap_tileset_slicing.py` (3).

**Full suite on the branch head:** 9 failed, 9,274 passed: the same 9 as the baseline. The ruff gate and the mypy island are clean.

**Not validated:**
- **No human has painted a map yet.** Every check above is automated.
- Same single machine and resolution as Milestone 1.
- Very large maps (the limit is 256×256) have not been tried for drawing speed.

### Bugs found and fixed while building it

1. External JSON tilesets resolved their image next to a folder named after the tileset file, so they never loaded (`caf8e1d`).
2. Multi-row tilesets were sliced upside down: row 0 of the image came out as the last row (`caf8e1d`). Every Tiled map with a tileset taller than one row was affected.
3. `map_file_paths` mangled Windows-style room paths.
4. Door far-sides and arrival spots of new rooms landed inside the new border walls.
5. The legacy editor and Creator Mode saved invalid scenes for painted rooms: the runtime snapshot added `overrides` and an empty `layers` list to inline tile layers (`005fad4`). Found by the full suite.
6. Obstacle tiles had grass baked into their background, so a rock on a wood floor showed a green square (`7e71982`).

## Milestone 3 — map tools

**Goal:**
- Bring your own tileset.
- Fill and rectangle tools.
- A layer drawn above the player.
- Basic clipboard support.
- All on the existing tilemap format and `project_ops`.

Detailed results: [`docs/reviews/milestone3_map_tools.md`](docs/reviews/milestone3_map_tools.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Import a custom tileset in the Studio | **Done** | **Map → Import...** opens a form: Browse... (the OS file dialog) or a pasted path, a name and the tile size in the image. A preview draws the tile grid and shades any edge that isn't a whole tile. |
| Correct dimensions and alignment | **Done** | The image is cut to whole tiles and scaled to the map's 32 px tiles (nearest-neighbour up, Lanczos down), so every tile lines up with the grid. Checked: 16 px tiles in play line up and collide cell-exactly. |
| Transparency | **Done** | Alpha is kept through import, the palette and the game. Checked: transparent treetop corners show the grass beneath. |
| Project-relative asset paths | **Done** | The image is copied into `assets/tilesets/` with a Tiled tileset file beside it. Map files reference it relatively; existing tile ids never change. |
| Not limited to the starter tileset | **Done** | A tileset row cycles through the room's tilesets; every room gets each imported one. |
| Rectangle tool | **Done** | Drag a rectangle; it previews, then paints as one edit. It also works with the eraser and with multi-tile stamps. |
| Fill tool | **Done** | Fills connected cells of the same tile on the active layer. On the ground it also stops at walls, so filling a walled room stays inside it. It is one edit. |
| Undo/redo for both, consistent collision | **Done** | One Ctrl+Z per rectangle or fill. Only the Walls layer collides, whichever tool painted it. Checked in play with imported wall tiles. |
| A layer drawn above the player | **Done** | "Above" layer: z 10, never collides; the runtime draws it over characters. Checked by pixel: the treetop covers the player, who walks on through. While editing other layers it is drawn see-through. |
| Rendering separate from collision | **Done** | Layer buttons Ground / Walls / Above. Collision is a property of the Walls layer only; drawing order is the layer's z. |
| Clipboard in text fields | **Done** | Ctrl+A, C, X and V in every Studio text field. Checked in the real window. |
| Clipboard for objects (extra) | **Done** | Ctrl+C / Ctrl+V and the right-click menu: copy an object, paste it at the mouse, in any room. |
| Start-up click investigation | **Ongoing** | No lost click reproduced. A related intermittent failure was traced to physical mouse movement during a run, and the GUI driver now stops on that. The app now logs its first mouse presses. |

### How it was validated

**Whole workflow, real window:** `tooling/acceptance_map_tools.py`, on a fresh project with OS-level input only, including the OS file dialog. **15/15 pass:**
- import a 16 px tileset from outside the project;
- rectangle, undo/redo;
- walls rectangle and eraser doorway;
- fill, undo/redo;
- a 2-tile stamp above the player;
- copy/paste of an object;
- text clipboard;
- save, close and reopen with everything compared;
- play under the treetops (pixel check) and against imported walls;
- stop with nothing changed.

The Milestone 1 and 2 acceptance tests pass on the same code (15/15 and 23/23).

**Headless:**
- `tests/test_project_ops.py` (20)
- `tests/test_studio_project.py` (10)
- `tests/test_tilemap_tileset_slicing.py` (4)

**Full suite on the branch head:** 10 failed, 9,283 passed.
- **The 9 baseline failures,** unchanged.
- **`test_ruff_gate_day_one_green`:** it fails only because of an untracked `mygame/` folder in the checkout. That is a hand-test project made with `mesh new`; its `main.py` has E402 findings. The gate finds nothing on the branch's own files. Delete the folder and the test passes again.
- **mypy island:** clean.

**Not validated:**
- **Nobody has used these tools by hand yet.**
- Very large tilesets (the limit is 4096 tiles) and tilesets with spacing or margins between tiles; the importer assumes a plain grid.

### Bugs found and fixed while building it

1. **Inline layers missing from a room's map file were dropped** at load. A room can now gain a layer without rewriting its map file (`3f20796`).
2. **The click-logger was garbage-collected at once.** Pyglet keeps only weak references to event handlers. Found because the log stayed empty.
3. **Labels split words.** Long multi-line labels broke words in the middle; the import form now uses one short line per sentence.

## Milestone 4 — project launcher and templates

**Goal:** open Mesh, choose what to make, start creating, without a terminal or environment variables. Details: [`docs/reviews/milestone4_launcher.md`](docs/reviews/milestone4_launcher.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| The tenth failure fixed at its cause | **Done** | The ruff gate skips untracked game projects inside the checkout and still lints engine code. Games are kept out of the engine folder by default. Generated code is lint-clean with no suppressions. `mygame/` is untouched. |
| Double-clickable entry point | **Done** | `Mesh Engine.bat`: sets the engine path itself and runs the launcher without a console. |
| Welcome screen, New and Open Project | **Done** | The "Mesh Engine" launcher. **Open Project...** uses the Windows folder picker. |
| Recent projects that persist | **Done** | Kept in `%APPDATA%\Mesh\projects.json` (the existing registry, moved out of the engine folder). A missing project is shown red, with Remove. |
| Name, destination, template picker with descriptions | **Done** | Picture cards drawn from what each template builds; a live "will be created in..." line. |
| Clear, non-destructive validation | **Done** | Every check runs before anything touches the disk: empty or invalid names, relative paths, the engine folder, existing folders or projects, missing `config.json`, moved projects. Nothing is overwritten. |
| Create & Open; open Mesh Studio directly | **Done** | The Studio starts as its own process on the game; the launcher steps aside once it shows. |
| Blank Project | **Done** | A grass map, the player and the Person object type. No monster, battle, quest or demo files (checked). |
| Top-down Adventure | **Done** | A village and a house linked by doors, collision, a Guide with dialogue, a Grandma indoors, the starter tileset, save and load in the Esc menu. Built with `project_ops`. |
| Extensible template definitions | **Done** | One `Template` entry and one builder per genre; the launcher lists those marked `launcher=True`. |
| Old templates hidden, recoverable | **Done** | `lighting_playground` and `demo_slice` (older scene layout) are kept for the CLI and hidden from the launcher. |
| Studio protects unsaved work on close | **Done** | The first close warns; a second close leaves. |

### How it was validated

**Real window:** `tooling/acceptance_launcher.py`, **20/20**:
- launch via the `.bat`;
- create a Top-down Adventure in a folder with spaces and non-ASCII letters, picked in the Windows folder picker;
- edit the map and the dialogue, play and talk, save;
- close with the X button, relaunch, reopen from Recent projects, check everything persisted;
- create a Blank project, check it is clean, add a room and an object, play;
- open a Milestone 3 project and a copy of `mygame`, both unchanged;
- five bad-path cases;
- `git status` identical before and after.

**Regression:** Milestone 1 15/15, Milestone 2 23/23, Milestone 3 15/15.

**Headless:** `tests/test_launcher_and_templates.py` (12).

**Full suite:** 9 failed, 9,296 passed. These are exactly the 9 baseline failures. The ruff-gate failure from Milestone 3 is gone, with `mygame/` still in place. The ruff gate and mypy island are clean.

**Not validated:**
- A literal double-click in Explorer. The test runs the same `.bat` through `cmd`.
- Another Windows account, or a machine without Python 3.13. The `.bat` explains what to install, but this was not tried.
- **Nobody has used the launcher by hand yet.**

### Bugs found and fixed while building it

1. **The ignored start-up clicks were the test driver.** It attached to a stale same-titled window, and its minimise-and-restore foreground trick left windows deactivated. It now refuses ambiguous titles and focuses with a title-bar click (see the review doc).
2. **Studio closed without asking.** Closing the window lost unsaved changes silently; now it warns.
3. **Enter created a project.** In an early launcher, pressing Enter in the name field created a game in the default folder. It was caught in a probe; the stray folder, created at 19:53 that day, was removed. Enter now only confirms the field.
4. **The test-session guard was incomplete.** It protected only the repo's `projects.json`; the user's recent list, user folder and default games folder are now isolated for every test.

## Milestone 5 — visual event authoring

**Goal:** a person builds a small conditional, animated, dialogue-driven scene entirely in Mesh Studio, without code, JSON or an AI. Details: [`docs/reviews/milestone5_event_authoring.md`](docs/reviews/milestone5_event_authoring.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Import and assign sprites, preview, size, mirror | **Done** | Look tab: Import PNG... (copied into `assets/sprites`) and a project picture browser. No origin setting exists in the runtime. |
| Configure the Animator visually, preview without playing | **Done** | Animation tab: 4-direction walking from a sheet (Left can mirror Right); clips with row, frames, speed and mirror; live preview. Tested with generated art and with Ezekiel's own 6×8 sheet. |
| Dialogue editor | **Done** | Dialogue tab: lines, speakers, flow, choices that need, set or clear flags and count up, openings chosen by flags, a conversation tester. Saves the runtime's own graph. |
| Flags and conditions without JSON | **Done** | Conditions tab: Show when, Can be talked to when, Looks different when, each with a Pick list of the project's flags. A Flags panel; flags while playing. |
| Colliders and trigger zones, visually | **Done** | Collision tab: whole picture / footprint / circle with drag handles; trigger zones drawn in orange, sized by dragging, which can start a conversation and set flags. |
| A coherent inspector | **Done** | One tabbed, scrolling inspector (`engine/studio_inspector.py`), shared field and flag helpers. |
| Save / Discard / Cancel on close | **Done** | Replaces the close-twice behaviour. |
| One mutation system | **Done** | Every control goes through new `project_ops` operations: validated, undoable, schema-checked. |
| The defining acceptance test | **Done** | `tooling/acceptance_event_authoring.py`: **17/17**, real window, no scripts or API calls. |

### How it was validated

- **Real window:** `tooling/acceptance_event_authoring.py` 17/17. Authoring, save, close, reopen, play-through, quick-save/load and stop, all by mouse and keyboard.
- **Regression:**
  - Milestone 1 15/15, Milestone 2 23/23, Milestone 3 15/15, Milestone 4 20/20. Two of these tests needed small updates for the tabbed inspector and a redraw race.
  - The Ezekiel cemetery playtest 13/13, on a copy.
- **Headless:** `tests/test_project_ops_authoring.py`, and tests for every runtime fix (see the review doc).
- **Full suite:** the 9 baseline failures, nothing new. The ruff gate and mypy island are clean.

### Bugs found and fixed while building it

1. **Draw order was inverted.** It sorted by y ascending in arcade's y-up world, so whatever stood further back was drawn in front: the dug grave over Ezekiel's head. It now sorts by where each sprite stands.
2. **The interact prompt spilled off-screen** for long names.
3. **Hidden objects kept blocking.** ConditionalActivator read solidity too early.
4. **Trigger zones could never fire.** Sprites never got `mesh_tags` and `mesh_id`.
5. **Tall objects blocked with their whole picture.** Fixed with a box footprint collider.
6. **Editor (found by the GUI test):**
   - the play-mode layout dump listed hidden editor buttons;
   - previews were drawn for rows scrolled out of view;
   - "Show when" objects were invisible while editing.

## Milestone 6 — unified human and AI editing

**Goal:** edit a game in Mesh Studio while an external AI modifies the same project through Mesh's authoring interface, review its changes, undo them and keep working without losing anything. Details: [`docs/reviews/milestone6_unified_authoring.md`](docs/reviews/milestone6_unified_authoring.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Animation survives picture changes | **Done** | Kept, carried over to a same-layout sheet, or flagged with Use this picture / Reset animation (undoable). Real window 6/6. |
| One authoritative operation layer | **Done** for Studio, the new MCP tools, `mesh author` and the everyday `apply_ops` operations | `engine/authoring.py` over `project_ops`, with an operation list generated from it. Legacy CLI scene commands and the remaining `AIOps` operations are listed for the next slice. |
| AI changes while Studio is open | **Done** | Proposals with a review panel, accept and reject, one undo step, rebasing onto the person's edits, conflicts reported. Files are never written behind Studio. |
| Provider-independent | **Done** | Plain MCP tools and a JSON CLI; nothing names a model or vendor. |
| Required integration test | **Done** | `tooling/acceptance_ai_coauthoring.py`: **14/14** with the real MCP server and the MCP client library. |

### How it was validated

- **Integration:** `tooling/acceptance_ai_coauthoring.py` 14/14.
- **Earlier milestones' acceptance:** M1 15/15, M2 23/23, M3 15/15, M4 20/20, M5 17/17.
- **Headless:** `tests/test_authoring.py`, `tests/test_authoring_session.py` (a real loopback bridge), plus every MCP, AIOps and live-bridge test, now run with the real `mcp` SDK.
- **Full suite:** the 9 baseline failures, nothing new.

### Bugs found and fixed while building it

1. **The MCP server didn't start on `mcp` 2.x,** which is what a fresh `pip install -e .[mcp]` installs.
2. **`live_add_entity_from_prefab` reported success** for changes that couldn't apply.
3. **A replaced or removed picture silently dropped an object's animation** (the My Game1 report).

## Milestone 7 — capability preservation and consolidation

**Goal:** know what Mesh can actually do, verify it in the running engine, find duplicated or broken implementations, and make Mesh leaner without making it less capable. Reports:
- [`docs/reviews/milestone7_capability_inventory.md`](docs/reviews/milestone7_capability_inventory.md)
- [`docs/reviews/milestone7_capability_lab.md`](docs/reviews/milestone7_capability_lab.md)
- [`docs/reviews/milestone7_consolidation_plan.md`](docs/reviews/milestone7_consolidation_plan.md)

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Capability inventory, classified, verified findings separate from code-read ones | **Done** | Inventory report; sections A–F, other subsystems, 2.5D |
| Overlap investigation (events, quests, animation, saves, editor imports, input, project ops) | **Done** | Consolidation plan, section 1 |
| Verification harness in the real window | **Done** | `tooling/capability_lab.py`: **16/17**. The remaining failure is a confirmed defect (`background_planes` rejected by the schema), documented, not patched. |
| Studio integration per capability and a prioritised gap list | **Done** | Inventory "Studio" column; plan section 4 (lighting and HD-2D first) |
| Only small, evidence-backed consolidation | **Done** | Eight engine bugs fixed at their source with regression tests; the outline model moved out of `engine/editor/`; nothing deleted |
| 2.5D height investigated | **Done** | Not implemented anywhere (inventory, last section) |

### How it was validated

- **Lab:** the first run passed 7/17; after the fixes, 16/17 (measurements and screenshots in `docs/reviews/milestone7_lab/`).
- **Earlier milestones' acceptance:** M1 15/15, M2 23/23, M3 15/15, M4 20/20, M5 17/17, M6 14/14.
- **Full suite:** the 9 baseline failures, nothing new. The ruff gate and mypy island are clean.

### Bugs found and fixed while building it

Every one sat behind green unit tests.

1. Light glow ignored the camera.
2. Object lights were never removed, and leaked into later rooms.
3. A room's darkness carried into the next room.
4. Day/night overwrote the project's ambient light while switched off.
5. SequencePlayer `move_to` (and Patrol, FollowTarget) moved their speed per frame.
6. Batching broke y-sort.
7. Sprite shadows were hidden under their sprites.
8. Projectiles moved 300 px per frame.

## Milestone 8 — runtime reliability and persistent game state

**Goal:** make the existing engine dependable before expanding it. Details and evidence: [`docs/reviews/milestone8_runtime_reliability.md`](docs/reviews/milestone8_runtime_reliability.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| A trustworthy regression baseline | **Done** | Full suite at `da2616b`: exactly the 9 baseline failures. The baseline gate's two failures were investigated: a lost OS mouse press (rerun 15/15) and a lab sampling flaw (fixed in the harness). |
| The capability lab as a repeatable gate | **Done** | `py -3.13 tooling/runtime_gate.py`: all eight real-window suites, one reused output folder, one retry with FLAKY reporting, KNOWN for documented defects. About 45 minutes; not in the quick cycle. |
| Persistence across rooms, saves and a restart | **Done** | `tooling/acceptance_persistence.py`: 4/12 at first, 12/12 now, including closing and relaunching Mesh Studio before loading |
| Newly confirmed runtime defects fixed and regression-tested | **Done** | 9 defects confirmed in the window and 1 found in the code, all fixed, each with a unit test that fails without it. The lab: 27/27 plus 1 KNOWN. |
| Consolidation only where it improves reliability | **Partly** | QuestHook on the live event path; F6 loads the SaveManager quick save. `background_planes` and the quick snapshot are deferred, with the evidence why. |

### How it was validated

- **Full suite, final:** 9 failed, 9,365 passed, 8 skipped (`py -3.13 -m pytest -q -p no:cacheprovider` at the Milestone 8 head): exactly the 9 baseline failures.
- **Runtime gate, final:** 8/8 suites, no retries: M1 15/15, M2 23/23, M3 15/15, M4 20/20 (with `./mygame` copied as the older project, original checked unchanged), M5 17/17, M6 14/14, persistence 12/12, capability lab 27/27 plus 1 KNOWN.
- **Ruff gate and mypy island:** clean.

### Bugs found and fixed while building it

Each was confirmed in the real window except 4, which was read in the code and fixed because room memory needs the real room. Every one sat behind green unit tests.

1. Door arrival spots off the map.
2. Collected or defeated objects came back after leaving a room, or after loading a save.
3. A loaded save's object states went to the room being left.
4. Saves made after a load recorded the save file as their room.
5. Hard shadows ignored camera zoom.
6. Day/night never ran in Studio rooms, which name a background colour (that also skipped `initial_spawn`).
7. A room couldn't switch lighting off.
8. EnemyAI chased at 9 px/s for a speed of 100.
9. NPC schedules never moved anyone.
10. QuestHook heard no events in play.

## Milestone 9 — test trustworthiness and repository health

**Goal:** know whether the test suite can be trusted and where the repository carries needless complexity. An audit, not features. Reports:
- [`docs/reviews/milestone9_test_audit.md`](docs/reviews/milestone9_test_audit.md)
- [`docs/reviews/milestone9_repo_health.md`](docs/reviews/milestone9_repo_health.md)

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| The nine baseline failures diagnosed and resolved | **Done** | Six were one test leaving modules swapped for later tests; two read the owner's own RPG Maker project; one asserted a design changed in June. All fixed at the defect; no assertion weakened. |
| Skips and deselections explained | **Done** | 8 skips (opt-in GL, CI-only packaging, a missing sibling project, an empty table). 163 deselected `slow`/`e2e`: nobody ran them locally and CI's full job was red. **49 failed, identically on the pre-redesign tag**; 18 repaired; 31 remain, all explained (type debt, stale pipeline snapshots, wheel packaging). |
| Test inventory, duplicates, coverage gaps | **Done** | By subsystem and purpose; duplicates judged by what they assert; 16 removed with coverage kept |
| Repository health | **Done** | Size and composition; dead code (5 modules and 1 script removed, each with zero references); coupling; process defects in the gates |
| Test gates recommended | **Done** | Fast (`-m fast`), full headless (default run **plus** the slow/e2e run against a named known-failure list), graphical (`tooling/runtime_gate.py`) |

### How it was validated

- **Full suite, final:** 9,360 passed, **0 failed**, 8 skipped (all explained), 163 deselected (`py -3.13 -m pytest -q -p no:cacheprovider`)
- **Slow/e2e (deselected by default):** 31 failed, 132 passed (`-o addopts= -m "slow or e2e"`): 30 `verify-all` pipeline tests blocked by the type debt (7 of them also stale snapshots) and the wheel test. All named in the test audit; at the start it was 49 failed, the same 49 as on the pre-redesign tag.
- **Runtime gate:** 8/8 suites: M1 15/15 (**FLAKY**: its first attempt lost a click when the OS put the cursor on the primary monitor about 3 s after the window opened; it passed on the retry), M2 23/23, M3 15/15, M4 20/20 (`./mygame` copied, original checked unchanged), M5 17/17, M6 14/14, persistence 12/12, lab 27/27 plus 1 KNOWN.
- **Ruff gate and mypy island:** clean. **The project-wide type gate:** 516 errors beyond its baseline, real debt measured and *not* re-baselined. Its own growth guard refused that, rightly.

### Problems found in the testing process itself

1. **The type gate could never run** in a checkout holding a game project (the untracked `mygame/` has its own `main.py`), so 516 type errors accumulated unseen. Fixed: it excludes untracked folders.
2. **CI's full-suite job ran with `--maxfail=1` and had been red for months**, so 49 slow/e2e failures were never seen.
3. **Tests swapped `sys.modules` entries and never put them back**, which made results depend on order.
4. **Three bare `except: pass` blocks** (Creator Mode, July) broke the project's own swallow policy.

## Milestone 10 — Studio lighting, animation verification, targeted cleanup

**Goal:** light a game in Mesh Studio through its own controls; check both animation systems in the real window; fix the GUI driver's recurring flake; pay down the Studio inspector's type debt; reclaim the 15 GB broken web build. Report: [`docs/reviews/milestone10_lighting_animation.md`](docs/reviews/milestone10_lighting_animation.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Reclaim the broken web build | **Done** | `build/web/` deleted (owner-authorised): **15.26 GB** freed, measured |
| Beginner lighting in Studio: room on/off, room light, place / select / move / resize / recolour / duplicate / delete lights, flicker, preview, undo/redo, save/reopen | **Done** | **Lighting** panel and map handles; the edit view shows the game's own lighting; real-window acceptance 15/15 |
| Advanced: exact values, flicker parameters, shadows | **Done** | **More settings**; shadows on/off per room; `LightSource` lights untouched |
| Occluders | **Partial** | Walls painted on the map cast shadows (fixed: they never did for Studio maps). Rectangle occluders not added: a room's own occluder list replaces its wall shadows, so it would silently switch walls off. Polygon occluders stay in the legacy editor |
| No second lighting implementation; old projects compatible; room and project settings don't override each other | **Done** | Scene keys the engine already reads, plus `lighting_ambient_color` (falls back to the project's); old light keys kept |
| Animation playback verified in the real window | **Done** | Lab **Animate** room, 9/9; no defect found, nothing merged |
| GUI driver cursor flake | **Done** | Verified after each move and before each press |
| Inspector typing | **Done** | Inspector ~263 → 16; project-wide 516 → 272 beyond the unchanged baseline |

### How it was validated

- **Runtime gate:** 9/9 suites, lighting 15/15 and lab 36/36 (+1 KNOWN). Milestone 1 FLAKY once: something outside Mesh confined the cursor; the driver refused to click; the retry passed.
- **Full suite:** 9,373 passed, 1 failed: a determinism test reading the live git hash; pinned, its file passes.
- **Slow/e2e:** 31 failed, the Milestone 9 known list.
- **Ruff gate and mypy island:** clean. **Type gate:** 272 beyond the baseline (was 516).

### Engine defects found by the real-window runs

1. Walls painted in Studio never cast shadows (the occluder builder read only Tiled map files).
2. A wall reaching past a light's radius shaded the floor in front of it (corners were projected back onto the radius).
3. A room couldn't be made lighter than the project's near-black ambient (it could only tint it).
4. The Studio edit view ignored lighting.
5. Dragging a light crashed Studio.

## Milestone 11 — first-time creator experience and Studio usability

**Goal:** someone new to Mesh builds a small game in Studio (a character, connected rooms, behaviours, saving) without
JSON or hidden knowledge. It fixes what the Hollowmere trial found. Report:
[`docs/reviews/milestone11_creator_experience.md`](docs/reviews/milestone11_creator_experience.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| One player for the whole game; rooms keep only where it starts; changes reach every room; new rooms inherit | **Done** | The player is the project's `player` prefab; rooms hold `prefab_id`; acceptance steps 3, 5, 6, 20 |
| Old projects migrated deliberately, differences reported, saves kept | **Done** | Hollowmere copies: identical players shared on open; differing ones listed in a Players panel; the old quick save loads |
| Feet colliders by default (whole picture and circle still available) | **Done** | `{"kind": "box", "auto": true}`; a one-tile gap walked through (step 13) |
| Behaviours in plain language, grouped, internal ones under Advanced, readable settings, problems explained | **Done** | `engine/behaviour_guide.py`; registry and stored data unchanged |
| Patrol routes edited on the map, checked against walls and A*, undoable, saved | **Done** | `engine/route_check.py`; steps 9-11 (a point in a wall warned, dragged clear, the NPC patrols) |
| Game menu in play-tests: save, load, exit; honest feedback | **Done** | Esc or **Menu (Esc)**; "Game saved"/"Game loaded" only after success; steps 14-18, 21 |
| Original starter art with provenance | **Done** | `tooling/make_starter_art.py`, `docs/starter_art.md` |
| Targeted fixes from the trial (dialogue lines, arrival/door tabs, door bounds, focus, warnings, Only once) | **Done** | See the report's P6 table |
| Real-window acceptance from `Mesh Engine.bat` | **Done** | `tooling/acceptance_creator.py` 21/21; in the runtime gate as `creator` |

### How it was validated

- **Runtime gate (`tooling/runtime_gate.py`):** all 10 suites pass: creator 21/21, first workflow 15/15, map building 23/23, map tools 15/15, launcher 20/20, event authoring 17/17, AI co-authoring 14/14, persistence 12/12, lighting 15/15, capability lab 36/36. The full run (engine at `698aa64`) passed 5 of 10. The other five failed on expectations this milestone changed on purpose: the picker's plain names ("Has health", "Talk"), "+ Line" becoming "+ Next line"/"+ Separate line", the feet collider letting the player stand closer to walls, the player living in `prefabs.json`, and an older project now asking to save after its players are shared on open. Only those scripts changed (`7a58796`); each suite was then rerun alone and passes. No engine code changed after the full run.
- **Full suite:** 9,403 passed and 1 failed: the exception-policy ratchet, which the acceptance script pushed over;
  narrowed, and its file passes.
- **Slow/e2e:** 31 failed, 132 passed: the Milestone 9 known list.
- **Gates:** ruff gate and mypy island clean. Type gate 258 beyond the baseline (264 before this milestone).

### Engine defects found on the way

1. Toasts never showed in Studio games: the HUD drew them after the health bar and gave up when the player had no
   health stats.
2. Arcade keeps a sprite's hit box when its texture changes. A character made from a whole sheet kept the sheet's
   box, so shadows and depth sorting sat far below its feet (the Animator never resynced it).
3. NPCs moved by Patrol never walked or turned: the Animator only read velocity.
4. A content-isolation test still read the pre-shared-player room (missed in Stage A, caught by the full suite).

## Milestone 12 — shadows that belong to their light

**Goal:** a shadow blocks the light that casts it and nothing else. It doesn't darken the room light, doesn't
touch other lamps, and isn't black painted over the scene. Report:
[`docs/reviews/milestone12_shadow_quality.md`](docs/reviews/milestone12_shadow_quality.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Baseline and an architecture decision | **Done** | Report, Stage A: the overlay painted black at alpha 180 from one chosen light; the composite path was unreachable, with a single global mask |
| Correct compositing (ambient kept, only the casting light blocked, no darkening without lights, shadows-off unchanged) | **Done** | `light_compositor.py`; GPU pixel tests (examples A–D exact); lab checks 2, 3, 19 |
| Many shadow-casting lights, independent | **Done** | Per-light masks; budget 16 a frame, over budget lit without shadows and reported; lab checks 4–8, 15 |
| Geometry: corners, diagonals, short blocks, past the reach, lamps near walls, moving | **Done** | `light_shadow_polygons`; ray-test pixel checks, 0 wrong in 10 scenes and 6 moving steps; lab checks 8, 10–12 |
| Soft edges, optional, ambient intact | **Done** | Sharp / Soft / Softer (the lamp as a disc); a real penumbra; joined tiles = one wall |
| Studio controls through canonical ops | **Done** | Shadow edges presets; per-light On and Casts shadows; `set_room_lighting(softness=)`, `set_light(shadows=)` |
| Performance measured, honest fallback | **Done** | Bench and real-window profile; no GPU: lit without shadows, `shadows_unavailable` |
| Real-window lab, 20 items | **Done** | `tooling/shadow_lab.py` 14/14 (legacy overlay 6/13); in the runtime gate |

### How it was validated

- **Runtime gate:** one combined run, no retries: **11/11 suites** (shadow lab 14/14, creator 21/21, lighting 15/15, capability lab 36/36, and the rest as before).
- **Full suite:** 9,400 passed and 4 failed on the first run: import policy (3) and the type-ignore ratchet. Fixed.
- **Slow/e2e:** 34 failed: the known 31, plus 3 that pinned the old overlay as the hard-shadow path. Those now
  select it explicitly and pass, so the known 31 stay.
- **Gates:** ruff and the mypy island clean; type gate 259, unchanged.

### Defects found on the way

1. A room without its own shadows setting kept the previous room's (state leaking between rooms).
2. Polygon occluders' straight-ended shadows left a lit wedge behind long edges.
3. Rectangle shadows started at the chord between the outermost corners, darkening part of the wall itself.

## Milestone 12.1 — character shadows, natural flicker, lighting customisation

**Goal:** characters cast shadows from the lamps around them; lights flicker like flames instead of pulsing; shadows
can be tuned without losing the simple presets. Report:
[`docs/reviews/milestone12_1_lighting_polish.md`](docs/reviews/milestone12_1_lighting_polish.md).

### Acceptance criteria and status

| Criterion | Status | Evidence |
|---|---|---|
| Players and NPCs cast directional shadows from nearby lamps (feet, away from the light, length with distance, softer with distance, the light's colour and ambient respected, none when a lamp is off or doesn't cast) | **Done** | Through the M12 per-light masks (no overlay); GPU tests 8/8; lab items 1-4, 7 |
| Contact shadows kept, separately controllable; per-character settings (cast on/off, height, strength, length) | **Done** | Look tab "Under feet" / "From lamps" + fine-tune; `set_shadows`; lab items 5, 6 |
| Natural flicker presets (Steady, Candle, Torch, Fire, Faulty lamp, Custom), no pulsing, reproducible, frame-rate independent, independent neighbours | **Done** | `flicker_sample`; `tests/test_natural_flicker.py` 14; lab items 10-16, every sample against the formula |
| Torch then adjust; custom shown as Custom; flicker off restores the base; Studio = Play; reduced-flicker setting; no aggressive flashing | **Done** | Lab items 15, 17, 18; "Calmer Flickering"; a faulty lamp at most 3 smooth dips a second |
| Shadow customisation: Sharp / Soft / Softer kept, collapsed fine-tune (edge, strength by occlusion, quality, characters on/off) | **Done** | `set_room_lighting(edge=, shadow_strength=, quality=, character_shadows=)`; lab items 8, 9 |
| Performance measured; budget kept; diagnostics | **Done** | Bench: 6 characters +0.06 ms CPU; real window in lab item 22; stats `characters`, `character_shadows`, `character_feet` |
| Real-window Lighting Polish Lab, 22 items, time series, GPU pixel tests, subjective inspection | **Done** | `tooling/lighting_polish_lab.py` (in the runtime gate) |

### How it was validated

- **Headless:** 9,423 passed; slow/e2e the known 31; ruff clean; type gate 259 (unchanged).
- **Runtime gate:** final combined run 10/10 suites through shadow_lab. The run was stopped before the last two to free
  the owner's computer; those passed on the same code (Lighting Polish Lab 18/18, capability lab 36/36).
- **The first combined run (8/12)** failed on input lost while the PC was in use; those suites passed alone.
- **Subjective inspection** of every lab screenshot and the flicker plots (report, Stage E).

### Defects found on the way

1. **Flicker's brightness never reached the screen.** Arcade's `Light` keeps its colour private and the code wrote a
   public attribute that doesn't exist; only the reach ever moved.
2. **The old flicker peaked only on its beat**, which owners saw as pulsing.
3. **Five new type-gate errors.** The first two 12.1 commits brought four, and a fifth turned up while flicker went in.
   All five are fixed, and the gate is back to 259.

## Milestone 12.2 — visual consistency, transitions, shadow verification

**Goal:** a game looks finished, not like a set of editor objects. Report:
[`docs/reviews/milestone12_2_visual_consistency.md`](docs/reviews/milestone12_2_visual_consistency.md).
From this milestone on, no test drives the owner's mouse or keyboard without permission. Verification is headless
plus hidden-window renders of the real game and Studio.

| Criterion | Status | Evidence |
|---|---|---|
| Doors: one SceneTransition, shown as Door / Invisible passage / Map artwork; picture hideable; area, walk-in and press-E | **Done** | `set_door`; Look tab "How it shows"; `tests/test_door_presentation.py`; hidden-window check 10/10 |
| No round shadow under doors, passages, arrival spots, hidden pictures; characters keep theirs | **Done** | `ground_shadow_default`; check: door drawn without blob, passages not drawn |
| Round objects: angular shadows? | **Real, fixed** | See-through wall tiles cast their outline; water none (`a3_rock.png`) |
| Corner joints: partial wedges? | **Real, fixed (two causes)** | An L of tiles shadowed its own face; Softer lamps by a wall leaked light (2,506/5,101 px wrong, now 1). `tests/test_shadow_corners_gpu.py` |
| Editor-only symbols absent in play | **Done** | Passage areas identical to the room without them; outlines only in Studio |

**Deferred: needs someone at the screen.** A live walk through a passage, dragging and typing in the door panel, and
the real-window suites touched by these changes:

```
py -3.13 tooling/runtime_gate.py --only shadow_lab lighting_polish_lab lighting creator
```

## Milestone 13 — repository health and consolidation

Report: [`docs/reviews/milestone13_repository_consolidation.md`](docs/reviews/milestone13_repository_consolidation.md).

- **One implementation for common edits.** Lights, object removal and behaviour settings run through `project_ops`
  for Studio, the authoring API, MCP and the in-game console's AI jobs. Objects are resolved by one function, and the
  same request gets the same result and the same refusal everywhere.
- **Type debt: 259 errors beyond the baseline down to 0.** The type gate passes, and with it the 30 `verify-all`
  tests it blocked.
- **Verification.**
  - Slow/e2e failures dropped from 31 to the wheel test (an owner decision); default suite 9,435 passed, 0 failed.
  - Test windows are always hidden.
  - An intermittent "No window is active" failure was traced to arcade forgetting the active window when another
    closes, and fixed in `GameWindow.close`.
  - The swallow-scan step honours `--artifacts`.
  - New `gpu` test tier; tiers no longer depend on a writable pytest cache.
  - The real-window gate needs `--owner-present`.
- **Dead code.** The unreachable hard-shadow composite path and its backend (`shadow_pipeline.py` 787 → 237 lines),
  8 test files that tested only it, and the unread repo-root `projects.json` are gone.
- **Owner decisions.** Pip-installed Mesh (the wheel test), and the "Soft Shadows" pause-menu toggle, which has done
  nothing since M12.
  - **Decided by the owner, 2026-10-24.** Both are housekeeping, kept separate from the UI redesign:
    - **Pip install:** support pip-installed Mesh by putting the redistributable packs it needs in the wheel. First
      check their licences and the wheel's size.
    - **Pause menu:** remove the obsolete "Soft Shadows" toggle. Older saved settings that still contain it must
      keep loading.

## Milestone 14 — visual polish and creator acceptance

Report: [`docs/reviews/milestone14_visual_polish.md`](docs/reviews/milestone14_visual_polish.md). Hidden-window
evidence only; human acceptance is pending (the report lists the checks).

| Criterion | Status | Evidence |
|---|---|---|
| M12.2 fixes hold (round tiles, L joints with two lamps, Softer leaks, doors) | **Confirmed** | `milestone14_evidence/`; polish check 10/10 |
| Soft character shadows streaked | **Real, fixed** | One shadow at Soft/Softer; GPU test; bench unchanged |
| Contact shadow fits the footprint | **Done** | Sized from the picture's bottom rows; characters keep 24×8 |
| Three door styles: same destination, activation, undo, save/load, AI authoring | **Verified headless** | `tests/test_door_styles_integration.py`; live input pending |
| Studio labels clipped at the map edge / split mid-word | **Real, fixed** | Kept in view; pyglet wrap bug bypassed (`studio.hard_wrap`) |

## Known limitations (honest list)

- **Starter art is simple:** a hero, a villager and a sign of Mesh's own (Milestone 11). The tileset still has no roof or door tiles.
- **No counter conditions.** Choices count up, but nothing can require "graves_dug ≥ 3"; flags gate everything.
- **Event sequences beyond conversations** (wait, move, signal) run in `SequencePlayer`, which works since Milestone 7. Studio can't edit its steps yet (JSON only). `ActionListRunner` does nothing in the live game (see the Milestone 7 inventory).
- **Lighting** has a Studio panel since Milestone 10 (room light, point lights, flicker, shadows from walls); since Milestone 12 every lamp casts its own shadow (up to 16 a frame), with Sharp / Soft / Softer edges; since 12.1 players and NPCs cast shadows from lamps and lights flicker by preset (Candle, Torch, Fire, Faulty lamp, Custom). Still JSON or the legacy editor: cookies, shafts, rectangle/polygon occluders, day/night. **Parallax, camera zoom and the HD-2D look** work in the engine (Milestone 7 lab) but have no Studio controls yet.
- **Long inspector sections scroll** with the mouse wheel; there's no scrollbar to drag.
- **Map tools are still basic.**
  - Three layers.
  - No autotiles, tile flipping, or copying a region of the map.
  - Imported tilesets must be a plain grid (no spacing or margins).
  - Importing can't be undone (it writes files; an unused tileset is harmless).
- **Text fields are single-line.** Pasted line breaks become spaces.
- **Middle-drag is the only way to pan with the mouse.** Laptop users can pan with WASD or arrows while no text field has focus.
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

0. ~~Pay down the type debt~~ **Done in Milestone 13** (0 beyond the baseline; `verify-all` runs green apart from the wheel decision). Keep the full headless gate (default run plus slow/e2e, both desktop-safe now) routine.
0. **Studio lighting controls** on the now-verified runtime (lights, occluders, room ambient and lighting on/off), then the HD-2D look and camera zoom areas. Keep running `tooling/runtime_gate.py` at the end of each milestone. Deferred from Milestone 8: `background_planes` → `background_layers` (needs a visual-equivalence test), quick snapshots into SaveManager slots (monster companion state), a respawn option for defeated enemies, and the templates' CameraFollow `zoom: 1.0` that overrides a room's own zoom.
1. **Finish the single operation path:** route the legacy CLI scene commands that target Studio projects through `engine/authoring`, then retire their duplicate code; move the remaining `AIOps` operations (lights, quests, world links) onto `project_ops` operations.
2. **Launcher follow-ups:** return to the launcher when the Studio closes; rename, move or delete projects; a packaged build.
3. **Monster code as a plugin** via `PluginManager`; project-scoped `behaviours/` folder for custom scripts.
4. **Archive the legacy editor and Creator Mode** only once the Studio covers what it still lacks. The inventory is in `docs/reviews/milestone3_map_tools.md`; dialogue, list/object settings and triggers on the map are now done (Milestone 5). Still missing:
   - quest, item and prefab editors;
   - counter conditions;
   - event sequences.

   Then archive the demo content and its ~62 tests.

## Decisions needing the owner

- **Starter art:** Milestone 11 generated a hero, a villager and a sign (`docs/starter_art.md`). Replace them with commissioned art if wanted: same sheet layout, rerun the template previews.
- **Door style:** doors are walk-in (touch to enter), the RPG Maker convention. Press-E doors exist as a behaviour setting (`allow_interact`). Is walk-in the right default?
- **Engine-repo showcase:** keep it, and with it the legacy editor, or archive it with the demo content?
