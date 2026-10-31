# Milestone 22A.1: expanding a flat HD-2D room's ground in Mesh Studio

The owner approved this plan on 2026-10-28. It covers only expanding a room's flat, unsculpted, unpainted ground, east and north. These are not part of M22A.1 and need review first:
- sculpted or painted ground;
- growing west or south (which would move everything);
- shrinking.

## Preflight findings

1. **`project_ops.resize_map()`** keeps every existing tile at its world position: rows are added at the top (north) and columns at the right (east). Its new cells are 0, so an expanded HD-2D room's new ground would have had no ground tile. `expand_hd2d_room` fills only the new cells of the `ground` layer, with the one tile along the edge(s) it grows from (see the review corrections below; the first version used the layer's most common tile). The `walls` and `overhead` layers get nothing new. 2D Resize is unchanged and its new tiles stay empty, as a test pins.
2. **The room's tiles and its map file.** A room's map file (`<pack>/maps/<room>.json`) holds the size, the tilesets and empty layers; the tiles live in the room document. At load, the room's own `tilemap.width`/`height` override the file's size (`scene_load_apply` → `tilemap.py`: "the scene's size"). So Play and export already follow the room. Three things still read the file's own size: Tiled, `ai_ops` tile painting and `tooling_runtime.brush_report`. `_write_map_file()` writes the file only when a room is made. So after an expansion, Studio's Save now writes an HD-2D room's map file at the room's size:
   - it's written first, and checked before anything is written;
   - it's resized only if it's Studio's own kind of file (tile layers with nothing drawn in them);
   - a map file with tiles or objects of its own is never resized, and the save is refused with the reason, nothing written (the room stays unsaved);
   - undo and redo need nothing of their own, because the file follows whatever the room is when it's saved.
3. **What stops the player.** Nothing clamps a character to the world size. In an HD-2D room with collision (sculpted ground, or models with colliders, e.g. the starter kit's cottage), `engine.hd2d.World` builds its walkable ground from the ground's extent, and `stand()` gives "nothing to stand on" past it, so the edge of the ground is where the player stops. The camera keeps inside `camera.bounds` (`fit_view`). NPC pathfinding uses the tilemap's size, the room's own. Rain covers the world size. All of these grow together.
4. **Found on the way: Undo after Save.** Undo and redo restored each room's "unsaved" mark as it was when the step was taken. Undoing past a Save therefore left a room that differed from its file marked as saved, and the undone state never reached disk. Save now marks every room it wrote as unsaved in every undo and redo step. The fix is general to Studio's undo (`Project.save`).

## What was built

- **`project_ops.expand_hd2d_room(scene, width_m, depth_m)`:** one operation that grows these together:
  - the ground's `to`;
  - the room's `world_width`/`world_height`;
  - its map (through `resize_map`, with the new ground tiles filled);
  - the camera's `bounds`, where they were the room's edges (bounds set otherwise are kept, and Studio says so; no bounds stay none).

  The south-west corner, and so every object, structure, water, sound, light and scatter instance, stays where it was.

  **It refuses, with the reason:**
  - not an HD-2D room;
  - no HD-2D ground;
  - sculpted or painted ground (heights, paint or chosen edges);
  - ground not starting at 0, 0;
  - ground not whole metres;
  - map size or world size not matching the ground;
  - a size that isn't whole metres from 8 to 256, smaller on either side, or the same.
- **`project_ops.hd2d_room_size(scene)`:** the size, and whether it can be expanded and why not.
- **`Project.save`:** keeps an HD-2D room's map file at the room's size, as above, and fixes undo after Save.
- **Studio:** 3D view → Camera and sun... → **Room size** shows "48 x 52 m (1 m is a tile)".
  - For a room that can grow, it says Expand grows the ground east and north, everything stays where it is, and rooms can't shrink here. Then come **Width x depth (m)** fields and **Expand room**: one undo step, after which the view shows the whole room.
  - For a room that can't grow, it says why (for example, the sculpted Lakeside or the ground-less Cottage), with no Expand button.

## Checked

**Fast tests** (`tests/test_hd2d_room_expand.py`, 11 tests):
- A populated room (a cottage, an NPC, water, a sound emitter, a light, scatter, painted path and wall tiles) grows to 48 × 36 with everything else in it identical.
  - Every old tile keeps its world position.
  - The 528 new ground cells are grass, and the new wall cells are empty.
- One side alone can grow; hand-set bounds are kept; no bounds stay none.
- Seven bad sizes are refused, as are eight unsupported rooms (sculpted, painted, shifted, no ground, map off, world off, half metres, 2D).
- 2D Resize is unchanged.

**Integration tests** (`tests/test_hd2d_room_expand_save.py`, 2 tests, a real starter project on disk):
- The map file stays 40 × 30 until Save, then becomes 48 × 36 (written first; its tilesets kept). Undo plus Save gives 40 × 30; Redo plus Save gives 48 × 36.
- A map file with a tile of its own: Save is refused, both files are unchanged, and the room stays unsaved.

**GPU tests** (`tests/test_hd2d_room_expand_gpu.py`, 3 tests, hidden window, Studio's own input events):
- A starter project's new 40 × 30 HD-2D room, with a cottage and a villager in it, is expanded to 48 × 36.
- Undo and redo work; Save writes the map file with the room; it reopens the same.
- In the game, the player walks from x 1200 to 1535 (the new 1536 px edge).

**Acceptance on a copy of Lakeside Village** (`tooling/hd2d_room_expand_studio.py lakeside`; the original is only read; `m22a1_evidence/lakeside_report.json`):
- **The Village** (45 structures, 8 objects, 3 lights, 40 × 44 m):
  - Asked for 40 × 40, Studio said "depth can only grow (44 m now, 40 m asked): shrinking isn't supported", and the room was unchanged.
  - Expanded to 48 × 52, with everything else in the room identical. Undo gave exactly the room before; Redo exactly the expanded one.
- **The sculpted Lakeside and the Cottage** (no ground of its own): each said why it can't be expanded, with no Expand button.
- **Saved:** the room file and the map file are both 48 × 52 (the map file's three layers each 48 × 52 = 2,496 cells), the world size is 1536 × 1664, and the camera bounds are the new edges. It reopened the same, with nothing unsaved.
- **Studio Play:** the renderer's ground, bounds and tilemap are 48 × 52.
- **Walking east in the game:**

  | Copy | Player stopped at | Camera target x |
  |---|---|---|
  | Unexpanded control | x 1280 (the old edge) | 877 |
  | Expanded | x 1535 (the new edge) | 1133 (kept inside the new bounds) |

- **Export:** the bundle, on its own engine, has the same sizes and the same walk (1535).

**Gates:** ruff gate ok; mypy 73 (baseline); targeted Studio, HD-2D, project-operation, tilemap and contract tests: 691 passed; the GPU tests for Studio and HD-2D: 68 passed. The fast tier only gains the 11 operation tests (about 0.5 s): the two tests that make a project on disk are `integration`.

## Review corrections (independent review: conditional pass)

1. **The new ground's tile.** Reproduced: a 10 × 10 room with a grass border round a paved middle (64 paving, 36 grass) grew east with paving, because the most common tile was used. The new ground now continues the edges it grows from: the old east column when the room gets wider, the old north row when it gets deeper. If those cells are all one tile, the new ground is that tile. If they aren't, the expansion is refused with the counts, and nothing is changed: "The ground tiles along the room's east edge aren't all one tile (tile 1: 9, tile 5: 1), so which tile the new ground should be can't be told; nothing was changed. Grow the room only the other way, or first make that edge of its 2D map one ground tile." Every earlier tile keeps its world position.
   - Tests: the paved-middle room grows with grass; a path running off the east edge refuses east and east-plus-north growth but allows north growth.
   - The populated test's path tile had been on the north edge, so it was moved inside.
   - Lakeside Village's Village (its ground layer all grass) still expands, checked in memory on the original file, which wasn't written.
2. **A missing or unreadable map file.** Save used to pass over it silently and write the room at its new size. Now, when an HD-2D room's map file is missing or can't be read, Save refuses unless the room's size is still what its saved room file has. The message says which ("is missing" or "can't be read"), and nothing is saved: no room file, no rebuilt map file (its tilesets live only in it), no overwrite. The room stays unsaved.
   - Tests, for both a deleted and a malformed file: the room file's bytes are unchanged; no map file is invented and the malformed one isn't overwritten; the room is still unsaved. After undoing the size, other edits to that room save normally.
3. **Undo and redo across saves, two rooms.** A test expands the Meadow, changes the Cave's sun and saves. It then undoes one step and saves, undoes another and saves, redoes both and saves, checking both room files and the Meadow's map file at each step (48 → 48 → 40 → 48 wide, sun evening → noon → noon → evening). After each undo the undone room is unsaved; at the end nothing is.

**Tests after the corrections:**
- Fast (`test_hd2d_room_expand.py`): 13 passed.
- Integration (`test_hd2d_room_expand_save.py`): 5 passed (6 with M22A's starter-kit test, moved there; see below).
- Targeted Studio, HD-2D, project-operation, tilemap and contract tests: 696 passed.
- GPU tests for expansion and the M22A Studio workflow: 7 passed.
- Ruff gate ok; mypy 73 (baseline).

Pictures: `m22a1_evidence/01_expanded_48x36.png` (starter room), `02_lakeside_village_expanded.png` (Studio, after Expand), `03_lakeside_village_play.png` (Play).

### CI on cba7a2c, and the fast tier

- **Windows:** passed.
- **Linux:** 10,048 passed and none failed. `verify-all` failed only the `pytest-fast` step budget: 83.45 s against 79.05 s (+4.4 s), on a runner rated 1.09 that the advisory check called slow.

Measured locally, part of the overrun was this work's own cost:
- M22A.1's fast tests took 2.56 s, 1.74 s of it in one test that rebuilt the tile map for every cell (`_cells()` called inside comprehensions). Each map is now built once, and the 13 tests take 0.97 s.
- M22A's `test_a_2d_projects_first_hd2d_room_brings_the_starter_kit_and_undoes` (#409) made a starter project (3.1 s) in the fast tier. It moved, unchanged, to the `integration` module, which already makes that project once.

No budget or baseline was changed.
