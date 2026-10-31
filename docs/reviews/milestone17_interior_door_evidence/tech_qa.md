# Tech QA: the cottage's inside exit door (feature/hd2d-interior-door, 2c202df on e950911)

Independent technical QA. I made no edits to the repository and no git writes. Hidden windows only.
Everything is in the review session's scratch folder (not committed):
- scripts `s1_static.py`, `s2_runtime.py` (run as `new` and `old`), `s3_tomas_render.py`, `s4_existing.py`, `s5_diffprojects.py`;
- results `out\runtime_new.json`, `out\runtime_old.json`, `out\s3.json`, `out\s4.json`, pictures `out\inside_*.png`, `out\tomas_dialogue.png`;
- `install\` (the install acceptance), `suites.txt`, `fast.txt`, and `tree_old\` (a scratch copy of the tree with the original placement).

## Verdict

**PASS, with minor findings.** I found no blocker or major defect.
- The door stands where the brief says, through no wall and on no other object.
- Entering, exiting, idling, save/load, Tomas's line, old projects, the install, and every suite and gate behave correctly.
- The new test fails on the original placement.

The one point the owner should decide on is design, not a bug: **D1**. The exit fires from a 2.0 × 1.7 m patch of floor in front of the doorway, reaching 1.9 m into the room. That is 24% of the walkable floor, against 16% for the old door.

## Defects

| # | Sev | Finding | Evidence | Fix |
|---|-----|---------|----------|-----|
| D1 | minor (design call) | **The exit zone is deep.** The exit fires anywhere the player's feet are in x 7.0–9.0, y 3.5–5.6 m. That reaches 1.9 m north of the south wall's inner face (3.7) and 2.1 m north of the doorway's outer face (3.5). It is 388 of 1598 standable 0.1 m cells (24.3%); the old door's was 260 cells (16.3%). Walking straight south at x 8.0, the exit fires with the feet at y 5.54, about 1.85 m before the doorway. On screen this is where the player's feet go behind the top of the door's picture, so it reads as touching the door. The engine works as designed here: the touch test is overlap of the picture boxes, and the door's box is 1.5 × 1.94 m, standing north of its bottom edge. From the arrival, holding DOWN+LEFT exits within 8 frames (0.13 s). Arriving and then pressing LEFT, RIGHT, UP or DOWN alone does not exit. | trigger map below; `runtime_new.json` walk_lines and exit | Accept as how HD-2D doors behave, or confine the zone. `SceneTransition` already supports `area_width`/`area_height` (an area centred on the sprite centre, y 4.48). For example, an area of 1.2 × 0.4 m covers y 4.28–4.68, so the exit fires at feet ≲ 4.87. Its x range would be about 6.9–9.1: the area test uses the player's full 1 m-wide sprite bounds, not its hit box. Re-measure if you adopt it. Moving the arrival east is not an option: Tomas (x 9.72–10.28) and the bed (x ≥ 9.15 for y ≥ 6.5) leave no room. |
| D2 | minor (test gap) | `test_every_character_door_and_arrival_has_somewhere_to_stand` checks a door at its **sprite centre** (y 4.48), not at its bottom edge, where a billboard actually stands. The inside door's bottom edge (8.0, 3.48) has **no floor under it**: `World.heights_at` returns `[]`, 2 cm south of the slab's edge. The outside door's base is on the ground (0.0, 'ground'). The door's elevation is explicit (0.1 m), so nothing visible depends on this today. With sun shadows off, half of its blob shadow (y 2.94–3.48) hangs over the void; against the near-black background it can only just be seen (`out\inside_nosun.png`). The test passes for the wrong reason for doors. | `s1`, ad-hoc `World.stand` check (see "Placement") | Leave the placement as it is: standing it on the slab (y ≥ 3.5) would push the 1.5 m-wide picture into the jambs. Make the stand test measure doors at their bottom edge with an explicit tolerance, or exempt doors and say why. |
| D3 | nit | The `INSIDE_ARRIVAL` comment says the door "is touched up to y 5.4 in front of it". 5.42 is the top of the **door's** box. The player's **feet** trigger up to y 5.60, because the player's box reaches 0.19 m below its feet. | `runtime_new.json`: N->S lines fire at 5.54; static map edge 5.6 | Say "feet touch it up to y 5.6". |

Observations, not regressions from this change (no action needed for this PR):
- **O1:** arriving inside, the feet land at (9.2, **6.013**). At the start they are at (9.2, **6.2**). `spawn_point` uses `FEET_32` (12 px) but the player is 48 px tall (feet offset 18), so arrivals land 0.19 m south. The commit comment acknowledges this, and the village and the old template use the same convention.
- **O2:** the door picture is an upright billboard stretched by 1/cos 55°. It shows about 0.6 m taller than the 2.2 m wall on screen, and is 0.15 m wider than the doorway on each side. It stands in front of the jambs, not through them. Whether that looks right is for visual QA (`out\inside_sun.png`).
- **O3:** after `save_manager.load_game`, `scene_controller.current_scene_path` gives the slot ('qa_inside', 'quicksave'), not the room. Transitions still work afterwards. This is engine behaviour that predates the change.
- **O4:** entity ids encode the position `link_rooms` first gave them. The inside arrival is `cottage_arrival_start_256_47p36_0_0` but stands at (294.4, 210.4). The old template had the same mismatch. Nothing references these ids: only `cottage.json` differs between projects made by the old and new templates.

## Measurements

### 1. Placement (live cottage, `runtime_new.json` / `s1`)
- The room model is at (8.0, 6.0) m.
  - The floor slab runs x 5–11, y 3.5–8.5, z 0–0.1.
  - The south wall's outer face is at y 3.5 and its inner face at 3.7. The doorway is x 7.4–8.6.
- The door's sprite centre is at (8.0, 4.48). Its bottom is at **3.48**: 2 cm south of the outer face, centred on the doorway. Its elevation is **0.1 m**, the floor top, level with the threshold.
- The door's hit box (= its opaque picture) is **x 7.25–8.75, y 3.48–5.418**.
  - That is within the room's width (5.0–11.0) and within the inner width (5.2–10.8).
  - Its bottom edge is in front of the outer face, not inside the wall or the room. It overlaps the jamb footprints (x 7.25–7.4 and 8.6–8.75) only in front of them: its plane is at y 3.48.
- Overlaps with the door:
  - Tomas: box x 9.72–10.28, y 4.81–6.16. No overlap (`check_for_collision` False); the gap is 0.97 m.
  - Table (x 7.4–8.6, y 6.6–7.4) and bed (x 9.6–10.7, y 6.6–8.2): north of the door box's top (5.42). No overlap.
  - Lamp: a light at (8.0, 7.0), 2 m up. Not a body.
  - Player start: box x 8.92–9.48, y 6.01–7.29. No overlap.
- Camera: pitch 55°, bounds (144, 96, 368, 288) px = (4.5, 3.0, 11.5, 9.0) m. The door lies inside the bounds.

### 2. Entering from the village (3 runs, each from the village start)

| Approach | Fires with feet at | Arrival feet inside | Arrival touches door |
|---|---|---|---|
| straight (UP at x 10.0) | (10.00, 8.86) | (9.20, 6.013), z 0.1 | no |
| angled from the west (UP+RIGHT) | (9.09, 9.04) | (9.20, 6.013) | no |
| angled from the east (UP+LEFT) | (10.89, 8.99) | (9.20, 6.013) | no |

- After arriving, 600 frames with no input: no transition (feet unchanged).
- The new project's start inside: feet (9.2, 6.2). 600 idle frames: no transition.

### 3. Exiting

| Route | Fires with feet at | Village arrival feet |
|---|---|---|
| from the arrival, LEFT to the door's line, then DOWN | (7.95, 5.544) | (10.0, 7.378) |
| from the arrival, DOWN+LEFT | (8.758, 5.571), after 8 frames | (10.0, 7.378) |
| from (6.5, 6.0), DOWN+RIGHT | (7.073, 5.405) | (10.0, 7.378) |

- Against the wall and the doorway: the exit fires about 1.84 m north of the inner face (3.7) and 2.04 m north of the doorway's outer face (3.5). At that moment the feet are behind the top of the door picture on screen (`out\inside_player_at_zone_edge.png` shows the player at feet y 5.62, just outside the zone).
- In the village after the exit:
  - 600 idle frames: no re-entry.
  - Holding DOWN for 120 frames (to y 0.03), then LEFT for 60 and RIGHT for 120: no re-entry.

### 4. Trigger map, inside (0.1 m grid of feet positions)
`X` means standable and the exit fires; `.` means standable, no exit; `#` means not standable; `x` means the exit would fire but the feet can't stand there. The test is `arcade.check_for_collision(door, player)`, the same test `SceneTransition` runs, with the player's feet put at each cell. Standing is `World.stand` with the player's footprint (±0.45 × ±0.19 m). Columns start at x 4.9.

New (door in the south doorway):
```
 6.4 ########...............................................########
 5.7 ########...............................................########
 5.6 ########..............XXXXXXXXXXXXXXXXXXX..............########
 5.5 ########.............XXXXXXXXXXXXXXXXXXXXX.............########
  ...  (rows 5.4 .. 3.9 identical to 5.5)
 3.9 ########.............XXXXXXXXXXXXXXXXXXXXX.............########
 3.8 #####################xxxxxxxxxXXXxxxxxxxxx#####################   (doorway: feet x 7.9-8.1)
 3.5 #####################xxxxxxxxxXXXxxxxxxxxx#####################
```
- The exit zone is x **7.0–9.0**, y **3.5–5.6**: 388 cells (24.3% of the walkable floor).
- Full rows are in `runtime_new.json` → `trigger_map`.

Old (door at (5.6, 7.6), by the west wall): the exit zone is x **5.7–6.6**, y **5.6–8.1**, 260 cells (16.3%).

Flood fill from the start without crossing the exit zone: **every non-exit standable cell is reachable**, in both layouts (1210/1210 new, 1338/1338 old). Between the exit zone and the table there is a corridor at y 5.7–6.4 (0.8 m), so the room's west and east halves connect without exiting.

Walk lines, new layout. Each starts by a teleport to a cell that doesn't touch the door, then holds one key:

| Line | Result |
|---|---|
| W→E at y 3.9 / 4.2 / 4.6 / 5.0 / 5.4 / 5.6 | exits at x 7.14 (0.26 m before the west jamb at 7.4) |
| W→E at y 5.8 / 6.2 | crosses to x 10.5, no exit |
| W→E at y 7.0 / 7.8 | stopped by the table / the bed, no exit |
| E→W at y 4.6 / 5.4 | exits at x 8.86 |
| E→W at y 5.8 / 6.2 | crosses to x 5.5, no exit |
| N→S at x 5.5 / 6.5 / 9.2 / 10.0 | reaches the south wall (y 3.94 / 3.9), no exit; x 10 passes beside Tomas |
| N→S at x 7.0 | exits at y 5.50 |
| N→S at x 7.6 / 8.0 / 8.4 | exits at y 5.54 |

Old layout: the inside lines at y ≤ 5.4 cross without exiting; E→W at y 5.8 and 6.2 exit at x 6.52.

### 5. Tomas
- From feet (9.51, 4.95), pressing E opens the dialogue.
- Speaker "Tomas"; text "Make yourself at home." / "The door in the south wall takes you back outside." ✓ (`out\tomas_dialogue.png`).
- It closes with E; the room stays the cottage.

### 6. Save / load (`game.window.save_manager`, as `tooling/hd2d_demo.py` does; also F5/F9)

| Step | Result |
|---|---|
| save inside at (9.2, 6.825) | ok |
| save outside at (11.953, 7.062) | ok |
| load the inside save | cottage, (9.2, 6.825), not touching the door; 300 idle frames, no transition |
| then walk out (LEFT to x 8, DOWN) | exits at (8.97, 5.50) → village (10.0, 7.378) |
| load the outside save | village, (11.953, 7.062); 300 idle frames, no transition |
| then walk in | → cottage arrival (9.2, 6.013) |
| F5 inside at (6.466, 6.2), move to (6.466, 8.075), F9 | back at (6.466, 6.2) |

### 7. Collision, navigation, cutaway, exterior door
I made one project with the original template (`tree_old`, e950911's `starter_village.py`) and one with the change, then compared every file.
- **Only `scenes/cottage.json` differs**, and only in four entities: the door, the arrival, the player start, and Tomas's line.
- `start.json` is byte-identical: the exterior door from #372 is unchanged. Entering through it works from all three approaches (above).
- The cottage's `settings` (structures, camera, sun, lights) are identical. The interior's collision, floors and cutaway are unchanged; the model is unchanged.
- `test_every_character_door_and_arrival_has_somewhere_to_stand` passes, but see D2.

### 8. Existing projects (old-template simulation, `s4.json`)
- The rewritten positions are door (179.2, 243.2), spawn (256, 191.2), player (256, 197.2).
- Played in the game, then opened in Studio on the cottage room and closed without saving:
  - The positions are unchanged in the files and in Studio's in-memory scene.
  - The only file written is `.mesh\editor_session_state.json` (the editor's session state; no scene file).
- In play the old layout still works: arrival (8.0, 5.412); out through the old west door → village (10.0, 7.378).
- Only `engine/project_templates.py` imports `starter_village` (at project creation). Nothing else references `INSIDE_DOOR`/`INSIDE_ARRIVAL`.

### 9. Installed engine
`py -3.13 tooling/hd2d_install_acceptance.py ...\qa_tech\install` exited 0 and the driver exited 0.
- Wheel `mesh_engine-0.5.0`: 178 bundled files, matching the allow-list.
- The installed `starter_village.py` has the new `INSIDE_DOOR`/`INSIDE_ARRIVAL`.
- In the projects it made ("Presentation", "Mesh Village", and the exported bundle), the inside door is at **(256.0, 143.36)** and the spawn and player at (294.4, 210.4) / (294.4, 216.4).
- Note: its `pip wheel .` leaves `build\` and `mesh_engine.egg-info\` (git-ignored) in the worktree. I listed and deleted only those two, which my run created; the worktree's `git status --ignored` matches its state before the run.

### 10. Suites (run from D:\Games\Mesh-cottage)
| Suite | Result |
|---|---|
| `pytest -q -m fast -p no:cacheprovider` | **4611 passed**, 6 skipped, 5386 deselected (126 s) |
| `MESH_GL_SMOKE=1 pytest tests/*_gpu.py` (17 files) | **111 passed** (156 s) |
| template + launcher + catalog (`test_hd2d_starter_template.py`, `test_launcher_and_templates.py`, `test_hd2d_catalog.py`, `-o addopts=`) | **61 passed** |
| `test_wheel_bundles_engine_data.py -o addopts=` (no PYTHONPATH) | **1 passed** |
| `tooling/ruff_gate.py` | ok |
| `tooling/mypy_gate.py` | exit 1, with only the two known local errors (`tooling/hd2d_lab/gltf.py` type-var, `tooling/hd2d_lab/lab.py` no-any-return); nothing new |

The wheel test also leaves `build\` and `mesh_engine.egg-info\` in the worktree. I removed only those, again; `git status --short --ignored` is back to its state before QA, and HEAD is still 2c202df.

### 11. The new test against the original placement
- In `tree_old` (a `git archive` of 2c202df with e950911's `starter_village.py`), `tests/test_hd2d_starter_template.py` gives **1 failed, 12 passed**.
- `test_the_cottage_inside_door_stands_in_its_south_doorway` fails on `assert door["x"] == room["x"]`: 179.2 ≠ 256.0.
- On the change, the file passes.
