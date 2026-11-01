# Technical QA: c3c7d7a, the cottage door stands in its doorway

Repository: D:\Games\Mesh-cottage, branch feature/hd2d-cottage-b, HEAD c3c7d7a. Reviewed read-only, with no repo edits and
no git writes. Hidden windows only. All evidence (scripts, JSON, pictures) is in this folder.

## Verdict

**PASS, with no blockers and no majors.** The fix does what it says. The door's bottom edge is now at 9.98 m (scene),
2 cm in front of the wall face at 10.0 m. It is centred on the doorway and wide enough to cover it. The template's
output changes only the door's and arrival's y and their ids. The door is still easy to enter from the front, the
sides and both diagonals. You cannot walk past it into the cottage shell. The player arrives outside the door's touch
area and does not loop back in. Save and load work. Existing projects keep their door. The new test fails on the old
placement. All suites are green. The only findings are two minor ones (a stale comment and a test that is weaker than
it looks), plus a pre-existing interior-door problem that is reported but out of scope.

## Defects

| # | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| 1 | minor | Stale tooling comment: `tooling/hd2d_visual_study.py` Walk.run says "the door's trigger reaches about 2 m: approach it from the south, not along its front". The trigger now reaches 1.08 m from the wall face (it was 2.17 m). Walking along the front at feet y 8.5 no longer enters the cottage (it did before). | interact_new.json / interact_old.json (straight-on trigger at feet 8.922 vs 7.828); qa_loop.py: old placement entered the cottage on the front leg at y 8.5, the new one did not | Update the comment (about 1.1 m). The route itself still works. |
| 2 | minor (test robustness) | `test_the_cottage_door_stands_in_its_doorway` takes the door's bottom as `y - image.height/2`. The renderer stands the billboard on `sprite.bottom`, which arcade 3.3 derives from the hit box (trimmed to opaque pixels: the door's hit box is x 9.25–10.75, top 11.918, not the full 64 px). The two agree only because door.png's bottom row is opaque. If the art gained a transparent bottom margin, the test would still pass while the door visibly floated. The wall face is also a hard-coded "2 m south" rather than the model's collision. | qa_interact.py: door_sprite = door_hitbox = [9.25, 9.98, 10.75, 11.918] while `door.width == 64` | Optional: in the test, also assert that door.png's bottom row has opaque pixels, or measure via the hit box. Not a blocker: the test does fail on the old placement (see 8). |

Not a defect (reported for the owner):

- **Interior door (item 9, pre-existing, out of scope; it shows).** The cottage interior's door sprite spans
  x 4.85–6.35 m with its bottom at 6.6 m. The interior's west wall spans x 5.0–5.2, so the door pokes 0.15 m
  through the wall into the black void outside the room. It is also a free-standing billboard 1.7 m in front of the
  north wall (whose face is at 8.3), standing on the floor in mid-room. The interior model's own doorway is a gap in
  the **south** wall (x 7.4–8.6, y 3.5–3.7), so the way out is drawn where the room has no opening. See
  inside_cmp.png (top: as made; bottom: door hidden). The same bottom-edge rule applies there, and it is visible.
  No other template door exists: the hd2d_rpg template has exactly these two, and the 2D templates are not HD-2D.
- **Cutaway rim (cosmetic, not a regression in visibility).** The door's top (now 1.08 m further north) overlaps the
  lower rim of the cutaway opening when the player is just behind the cottage: about 1,500 px at 1280×720, with feet
  at (10, 14.3). It covers only the cut-open interior, never the player (see 3). new_10_143_zoom.png: red marks the
  rim pixels the door now covers.
- Pre-existing, the same before and after: just behind the north wall (feet y 14.3–14.6), the cutaway shows only the
  player's head (613–687 visible px, against about 3,400 in the open). This comes from the interior's cobbled north
  wall, not from the door.

## Measurements

Coordinates are scene metres (32 px/m). Village m + 4 = scene m.

**Geometry (new template, fresh project).**

- Door entity: (320, 351.36) px = (10.0, 10.98) m. Sprite and hit box: x 9.25–10.75, y 9.98–11.918. Previously the
  door's y was 8.9–10.838.
- Arrival: (320, 255.36) px, the centre at 7.98 m; feet at 7.418.
- Cottage collision (unchanged):
  - the south wall is two boxes, x 7.5–9.4 and x 10.6–12.5, at y 10.0–10.2;
  - the lintel spans x 9.4–10.6 at z 2.0–2.5;
  - the walls on the other sides are E 12.3–12.5, W 7.5–7.7 and N 13.8–14.0.
  - The doorway gap is 1.2 m. The door's hit box overhangs it by 0.15 m on each side.
- The door has no collider and is not in the solids list.
- Player:
  - Feet box (footprint): 19 × 12 px (0.594 × 0.375 m), centred 18 px below the sprite's centre.
  - Touch box: arcade `check_for_collision_with_list` between the sprite hit boxes (the door has no
    `area_width/height`). The player's hit box is 0.56 m wide and runs from feet − 0.19 to feet + 1.09 m.

**1. Door interaction.** The script is qa_interact.py; results are in interact_new.json and interact_old.json.

| approach | new: feet at trigger | new: feet-centre gap to wall face | old: feet at trigger |
|---|---|---|---|
| straight on, x 10.0 / 9.2 / 10.8 (UP) | y 8.922 (player hit box top 10.016) | 1.08 m | y 7.828 (2.17 m) |
| diagonal UP+RIGHT from (8,7) / UP+LEFT from (12,7) | (9.933, 8.933) / (10.067, 8.933) | 1.07 m | (9.105, 8.105) / (10.895, 8.105) |
| along the wall from the west (feet y 9.781) | x 9.109 | wall-hugging | x 9.109 |
| along the wall from the east | x 10.891 | wall-hugging | x 10.891 |

All seven approaches entered cottage.json, in both placements.

- **Hugging the wall.** Walking UP beside the cottage stops at feet y 9.781–9.797, so the feet-box top sits at
  9.97–9.98, within 2–3 cm of the face. Standing there at x 8.3, 8.6, 11.4 and 11.7 does **not** trigger the door
  (the player's hit box right edge is 8.881, against the door's left edge at 9.25). You can stand beside the door
  near the wall.
- **Leaving the cottage.**
  - The player appears with feet at (10.0, 7.418). Their hit box top is 8.511, against the door's bottom at 9.98:
    1.47 m clear.
  - Idle for 600 frames: still in the village, position unchanged, 0 re-entries.
  - Holding UP from the arrival re-enters after 1.484 m (20 frames), the same as the old placement.
- **Stuck or in the wall.** A random walk of 1,200 frames (UP/LEFT/RIGHT, with DOWN every 20th) at the wall beside
  the door gave:
  - a feet-box top range of 9.454–9.999;
  - 0 frames with the feet box inside any cottage wall box.
  - It ended by entering the door.

  The door is not solid, and the wall stops the feet box before the face, so there is no "between door and wall"
  pocket to get stuck in.

**2. Collision and navigation.**

- A project made by the pre-fix template (in a scratch tree, COTTAGE_DOOR reverted) diffed against the fixed one
  differs **only** in the door's and arrival's `y` and in their ids (`…_316p8…` → `…_351p36…`). Structures, models,
  maps and NPCs are identical. Nothing references those ids.
- A loop around the cottage (UP to 15, LEFT to 6.5, DOWN to 8.5, RIGHT to 13.5) completed in the new project. In the
  old one, the front leg at y 8.5 walked into the door.

**3. Cutaway** (qa_cutaway.py; results in cut_new_a.json and cut_old_a.json).

- Method: 35 player positions behind the cottage (x 8.5–11.5, feet y 14.3–16.5). The cutaway is held on the player
  while the player is hidden, and the visible player pixels are counted with the door shown and with it hidden.
- Result: the door hides **0** player pixels at every position, in both the new and the old placement. The player's
  visible counts are identical between the two (613–3,378 px).

**4. Save and load** (qa_saveload.py).

- Saved beside the door at (8.6, 9.781). After moving and loading, the player was back at (8.6, 9.781). Walking
  RIGHT then entered the cottage, arriving at (8.0, 5.412).
- Saved inside, moved 1 m, loaded: back at (8.0, 5.412). Walked to the door and left to the village, arriving at
  (10.0, 7.418), with 0 re-entries over 400 idle frames.
- Cross loads in both directions were correct. After the loads the live door was at (10.0, 10.98) with its bottom at
  9.98.

**5. Existing projects** (qa_existing.py; a copy with the door at 9.9 × 32 and the arrival at 6.9 × 32).

- **Game.** The live door stays at y 9.9 with its bottom at 8.9. You can enter, leave, and arrive at (10.0, 6.338).
  On disk the door and arrival are unchanged (316.8 / 220.8).
  - The only file written is `.mesh/editor_session_state.json` (the game's camera and session state, which every
    project gets), plus an empty `saves/` folder. No scene, map or config file changed.
- **Studio.** Zero files changed. Studio's document holds the door at 316.8.
- **The engine.** No code in engine/ rewrites door positions. `COTTAGE_DOOR` is used only in starter_village.build.

**6. Installed engine** (`install/`: exit 0, driver exit 0).

- The wheel carries exactly the 178-file allow-list.
- Installed versions: arcade 3.3.3, pyglet 2.1.19, pillow 11.3.0, jsonschema 4.26.0.
- The play walk went "through the cottage door" and arrived in cottage.json at (8.0, 5.41). Quick save and load
  worked. Export worked, and the exported game ran.
- The "Mesh Village" project's door is at **(320.0, 351.36)** and its arrival at (320.0, 255.36): the new position.

**7. Suites**, run from the worktree:

| suite | result |
|---|---|
| `pytest -q -m fast` | 4,610 passed, 6 skipped, 5,386 deselected (122 s) |
| `MESH_GL_SMOKE=1 pytest tests/*_gpu.py` | 111 passed (157 s) |
| starter_template + launcher_and_templates + hd2d_catalog + hd2d_cutaway | 62 passed |
| test_wheel_bundles_engine_data.py, without PYTHONPATH | as instructed it ran **0 tests** ("1 deselected": the repo's addopts marker filter excludes it). With `-o addopts=` it ran: 1 passed (48 s). |
| ruff_gate | ok |
| mypy_gate | only the two known local errors in tooling/hd2d_lab (gltf.py type-var, lab.py no-any-return); nothing else |

Note: the worktree has an untracked `docs/reviews/milestone17_cottage_integration_evidence/door/` (created at 09:12,
before this QA; the fix's own evidence, it seems). It is not in c3c7d7a. Commit it or drop it, as the owner prefers.

**8. Mutation check.**

- Scratch copy: `git archive HEAD` into tree_old\.
- With the fix as it stands, the new test passes.
- With `COTTAGE_DOOR = (6.0, 5.9)`, the new test **fails** at the in-front-of-the-wall assert (`320.0 - 284.8 <= 1.6`).
  The other 11 tests in the file still pass, so the new test is the only guard on the door's position.

## Evidence files (this folder)

- Scripts: qa_common.py, qa_interact.py, qa_cutaway.py, qa_cutmask.py, qa_saveload.py, qa_existing.py, qa_loop.py,
  qa_inside.py, qa_front.py.
- Results:
  - interaction: interact_new.json, interact_old.json;
  - cutaway: cut_new_a.json, cut_old_a.json.
- Pictures:
  - front_cmp.png: the cottage front, new (left) against old (right). The doorway artefact and the wall shadow are
    gone.
  - cmp_behind_14.3.png and new_10_143_zoom.png: from behind the cottage.
  - inside_cmp.png: the interior door.
- Logs: suite_fast.txt, suites_rest.txt, install_log.txt, plus install\ (the acceptance outputs).
- projects\: probe (new template), new_a/new_b (copies), old_a/old_c (old door simulated), pre_fix_template (the
  template from the reverted tree).
