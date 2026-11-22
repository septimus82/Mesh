# M1-B-1: a representative HD-2D crossing, made in Studio (evidence)

Plan: `docs/plans/hd2d_online_investigation.md` §4, M1-B-1. One HD-2D room, the **Crossing**, with:

- a walk-in doorway to a second room, **Inside**, and a door back;
- stairs up to a raised bridge deck, and an underpass beneath it;
- lamps with shadows;
- a follow camera kept inside the room, and see-through buildings.

It uses only Mesh's shipped HD-2D starter kit. There is no new art and no engine change.

## Where it lives and how it is built

The plan's M1-B-1 puts the scene in a builder script, like the floors crossing that M1-A-3 already uses
(`tooling/hd2d_floors_demo.py build`). So nothing is committed as a project: the scene is rebuilt each time.

- **Builder:** `tooling/hd2d_m1b_scene.py`.
- **Output:** `build(OUT)` makes `OUT/game`. Its rooms are `packs/core_regions/scenes/crossing.json` (the start room)
  and `inside.json`. M1-A-3 and M3 can call it the same way.

```
py -3.13 tooling/hd2d_m1b_scene.py all OUT     # build (Studio) + check (game); pictures, build.json, check.json
```

**Built only through Mesh Studio's own input events, in a hidden window.** That means button clicks, typing into
fields, mouse clicks and drags in the 3D view, and a right-click menu. It never writes room files. The steps:

1. `mesh new --template starter` (a 2D project).
2. **+ New room** > HD-2D, 32 x 32 m, Outdoors > Create. This also installs the starter kit, and the room's camera
   bounds come from the room. Then **Set as starting room**. The player is dragged to the south path.
3. **Models...** > search > **Place in scene** > click, then the inspector's X and Y typed, for each piece:
   - six *Platform (4 x 4 m)*: two plateaus 2 m up;
   - *Bridge (6 m)* between them;
   - two *Staircase*;
   - *Cottage*, with **See-through in play** turned on;
   - two *Lamp post*.
4. **Lighting** > **+ Add light**, three times: one at each lamp post's lantern (2.5 m up) and one under the deck
   (1.4 m up). Radius and height typed under **More settings**.
5. **Person** (the guard): clicked onto the grass, then dragged under the bridge.
6. Right-click inside the cottage > **Add door to a new room...** > HD-2D, 16 x 12 m, Indoors > Create (**Inside**).
   The door is then made a **Passage** (an invisible area, because the cottage model has its own door), 1.5 x 1 m.
7. In Inside:
   - its door is dragged and made a 1.5 x 0.5 m Passage;
   - *Cottage interior* is placed turned 180 degrees, with See-through on;
   - a lamp is added;
   - the room is saved.

**The geometry, in metres** (x east, y north; floors are named as the collision world names them):

| Part | Where | Floor |
|---|---|---|
| Ground | everywhere | `ground`, 0 m |
| West plateau | x 2–14, y 18–22 | `platform_4m{,_2,_3}/col_platform`, 2 m |
| East plateau | x 18–30, y 18–22 | `platform_4m_{4,5,6}/col_platform`, 2 m |
| Bridge deck | x 13–19; standable y 19.5–20.5 | `bridge_6m/col_deck`, 2 m |
| Stairs | x 11 and x 26; y about 12.5–17.5 | `stairs*/col_stairs`, then `col_landing` at 2 m |
| Underpass | x 14.5–17.5 at y 20 | `ground` under the deck |
| Guard (Person) | feet (15.5, 19.94), 0 m | ground, directly under the deck |
| Cottage | (6, 8), its south wall at y 6 | `cottage/col_floor`, 0.1 m |
| Cottage door | Passage at (6, 8), 1.5 x 1 m | arrival at (6, 5) |
| Inside | interior at (7, 5), turned 180° | `interior/col_floor`, 0.1 m |
| Inside door | Passage at (7, 9), 1.5 x 0.5 m | arrival (Studio's) at (8, 4) |

## Evidence

All pictures come from hidden windows at 1280 x 720. The numbers are from [check.json](check.json); the Studio
record is [build.json](build.json).

| Picture | What it shows |
|---|---|
| [studio_01_crossing](studio_01_crossing.jpg) | The Crossing in Studio's 3D view, as built: the plateaus, bridge, stairs, cottage, lamp posts, the guard under the deck and the player. |
| [studio_02_inside](studio_02_inside.jpg) | Inside in Studio: the turned interior (doorway in the far wall) and its lamp. |
| [01_ground](01_ground.jpg) | Play: the player on the ground at the start, (16, 3.94), 0 m. The lamps' light and shadows are visible. |
| [02_stairs](02_stairs.jpg) | Halfway up the west stairs: 1.27 m on `stairs/col_stairs`. The camera rises with the player. |
| [03_deck_above_guard](03_deck_above_guard.jpg) | On the deck at (15.53, 20.03), 2 m on `bridge_6m/col_deck`. The guard is underneath at (15.5, 19.94), 0 m on the ground: the same x/y, two elevations, and neither blocks the other. |
| [04_under_deck](04_under_deck.jpg) | Under the deck at (16.94, 20.03), 0 m on the ground, beside the guard. The same x/y 2 m up is `bridge_6m/col_deck`. The under-deck lamp lights the underpass. |
| [05_behind_cottage](05_behind_cottage.jpg) | Behind the cottage. The cutaway opens the roof: 1754 of 1754 player pixels are visible, against 0 without the cutaway. |
| [06_doorway](06_doorway.jpg) | At the cottage's doorway, just before walking in. |
| [07_inside](07_inside.jpg) | Through the doorway, in Inside (0.1 m, `interior/col_floor`). The south wall is see-through: 5230 of 5626 pixels visible, against 2872 without. |

**The walk.** Only held arrow keys move the player (press and release events into the window); positions are never set.
The route:

1. ground
2. west stairs
3. west plateau
4. the deck above the guard (saved: `m1b_deck`)
5. east plateau
6. east stairs down
7. under the deck (saved: `m1b_under`)
8. behind the cottage
9. the doorway, into Inside
10. Inside's doorway, back to the Crossing, arriving at (6, 4.44) on the ground

Then both saves are loaded. Each comes back at the same feet, elevation and floor (the deck: 2.0 m on
`bridge_6m/col_deck`; under it: 0.0 m on `ground`).

**The camera.** It followed the player over 1344 frames, and its picture of the ground never left the room's bounds.
The largest correction `fit_view` would have made was 0.0 m.

**The GPU test.** `tests/test_hd2d_m1b_scene_gpu.py` (opt-in with `MESH_GL_SMOKE=1`) runs the same build and walk in
one module fixture, without pictures or timing, and asserts each point above.

- With `MESH_GL_SMOKE=1`: 7 passed in about 69 s on this machine. The Studio build takes about 57–60 s of that.
- Without it: 7 skipped.

## Frame timing on this machine

This is a record of what was measured, not a benchmark. M1-B-2 covers the full report.

| | |
|---|---|
| CPU | AMD Ryzen 7 5700X3D 8-Core Processor (16 threads) |
| GPU | NVIDIA GeForce RTX 4070, OpenGL 4.6.0, driver NVIDIA 610.88 |
| OS | Windows 11 (10.0.26300), Python 3.13.3 |
| Picture | hidden 1280 x 720 window, vsync off |

**The walk:** the Crossing is reloaded, and the player walks right for 3 s and then left for 3 s from the start (360
frames, after 30 warm-up frames). Each frame is timed over update + draw + `ctx.finish()` + `ctx.gc()`. The renderer
drew 19 draw calls, 942 triangles, 3 lamps (2 with shadow maps) and 18 shadow draws per frame.

| Run | median ms | p95 ms | p99 ms | max ms |
|---|---|---|---|---|
| Evidence run (`check.json`) | 2.57 | 5.32 | 5.69 | 5.91 |
| 5 more walks, one process | 4.62 – 6.67 | 5.58 – 8.79 | 7.29 – 9.88 | 8.00 – 11.25 |

The spread between runs is large. Another worker was running tests on the same machine at the time, and the GPU's clocks
were not pinned. Every frame stayed under 12 ms, against a 16.7 ms budget at 60 Hz.

## Findings

1. **Studio gap (authoring, not the engine): arrival spots can't be picked in the HD-2D 3D view.**
   - A `spawn_point` has no picture and no marker there, so `Hd2dView.ids_under` never returns it. It can't be
     clicked or dragged.
   - Smallest repro: make a new HD-2D room with a door (its arrival is 3 m south of the door). `ids_under` at the
     arrival's screen point is `[]` at any height.
   - Workaround here: Inside is fitted round Studio's automatic arrival at (8, 4). The interior is turned so its
     doorway is in the far wall.
   - Not fixed: this is Studio work, outside this content task.
2. **Engine behaviour, already known (Milestone 17, `docs/reviews/milestone17_interior_door_trigger.md`): door areas
   are tested against the player's whole picture rectangle, not its feet.**
   - Walking north, a door fires when the top of the player's 48 px picture enters the area, about 1.3 m above the
     feet.
   - Measured: the cottage passage's near edge is at y 7.5, and it fired with the feet at y 6.36. Inside's is at
     8.75, and it fired at 7.66.
   - The template's fix (`area_at: "base"`) can't be set from Studio, and the N7 authority refuses base-anchored doors
     (`mesh_net/world.py:174`).
   - So both passages are ordinary centred areas, placed beyond the doorway's line so that they fire as the feet step
     into it. `mesh_net.world.Door.touches` uses the same picture-rectangle test, so the two runtimes agree.
   - Not fixed: it is shared with 2D games and the authority.
3. **Interaction across floors (expected; plan §1.4 and D8a).** On the deck, the player gets the guard's
   "E: Interact" prompt from 2 m above (visible in 03). Interaction is planar until M3-4.
4. **Camera, minor.**
   - `fit_view` keeps the ground plane inside the bounds. A player on a 2 m deck near the room's far edge is drawn
     at the top of the picture.
   - It was seen at a room depth of 26 m, and is fixed in content by 10 m of grass north of the plateaus (32 m deep).
     The renderer was not changed.
5. **Cosmetic.** Studio's new Indoors HD-2D room keeps the grass ground, so grass shows round the interior.
6. **The net authority still refuses both rooms.** It says "HD-2D rooms walk on 3D floors; this authority runs 2D
   collision only". M1-A-2 hasn't merged, so the plan's "passes the M1-A-2 authority load" check is still to do.
   The doors are centred passages, which the N7 door reader accepts.

No defect needed an engine change for this scene.

## Checks run (final tree, this machine)

| Command | Result |
|---|---|
| `MESH_GL_SMOKE=1 pytest -W error tests/test_hd2d_m1b_scene_gpu.py` | 7 passed (71 s) |
| `pytest -W error tests/test_hd2d_m1b_scene_gpu.py` (no GL) | 7 skipped, with the opt-in reason |
| `MESH_GL_SMOKE=1 pytest -W error tests/test_hd2d*.py` | 1074 passed, 1 skipped (12 min 24 s) |
| `pytest -W error` on the marker-policy tests (`test_fast_marking_policy_contract.py`, `test_tier_marker_ratchet.py`, `test_test_lanes_contract.py`, `test_gpu_fixture_env_isolation.py`) | 283 passed |
| `python -m tooling.ruff_gate` | ok |
| `python -m mesh_cli replays run --suite replays/suite.json` | 13 / 13 passed, 0 goldens updated |
