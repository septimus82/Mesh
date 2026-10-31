# Milestone 23A: a responsive editor workspace, and tools you can find

This milestone answers the owner's first hands-on creator test (Woodland Clearing). The editing tools were easy to use once found, but Sculpt, Paint and Scatter were buried at the end of a long left panel that didn't look scrollable. M23A is based on `redesign/visual-editor` at `a370605` (#412). Evidence is in `m23a_evidence/`.

Every picture and number below comes from Mesh Studio in a hidden window, driven by its own input events (`tooling/studio_workspace.py`, phases `shots` and `creator`).

## Stage 1: the workspace as it was

**Fixed dimensions** (`engine/studio.py`):
- A 44 px top bar and a 26 px status bar.
- A **230 px left panel** and a **330 px right panel**, always both shown. The view is whatever is left: `_map_rect` = (230, width − 330).

The view at each window size (`before_shots.json`):

| Window | View (px) | Share of the window | Left panel |
|---|---|---|---|
| 640 × 480 | **80** × 410 | 11% | 19 rows below the window |
| 1280 × 720 | 720 × 650 | 51% | 12 rows below, Sculpt/Paint/Scatter among them |
| 1920 × 1080 | 1360 × 1010 | 66% | fits |
| 2560 × 1440 | 2000 × 1095 | 73% | fits |

The 2560 × 1440 rows are really 2560 × 1165: a hidden window is clamped to the desktop's height, so that is the largest this PC allows.

**The left panel** was one long list: rooms, the 3D view's buttons, Camera and sun..., weather preview, Wind and motion, Models..., Sculpt/Paint/Scatter (with the chosen brush), then every object. M22B made it scroll by mouse wheel and keep scrolled-out rows unclickable, but the only sign of more was a faint "v N more below" line.

**The top bar** (Play, Save, Undo, Redo, Flags, Lighting, Sound, AI, the room's name) fit at 640 px but left no room for anything else.

**Window:** resizable already. Studio rebuilt its panels for a new size since M22B, but it opened at the project's own window size and was never maximised.

**State that must survive:**
- the tool armed (sculpt, paint or scatter, placing an object or light);
- the selection and its inspector, and the right panel's own panel;
- the 2D tile palette's tileset and scroll;
- boxes being typed in (M22B's commit, refusal and focus rules).

**2D rooms:** the Map section (layers, select/eraser, brush/rect/fill, tileset, Resize, palette) lived in the same long left panel. The palette's height came from a guess at how much of the panel was left (2 rows with many rooms or objects).

## Design (the smallest change that answers it)

No new UI framework, no docking, no detachable windows: the existing panels, rows and buttons, rearranged.

1. **Categories.** The left panel starts with five tabs, always in view: **Rooms** (the rooms, New room, the 3D view's buttons), **Terrain** (Sculpt, Paint, Scatter and the chosen brush; in a 2D room the map's tiles and palette), **Objects** (Models..., then every object), **Environment** (Camera and sun..., weather preview, Wind and motion, Lighting..., Rain and weather sounds...) and **Audio** (Room sounds and ambience..., Place a sound). Each category shows only its own tools. The existing controls and operations are reused unchanged: the 3D view's section was split into its four parts (`nav_section`, `environment_section`, `models_button`, `terrain_section`).
2. **Panels shown or hidden.** The top bar gains **Tools**, **Inspector** and **Focus (Tab)**. Tab (outside a text box) hides both panels for the view alone, and brings them back.
3. **Narrow windows.** When both panels would leave the view under 400 px, only one is shown: the one last used. Opening something to inspect, or a right-hand panel, shows the inspector; choosing a category shows the tools. Under 960 px the top bar uses shorter labels and leaves Lighting and Sound to their categories.
4. **A visible scrollbar.** A panel whose rows don't all fit gets a scrollbar at its edge, with the shown part in MeshMind cyan, beside the existing "more above / below" lines.
5. **The whole screen.** Studio opens maximised (`engine/game_launch.py`), still an ordinary window to resize or restore. `MESH_STUDIO_WINDOWED=1` keeps the project's own size. It maximises only a window already on screen, on the first frame of its own loop: a hidden window (every test's) is never shown or grown.
6. **The status bar** runs the window's full width (the panels' bottom strip was empty), so messages have more room.
7. **The 2D palette** fills the Terrain category instead of a guessed share of the whole panel.

Graphite and MeshMind cyan are unchanged: the same colour tokens and button styles.

## After

**The view at each window size** (`after_shots.json`, `after_creator.json`):

| Window | View before | View after | Panels shown |
|---|---|---|---|
| 640 × 480 | 80 × 410 | **410 × 410** | one at a time |
| 1280 × 720 | 720 × 650 | 720 × 650; 950 × 650 with Tools hidden; 1280 × 650 in Focus | both |
| 1920 × 1080 | 1360 × 1010 | 1360 × 1010 (1920 × 1010 in Focus) | both |
| 2560 × 1440 (1165) | 2000 × 1095 | 2000 × 1095 (2560 × 1095 in Focus) | both |

At every size nothing is drawn past the window's edges, and no top-bar button runs past them.

**What a creator does** (`creator` phase; `tests/test_studio_workspace_gpu.py`, 9 GPU tests):
- **Categories:**
  - Terrain shows Sculpt, Paint and Scatter at once, with a line on what each does.
  - Paint shows its materials; Scatter shows its collections and brush, all in view at 1280 × 720.
  - Objects shows Models... and the objects; Scatter stays armed meanwhile.
  - Environment shows Camera and sun..., Lighting... and the wind; Audio shows the room's sounds and Place a sound.
- **The inspector:** an NPC's inspector is kept through Rooms, Terrain and Objects, and when the Inspector is hidden and shown again.
- **Editing:**
  - Ctrl+S in the NPC's focused name box saved "Elder Oak" with the box still focused.
  - Undo gave "Elder", Redo "Elder Oak".
  - Play and Stop: back in edit mode with the NPC still selected.
- **The view:**
  - Tools hidden: 950 px wide. Focus (Tab): the whole 1280 × 650, with no panel and no inspector boxes. Tab again: 720 again.
  - The mouse wheel over either panel left the 3D camera alone.
- **Resizing:** 1280 → 640 → 1920 → 2560 → 1280 with an NPC selected. Usable view at each size; nothing past the window.
- **2D:** in a starter project, the Terrain category's palette picked a tile ("Painting Flowers on the ground").
- **Scrollbar:** the Objects category in a project with 30 extra objects shows a cyan scrollbar and "v 25 more below" (`after_objects_scrollbar_1280x720.png`).

**Pictures:**
- `compare_1280x720.png`: before, Sculpt, Paint and Scatter are hidden below "12 more below"; after, the Terrain category has all three in view.
- `compare_640x480.png`: before, an 80 px view; after, one panel and a 410 px view.
- `creator_scatter_1280x720.png`, `creator_focus_1280x720.png`, `creator_selected_2560x1440.png`, `creator_2d_terrain_1280x720.png`, `before_hd2d_1920x1080.png` / `after_hd2d_1920x1080.png`.

**Looked at by eye:**
- Labels: no clipped or overlapping labels.
- Status line: at 640 px a long status message is cut at the window's edge. It now has the window's full width, but very long messages still don't fit there.
- Empty space: the empty inspector ("Nothing selected") still takes its 330 px at 1280. Hiding it automatically with each selection would move the view about, so it's left to the Inspector button (recorded in the M22 backlog).

## Found on the way

- **M22B's guard and the categories.** M22B made every button wait while a box holds a refused value. That also stopped the category tabs, so with a refused name a person couldn't even switch category. Tabs now commit the boxes and go on; they wait only when showing the tools would hide the inspector (a narrow window). `tests/test_studio_workflow_polish_gpu.py` covers it (another room, reached through the Rooms category, still waits).
- **A test window on the owner's screen.** The first version maximised the window straight after launching Studio. On Windows, maximising a hidden window shows it. One default-suite test (`test_launch_editor_pins_project_without_using_last_root`) launches Studio through that path with a hidden window and no event loop, so a frozen, maximised window appeared on the owner's screen during a run. The run was stopped at once. The fix maximises only a visible window, on the first frame of its own loop. Checked: that test, with `maximize` replaced by a recorder and the clock ticked afterwards, made no call.

## Review corrections (independent review: conditional pass)

Three input-safety cases, reproduced on `371d152` with Studio's own input events, including the keyboard's Tab (`tooling/studio_workspace.py safety`; `m23a_evidence/before_safety.json`, `after_safety.json`). In each, a box held typed, uncommitted text: typed, then left by clicking blank space in its panel, which doesn't commit it.

1. **Tab (Focus).**
   - **Before:** a changed name ("Elder Ash") and a refused one (blank) were both lost. The panels went, and came back showing "Elder".
   - **Now:** Tab waits like F4 and Esc (`_settle_fields`). The valid name is taken first ("Elder Ash", kept when the panels come back). The refused blank keeps its text and the panels, with "A name can't be empty. Correct the box, or click it and press Esc to put back what it was; until then nothing else is done."
2. **Switching category with an invalid brush box.**
   - **Before:** Scatter's radius "big" (refused: "Type a number.") was hidden by switching to Objects. Save, with nothing else changed, was greyed out and said nothing more; the text only came back on returning to Terrain.
   - **Now:** a category switch waits while a box it would hide (one the left panel made) holds a refused value. Terrain stays, with "big" in view and the reason with what to do. A valid radius (3 m) is taken and the switch goes ahead. A refused box in the inspector doesn't stop a switch, since it stays in view.
3. **Resizing.**
   - **Before:** a changed name and a refused one were both lost when the window was resized (the panels are rebuilt for the new size).
   - **Now:** a resize's rebuild keeps what is typed in the boxes, still uncommitted ("Elder Birch" and the blank, in their boxes; the name on record still "Elder").

Regression tests: 5 more in `tests/test_studio_workspace_gpu.py` (Tab with a valid name; Tab with a refused one; a category switch with a refused brush box, then a valid one; a resize with a valid name and with a refused one).

## Tests and gates

- **New:** `tests/test_studio_workspace_gpu.py`, 14 GPU tests (integration) on the creator and safety phases.
- **Updated to find tools by category, as a person would:**
  - `tooling/hd2d_studio_demo.py` (the driver: each category in turn, the Tools button first in a narrow window);
  - `tooling/studio_workflow_polish.py` (the same; a taller test tileset, because the palette now shows 16 rows; the panel's own scrolling checked in the Objects category);
  - `tooling/hd2d_room_studio.py` (unchanged: it uses the driver);
  - `tests/test_weather_collisions_gpu.py` (finds "Preview weather" under Environment).
- **GPU tier, after the review corrections:** 231 passed, 0 failed.
- **Default selection, after the review corrections:** 10,069 passed.
- **Headless Studio, HD-2D and contract tests:** 612 passed.
- **Ruff gate:** ok. **mypy:** 73 (baseline). No timing budget or baseline was changed; the new tests are GPU and integration tests.

## Not changed

- The project format, scenes, game runtime and its visuals, and audio behaviour.
- Every tool's own operations and validation.
- No sunshafts, thunder, snow rendering, rivers or new models. Snow's missing Studio authoring is recorded in the M22 backlog for a later environment milestone.
- The Lakeside Village and Woodland Clearing projects.
