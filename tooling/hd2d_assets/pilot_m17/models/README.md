# M17 pilot: cottage_m17.glb

The starter cottage (`assets/hd2d_starter/models/cottage.glb`) re-dressed with the PixelLab candidates in
`../textures/`. An art-direction experiment for `tooling/m17_visual_pilot.py`, which swaps it in under the structure
id `cottage`. Nothing in the starter kit was changed.

Build (headless, from the repo root):

    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/pilot_m17/build_cottage_m17.py -- tooling/hd2d_assets/pilot_m17/models/cottage_m17.glb

Built with Blender 5.2.0 LTS (glTF I/O v5.2.39). The build is deterministic. `provenance.json` has hashes, the
PixelLab call for each texture (full records in `../textures/provenance.json`) and the starter assets reused.

## Differences from the starter cottage

The script calls `build_cottage.build()` unchanged and then re-dresses the result:

| | Starter | Pilot |
|---|---|---|
| Lower walls | timber, 0.1-1.3 m | `stone_b_seamfix`, 0.1-0.9 m (the drawn split moved down; wall boxes otherwise identical) |
| Floor slab's outer edge (0-0.1 m) | timber | `stone_b_seamfix`, so the plinth reaches the ground |
| Upper walls, gable ends | starter `plaster` (baked 0.16 m timber band under every whole metre), from 1.3 m | starter `plaster`, same 1 tile per metre, from 0.9 m. The band at 0.84-1.0 m is hidden by the sill beam; the one at 1.84-2.0 m runs along the window heads, level with the lintel's underside |
| Roof slopes | `shingles`, UVs projected flat (27.9 px/m along the slope) | `roof_slate`, UVs along the slope (32 px/m) |
| Lintel, floor top | timber, floorboards | unchanged |
| Framing (new, drawn only) | none | starter timber: 4 corner posts (0.9-2.5 m, 4 cm proud), a 0.15 m sill beam on the plinth (3 cm proud, stopping at the door jambs), 2 door jambs (0.15 m wide, 4 cm proud, outside the 1.2 m opening) |
| Windows (new, drawn only) | none | two `window_a` decals, 0.81 x 0.91 m, 1 cm out of the south wall, centred in each 1.9 m span beside the doorway (x = +/-1.55 m), 1.1-2.006 m. Clear of the door sprite (which covers \|x\| <= 0.75 m) and of the jambs |
| Door | open doorway | unchanged (door is a separate sprite entity) |
| Collision | 7 `col_` nodes | identical (byte-identical vertex and index data) |
| Triangles (drawn) | 152 in 26 parts | 288 in 50 parts |
| Overall bounds | 5.6 x 4.6 x 3.8 m | same |

Every texture is at 32 px per metre (64 px tiles repeat every 2 m, the 32 px starter textures every 1 m), sampled
NEAREST, embedded pixel-identical to its source PNG.

## Tried and rejected

- `plaster_b` (iteration 1): in game, its one bold crack read as a large scribble repeating every 2 m on a flat field;
  a step down from the starter plaster. Iteration 2 uses the starter plaster.
- East and west windows (iteration 1): the game camera only sees the south face, so they never showed. Dropped.
