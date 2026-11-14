# Milestone 7: the Engine Capabilities Lab

Branch `redesign/visual-editor`. The other two reports:
- [`milestone7_capability_inventory.md`](milestone7_capability_inventory.md)
- [`milestone7_consolidation_plan.md`](milestone7_consolidation_plan.md)

**Question:** do Mesh's reusable systems work in the running engine, not only in unit tests?

**Answer, after this milestone:** the sixteen capabilities below do, measured in the real Arcade window. Eight of them were broken when the lab first ran, and all eight had green unit tests.

## The harness

`tooling/capability_lab.py` builds a disposable project, then plays it in Mesh Studio's play-test, which runs the game's own loop in the real window.

```bash
py -3.13 tooling/capability_lab.py --out DIR            # all checks
py -3.13 tooling/capability_lab.py --out DIR --only lights torch
```

- **Placeholder content only.**
  - Generated coloured squares, a striped background, and three generated `.wav` tones.
  - No third-party art.
  - The project lives in `DIR/lab` and is not kept.
- **One small room per capability:** Paths, Lights, Torch, Sequence, Camera, Depth, Audio.
  - Rooms are made with Studio's `Project`/`project_ops` and the `authoring` API, as a person or AI would make them.
  - Scene keys Studio can't author yet (lights, occluders, camera areas, background layers) are written into the room documents.
- **A probe plugin** in the project's own `mods/` registers a custom behaviour, `LabSpinner`.
- **How each check reads the result:**
  - It reads the game's state from Studio's layout dump, which while playing now includes `engine/runtime_probe.py`: lighting, particles, camera, and the last positional sounds.
  - Where the question is visual, it also samples screenshot pixels.
- **Input:** OS-level keys and mouse, only to the Mesh window (`MESH_GUI_AT`, `MESH_GUI_POLITE` as for the other GUI tests).
- **Output:** `DIR/lab_report.json` plus a screenshot per check.
- **Its own rule:** no check works around a failure. When one failed, either the harness was wrong (fixed in the harness, listed below), or the engine was (fixed at its source, with a unit test).

## Results: final run, 16 of 17

Evidence is in [`milestone7_lab/`](milestone7_lab/): `lab_report.json` plus the screenshots named below.

| # | Capability (system used) | Measured | Result | Screenshot |
|---|---|---|---|---|
| 1 | Flickering light (static scene light, `flicker_*`) | Lighting on, mode hard. Centre of the light 99, darkness far away 12. Brightness near the light's edge over 1.2 s: 28, 50, 48, 45, 42, 39, 36, 33. | PASS (after fixes A, C, D) | `lights.png`, `flicker_*.png` |
| 2 | Occluder shadow (hard shadows, rect occluder) | Behind the pillar 10 vs 33 at the same distance in the open | PASS (after fix A) | `lights.png` |
| 3 | Moving object with a dynamic light (`LightSource` + `PatrolPath`) | One light, following the torchbearer through its ping-pong patrol (6 samples over 3 s) | PASS (after fix B) | `torch.png` |
| 4 | NPC paths around an obstacle (`FollowPath`, A*) | From (304, 204) to the goal (464, 240) beside a 9-tile wall, never inside it | PASS | `nav_walker.png` |
| 5 | Line of sight changes behaviour (`ChaseTarget`, `los_required`) | The chaser that could see the player moved to (159, 112); the identical one behind the wall stayed at (528, 112) | PASS | `los.png` |
| 6 | Move, wait, then dialogue (`SequencePlayer` + `Dialogue`) | Moved 96 px to (368, 176); the dialogue "Moved, waited, now talking." opened 3.1 s after it was seen arriving (the wait step is 3 s) | PASS (after fix E) | `sequence.png` |
| 7 | Camera zoom (`settings.camera.areas`) | Walking into a 200×128 area: zoom 1.0 → 1.8, area "close-up" | PASS | `zoom_area.png` |
| 8 | Parallax background (`background_layers`, parallax 0.5) | Camera moved 441 px; the background's stripe moved 220.5 px on screen (expected 220.4) | PASS | `parallax_before.png`, `parallax_after.png` |
| 9 | HD-2D draw order (y-sort; two sprites share a texture) | Where the front red square overlaps the blue one: red (220, 50, 50). Where blue overlaps the back red one: blue (50, 90, 230). | PASS (after fixes D, F) | `depth.png` |
| — | Sprite shadows (default on) | Floor just under a sprite's feet 69, plain floor 108 | PASS (after fix G) | `depth.png` |
| 10 | Particle effect (`ParticleEmitter`) | 13 live particles | PASS | `particles.png` |
| 11 | Positional sound (`play_world_sfx`; listener is the camera) | The same hit sound at 900 px: volume 0.0, pan 1.0; at 284 px: volume 0.41, pan 0.32 | PASS (after fix H) | `audio.png` |
| 12 | Save and load (F5 / F9, SaveManager slot) | Saved with the player at (128, 128) and the chasing NPC at (159.5, 112). Walked to (231, 128). After F9 both were back exactly. | PASS | `save_load.png` |
| — | Prefab reuse | A `prefab_id: person` reference and a Studio-placed copy both spawned | PASS | `particles.png` |
| — | Custom behaviour from a plugin (`<project>/mods/`) | `LabSpinner` turned its square 216° → 306° in 0.6 s; the plugin logged its load | PASS | `particles.png` |
| — | Room transition (`SceneTransition` door made by `link_rooms`) | Lights room → Paths room, arriving at (560, 64) | PASS | `transition.png` |
| — | `background_planes` from a scene file (headless) | `SchemaValidationError`: "Additional properties are not allowed ('background_planes' was unexpected)" | **FAIL: confirmed engine defect, not fixed** (consolidation: convert to `background_layers`) | — |

## Engine bugs found and fixed

The first full run passed **7 of 17**. Every failure was then traced to its cause, either in the engine (below) or in the harness (next section).

| | Bug | How the lab showed it | Fix | Regression test |
|---|---|---|---|---|
| **A** | **Light glow ignored the camera.** `LightLayer.draw` ran under the GUI camera with no scroll offset, so a light at world (368, 240) was drawn at *screen* (368, 240). Its hard shadow, which does subtract the camera, appeared somewhere else. | The flicker light's circle sat in the room's corner, around the player; the pillar's shadow was a wedge at the right place, with no light around it. Brightness at the light: 2. | Draw the light layer through the world camera (scroll and zoom), then return to the GUI camera (`engine/lighting/__init__.py`). The composite is a full-screen quad, so it is unaffected. | Lighting suites (458) |
| **B** | **Object lights were never removed.** No code ever took a handle out of `_dynamic_handles`. Studio's edit view loads a room into the game window too, so play-testing left a frozen copy of the light behind, and it kept shining in every later room. | Two torch lights: one at the start point, never moving, and one following the NPC. The frozen one was also visible in the Sequence room. | `configure_scene_lighting` clears object lights when a scene loads, before the new objects spawn and register their own. | `test_scene_lighting_reset.py` |
| **C** | **A room's ambient tint carried into the next room.** It was only set when a room had one. | The Sequence, Camera and Depth rooms, which set no darkness, were as dark as the Torch room before them. | A room without `ambient_light_rgba` gets the project's. | `test_scene_lighting_reset.py` |
| **D** | **Day/night overwrote the project's ambient while switched off.** `DayNightCycle.__init__` always applied its 21:00 colour. | The probe read ambient [58, 41, 46] with a project ambient of [255, 255, 255]: every lit room was dusk-dark. | Apply it only when enabled. | `test_day_night.py` |
| **E** | **SequencePlayer `move_to` moved `speed` px per frame.** It passed (velocity, `dt`) to a mover that adds what it's given and ignores the fourth argument. | The herald jumped 80 px a frame and swung round its target forever, so the sequence never reached its `signal` and the dialogue never opened. | Pass this frame's distance, never past the target. Patrol and FollowTarget made the identical call and were fixed the same way (unit tests only, not lab-run). | `test_sequence_player_move_to.py`, `test_patrol_follow_speed.py` |
| **F** | **Batching broke y-sort.** `build_batches` gathered every use of a texture into one batch at its first position. | The front red square was drawn behind the blue one, because both reds were drawn first. | Merge only neighbouring draws. | `test_render_queue_batching_groups.py` |
| **G** | **Sprite shadows were hidden under their sprites.** A 24×8 ellipse anchored 4 px below the sprite's centre. | No visible shadow under any sprite: equal brightness under the feet and on the floor. | Anchor at the feet, with the same helper y-sort uses. | `test_sprite_shadow_model_contract.py` |
| **H** | **Projectiles moved `speed` px per frame.** `change_x` was set in px/s; arcade applies it once a frame. | Shots were measured 20,000 px off the map; no hit was ever recorded. | Convert to arcade's per-frame unit. | `test_projectile_speed.py` |

Bugs A to D share a lesson. Lighting had about 430 tests and none of them drew a frame, so a light in the wrong place was invisible to all of them.

## Harness mistakes, corrected in the harness

Listed so the passes aren't mistaken for tuning. None of these changed engine code.
- **Plugin location.** The first draft put the probe plugin in the engine repo's `mods/`. The game loads mods from the folder it runs in, so it moved to the project's `mods/`. This also corrected an earlier audit claim.
- **Rooms smaller than the window.** The camera is clamped to the map and so never moved, making parallax and positional sound untestable. The Camera and Audio rooms were widened to 60 tiles, and the old right-hand wall was removed.
- **Flicker sampled at the light's centre.** Flicker mostly changes a light's reach, so it is now sampled near the edge.
- **Darkness.** The project's base ambient is set to full brightness, and dark rooms tint it down. This is how per-room darkness works (consolidation plan).
- **Draw order judged by brightness.** Now judged by hue, so a dark room can't fail it.
- **The sequence's wait** was lengthened to 3 s, because the herald's arrival was seen late.
- **Prefab reference** found by position: Studio's dump reports an object's authored `name`, and the reference's `mesh_name` isn't shown (minor; noted in the inventory).

## What the lab does not cover yet

Still UNVERIFIED in the engine:
- **Rendering:** depth tint; outlines; shadow polygons at zoom ≠ 1.
- **Lighting:** cookies; light shafts; ToggleSceneLights; soft shadows (unreachable); day/night over time; fog.
- **Camera:** shake.
- **Events:** CutsceneController; timers.
- **AI:** EnemyAI; NpcSchedule; Wander/Flee.
- **Gameplay:** Vendor, drops and chests; DamageOnTouch (CODE says it doesn't damage).
- **Quests:** QuestHook.
- **Other:** post-processing (unreachable); web export.

These are the first rooms to add (consolidation plan, section 5).

## Notes

- **Listener.** Positional sound uses the camera centre as the listener. That is a valid design, but in a room smaller than the window, distance never changes.
- **Torch-light trail.** In the final full run the torch's light trailed its NPC by a steady ~12 px. A separate run of that check alone (with one Torchbearer counted in the dump) put the light exactly on the NPC in all six samples. The trail's cause was not found; it is not reproducible so far.
- **False warning.** The scene validator warns "missing required params: goal_x, goal_y" for a FollowPath whose settings are in `behaviour_config`, the form Studio writes, although it walks correctly.

## Regression

| Check | Result |
|---|---|
| Milestone 1 acceptance | 15/15 |
| Milestone 2 acceptance | 23/23 |
| Milestone 3 acceptance | 15/15 |
| Milestone 4 acceptance | 20/20 (with `--old mygame`, which the test copies first; the original was not modified) |
| Milestone 5 acceptance | 17/17 |
| Milestone 6 co-authoring | 14/14 |
| Full suite | 10 failed, 9,350 passed: the 9 baseline failures, plus one exception-count ratchet tripped by the lab harness's own handlers. Those handlers were narrowed and the ratchet passes now; nothing else is new. The ruff gate and mypy island are clean. |
