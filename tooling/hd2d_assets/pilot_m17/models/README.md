# M17 pilot cottages (Stage 1B)

The starter cottage (`assets/hd2d_starter/models/cottage.glb`, variant A) with improved geometry, in two texture sets,
so the geometry gain and the texture gain can be judged separately. `tooling/m17_visual_pilot.py compare OUT --set
cottage` swaps each in under the structure id `cottage`. Nothing in the starter kit was changed.

| | File | Images |
|---|---|---|
| B | `cottage_m17_geo.glb` | starter only: cobbles plinth, plaster, timber, shingles, floorboards; flat dark-glass panes (no image) |
| C | `cottage_m17.glb` | the same, except `stone_b_seamfix` on the plinth and `window_a_glass` in the panes |

Build (headless, from the repo root; each build is reproducible byte for byte):

    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/pilot_m17/build_cottage_m17.py -- tooling/hd2d_assets/pilot_m17/models/cottage_m17_geo.glb --set starter
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/pilot_m17/build_cottage_m17.py -- tooling/hd2d_assets/pilot_m17/models/cottage_m17.glb --set pixellab

`../textures/window_a_glass.png` comes from `py -3.13 tooling/hd2d_assets/pilot_m17/make_window_glass.py`. It is
window_a.png with its 107 cream pane pixels set to the window's own dark blue-grey. Blender 5.2.0 LTS (glTF I/O
v5.2.39). `provenance.json` has hashes, sources and the exact edits. Stage 1's record is kept there, marked
superseded.

## Geometry (B and C), compared with the starter

- **Plinth.** The stone/plaster split is at 0.85 m instead of 1.3 m. The floor slab's 0.1 m edge uses the plinth
  material.
  - The plinth's V offset puts its top on a mortar line (stone row 11) or a gap row (cobbles row 0).
  - The stone's broken mortar rows 41-43, with their stray highlight, stay off the wall.
- **Hidden faces removed.** These are each wall box's top and bottom, and the lintel's ends and top. They used to sit
  coplanar with other materials (floor, other box, roof underside, walls), and the cutaway shows them. The starter has
  60 such overlapping triangle pairs; B and C have 0.
- **Framing**, in starter timber, wholly outside the walls (1 cm clear) and never inside the room:
  - a sill ring, 0.85-1.0 m, 4 cm deep, open at the doorway;
  - four L-shaped corner posts, 6 cm deep, with vertical grain.

  The sill covers the starter plaster's baked band at 0.84-1.0 m. The band at 1.84-2.0 m reads as a head beam level
  with the lintel.
- **Two modelled windows** on the south wall, centred in each 1.9 m span (x = +/-1.55 m), 1.125-1.719 m:
  - a pane 2 cm out of the wall;
  - a timber frame and cross mullion 2.5-6 cm out, with vertical grain on the uprights;
  - the layout and size of window_a.png's opening at 32 px/m (0.5 x 0.59 m).
- **Roof.** Starter shingles, with UVs along the slope at 32 px/m (the kit's flat projection gives 27.9) and the image
  upright, read from outside. The darkest gap row ends at the eave.
- **Removed:** the Stage 1 door jambs, which sat behind the 1.5 m door sprite.
- **Unchanged:** collision (byte-identical), the doorway, lintel, floor and bounds (5.6 x 4.6 x 3.8 m).

Drawn triangles: 152 in the starter, 402 in B and C.
