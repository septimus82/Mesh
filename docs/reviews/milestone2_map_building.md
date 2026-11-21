# Milestone 2 — visual map building: test results and implementation notes

Branch `redesign/visual-editor`. Summary and status table: [`MESH_REBUILD.md`](../../MESH_REBUILD.md).

## Graphical acceptance test

`py -3.13 tooling/acceptance_map_building.py [--out DIR]`, run from the repo root on Windows.

What it does:
- Creates a fresh project with `mesh new village`.
- Opens it with `mesh edit` and drives the real window with OS-level mouse and keyboard input (`tooling/gui_driver.py`: SendInput, guarded so that input only goes to the game window).
- The Studio's opt-in layout dump (`MESH_STUDIO_LAYOUT`) is read only to find things and check state. Nothing is done through internal APIs.
- Saved files are checked on disk and against the scene schema.

**Final run on the committed code: 23/23 passed.** That is the owner's 17 steps plus 6 interaction checks. The full report is [`milestone2_screens/report.json`](milestone2_screens/report.json).

| # | Step | What was checked | Result |
|---|---|---|---|
| 1 | Open Mesh Studio | Fresh project opens in the Studio | Pass |
| 2 | Open the starting map | 24×16, 32 px, all grass | Pass |
| 3 | Paint a floor | 6 dragged rows of wood floor, every interior cell checked | Pass |
| 4 | Walls and obstacles | 4 dragged stone-wall sides, a rock; every wall cell checked | Pass |
| 5 | Erase and repaint | Eraser stroke opens 5 bottom-wall cells; 2 repainted, leaving a 3-cell entrance | Pass |
| 6 | Undo/redo a stroke | A 6-cell flower stroke: Ctrl+Z removes all 6 at once, Ctrl+Y restores all 6 | Pass |
| 7 | Place an NPC | Person placed inside the room, renamed "Elder" | Pass |
| 8 | Dialogue behaviour | Dialogue removed, re-added via right-click → Add behaviour…, line set | Pass |
| 9 | Second room | "+ New room" "Cabin" opens at once: 20×15, wood floor, stone border | Pass |
| 10 | Different layout | Carpet, water and trees painted | Pass |
| 11 | Connect with a door | Right-click inside the room → "Add door to Cabin" | Pass |
| 12 | Save | Ctrl+S, nothing left unsaved | Pass |
| 13 | Close and reopen | Process closed, Studio relaunched | Pass |
| 14 | Persisted | Tile layers identical cell by cell; Elder, its line and the door present; both rooms valid against `scene.schema.json`; Cabin tiles intact | Pass |
| 15 | Play both rooms | Walked through the entrance into the door; arrived in the Cabin at its arrival spot (256, 128) and stayed; walked back through the Cabin's door | Pass |
| 16 | Walls block, doors work | Holding A: stopped at x=160, flush with the left wall (inner edge 128 + half the 64 px player). Holding W: stopped at y=384, flush with the top wall | Pass |
| 17 | Stop | F4: back in the editor, not dirty, tiles unchanged | Pass |
| x1 | Drag an object | Guide dragged 112 px; no tile changed; Ctrl+Z moves it back | Pass |
| x2 | Paint over an object | Stroke starting on the Elder paints; Elder neither moved nor selected | Pass |
| x3 | Typing vs. shortcuts | Typed " wasd", then Delete, Ctrl+Z, Ctrl+S and F4 in the name field: the view didn't pan, nothing was deleted, saved or played, and the rename applied | Pass |
| x4 | Zoom and pan, then paint | 3 wheel notches zoom in; middle-drag pans; the clicked cell is the one painted | Pass |
| x5 | Right-click with a brush | Opens the map menu, paints nothing; Esc closes it and returns to Select | Pass |
| x6 | Switching rooms | Unsaved paint in the Cabin survives Cabin → Start → Cabin | Pass |

Screenshots from the final run:
- [Walls and obstacles](milestone2_screens/04_walls_and_obstacles.png)
- [Undo/redo of a stroke](milestone2_screens/06_undo_redo_stroke.png)
- [The second room](milestone2_screens/10_paint_second_room.png)
- [After reopening](milestone2_screens/14_persisted.png)
- [Playing, back from the Cabin](milestone2_screens/15_play_both_rooms.png)
- [Stopped by the walls](milestone2_screens/16_walls_block.png)
- [Painting while zoomed and panned](milestone2_screens/21_x_zoom_pan_then_paint.png)

### Reliability of the test itself

The test was run 8 times while it was being finished. Every failure was investigated before being dismissed.
- **Test races:** fixed in the test, not the editor.
  - A stroke helper didn't wait for its stroke to apply.
  - One step didn't wait for its own Ctrl+Z.
  - One assertion wrongly expected nothing to be selected.
- **Unexplained, not reproduced:** in two consecutive runs, the first clicks after start-up were ignored.
  - In one of them, three palette clicks over ~9 s did nothing; later clicks all worked.
  - With logging added to the Studio's mouse handler, 4 more probe runs (32 clicks) and 4 more full runs showed no dropped click, so the cause was not found.
  - If a human sees the editor ignore the first clicks after opening, this is the thing to report.

## Other checks

- **Full suite** (`pytest`, 7 min): 9 failed, 9,274 passed, 9 skipped.
  - The 9 are the known baseline: widget overlays ×5, battle-sprite headless probe, RMMZ fixtures ×2, legacy editor selection/nudge.
  - An earlier run on this milestone had a 10th failure, a real bug (below), now fixed.
- `test_entity_paste_respects_snap_to_tile_center` fails only when run in isolation. It fails the same way on the archive tag (order-dependent, pre-existing).
- Ruff gate and mypy island: clean.
- Headless tests added in this milestone:
  - `tests/test_project_ops.py`: 4 map tests (13 in total).
  - `tests/test_studio_project.py`: 4 map tests (8 in total).
  - `tests/test_tilemap_tileset_slicing.py`: 3.

## Bugs found and fixed

1. **External JSON tilesets never loaded.** The image path was resolved next to a folder named after the `.json` file (`caf8e1d`).
2. **Multi-row tilesets were upside down.** The crop used a bottom-up y on a top-down image (`caf8e1d`). Any Tiled map whose tileset is taller than one row was affected, not only the Studio's.
3. **Windows-style room paths broke map paths** (`5286115`).
4. **Doors into a new room arrived inside its border wall.** Far-side door and arrival positions now sit inside the room (`5286115`).
5. **The legacy editor and Creator Mode saved invalid scenes for painted rooms** (`005fad4`). `build_scene_snapshot` added `overrides` and an empty `layers` list to inline `tile_layers` tilemaps, which the schema forbids. Found by the full suite (`test_creator_mode_add_person`), since the starter room now ships with a map.
6. **Obstacle tiles carried a grass background** (`7e71982`).

## Implementation notes

- **No new map format.**
  - Painted tiles live in the scene's inline `tilemap.tile_layers`, which the runtime already merges over the map file by layer name.
  - The map file next to the room (`packs/<pack>/maps/<room>.json`) is a plain Tiled JSON skeleton: size, tileset reference, empty `ground` and `walls` layers.
  - The skeleton is written as soon as the map exists, so unsaved rooms load in the Studio and in play-tests; the scene document stays the single source of the tiles.
- **Collision.** `walls` is the map's `collision_layer_id`. Its tiles become the existing tilemap collision sprites. Nothing new was added to movement.
- **Edits.**
  - Every change goes through pure functions in `engine/project_ops.py` (`add_map`, `paint_tiles`, `erase_tiles`, `map_info`, `cell_at`, `cell_center`) and `engine/studio_project.Project`, which snapshots whole documents for undo.
  - A brush stroke collects cells while the mouse is down and is applied as one edit on release.
- **Tileset.**
  - `assets/tilesets/starter.png` and `starter.json`: 16 tiles. Each tile's `layer` and `label` are Tiled tile properties, which drive the palette groups.
  - Regenerate with `tooling/make_starter_tileset.py`.
  - New projects get a copy. Existing projects get one the first time the Studio needs it.
- **Starting maps.**
  - The starter template's room has a 24×16 grass map.
  - New rooms are 20×15 with a wood floor and a stone-wall border.
  - A room with no map shows "Add a map", sized to cover its objects.
- **Clipboard.** Not implemented, for objects or tiles. Text fields have none either (`arcade.gui`). Documented rather than added in this milestone.
