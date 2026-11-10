# H-485B: Studio HD-2D billboards stand up for the camera drawing the frame (#485)

Baseline `redesign/visual-editor` @ `14e9d4f`. Its HD-2D renderer is identical to H-485A's `49c330d`: only the
networking merge came in between. Diagnosis: `evidence/485-shadow-parity` @ `39a71d8`
(`docs/reviews/h485_shadow_parity/`, never merged).

## Change

`engine/hd2d/renderer.py`, the approved reference patch unchanged:

- `draw()` computes the billboard stretch once, `1 / cos(cam.pitch)`, where `cam = camera or self.camera`. Before,
  it used the renderer's own game camera, `self.camera.pitch`, even when Studio passed its own camera.
- That one value goes to:
  - character, sign and door billboards (`_sprite_quads`, which now takes it as the keyword `stretch`, with no
    fallback);
  - the tree-canopy sun-shadow casters;
  - scatter decoration;
  - campfire billboards.
- `dof_focus` measures the followed character with the camera it is given.

The sun matrix, shadow resolution, lighting, projection and models are unchanged. In play `cam is self.camera`,
so every value is unchanged.

**Read but deliberately unchanged:**

- `_bind_cutaway(game_camera.pitch)` belongs to play's roof cutaway; Studio passes none.
- Studio's mouse picking (`studio_hd2d._under`) already used Studio's own pitch for the billboard stretch. Picking
  now matches what is drawn; before, it picked a billboard shape the picture didn't show.

## Pictures (RTX 4070; Mesa llvmpipe gives the same hashes and shares)

| picture | shows |
|---|---|
| `pictures/studio_canvas_cottage_before_after.png` | Studio's real canvas, before, after and changed (magenta): 30.4% of the canvas. The door, stretched for the room's 55° instead of Studio's 40°, was 1.34× too tall and hid the character and table behind it. |
| `pictures/studio_canvas_village_decor_before_after.png` | Village with trees, a meadow, a campfire and a raised hill: 8.2%. Trees, grass, flowers, the fire and the canopy shadows now stand for Studio's 40° pitch instead of the room's 30° (slightly taller). |
| `pictures/studio_canvas_village_before_after.png` | Template village: 0.23%, the #483 number (Elder, sign, door to the cottage, and their shadows). |
| `pictures/no_billboards_*.png` | The same canvas with every billboard left out: structures, roofs (11 cutaway structures in the village), terrain, lamps and ground. Byte-identical before and after, in all three rooms, on both GPUs. |
| `pictures/matched_*_game_vs_studio.png` | Play's own camera (following the player at the room's pitch: 30° outdoors, 55° in the cottage), with Studio's camera set to it. The game's path and Studio's path give byte-identical pictures, before and after; the fix's equal the baseline's. The GPU test checks this pose as well as four Studio poses. |

## Gameplay preservation (byte-exact against `14e9d4f`)

`scripts/gameplay485b.py` (HiddenGame 960×540, the game's own draw path) covers the village, the cottage and the
decorated village (trees, meadow, campfire, player beside it). Each room has two settled frames, 24 walking frames
with the camera following, and an arrival frame: 81 frames per run.

| | RTX 4070 | Mesa llvmpipe |
|---|---|---|
| frames (hash, draw calls, framebuffer binds, camera target) | identical; 2 baseline + 2 fix runs, 324 frames | identical; 5 + 5 runs, plus 3 + 3 run from one directory: 1,296 frames |
| draw calls per frame | 32 / 7 / 57–59 | same |
| render passes (framebuffer binds per frame) | 12–18, the same frame by frame | same |
| GL objects created while walking, and live at the end | identical | identical |

## Performance (gameplay frame time, draw + finish, median ms)

| room | RTX baseline | RTX fix | Mesa baseline vs fix, same directory (3 + 3 runs) |
|---|---|---|---|
| village | 5.73 / 5.69 | 5.58 / 6.35 | ratio 1.002 |
| cottage | 3.48 / 3.48 | 3.47 / 3.12 | ratio 0.937 |
| village + decor | 9.00 / 8.94 | 9.01 / 9.05 | ratio 0.980 |

Running the two trees from different worktree folders on Mesa showed the village about 13% apart. Running both from
the same folder showed none, so that gap belonged to the folder, not the code. That fits gameplay doing the same
arithmetic with the same values.

## Tests

- `tests/test_hd2d_billboard_camera.py` (CPU):
  - a billboard's height is `drawn height / cos(drawing pitch)` whatever the game camera's pitch;
  - `_sprite_quads` has no fallback stretch;
  - the DoF focus uses the camera it is given.
- `tests/test_hd2d_billboard_camera_gpu.py` (GPU), in the village, the decorated village (trees, meadow, campfire)
  and the cottage:
  - a fixed Studio camera's picture and sun shadow map are byte-identical while the unseen game camera's pitch, or
    every field, changes, with shadows on and off;
  - character, scatter, canopy-caster and campfire billboards all get Studio's stretch;
  - character billboard heights are measured from the geometry;
  - game/Studio parity at 4 Studio poses (pitch 25 and 65, orbit, zoom) and at play's own camera (room pitch 30 or 55);
  - repeating everything allocates no GL objects;
  - in play (walking and still), every billboard follows the game camera.
- **Proof that the tests catch the mistake:**
  - on the unfixed `14e9d4f` the GPU tests fail 9 of 14: independence, heights and parity;
  - the play and GL tests pass there, as they should;
  - two mutations of the fixed tree are caught:
    - `_sprite_quads` ignoring the stretch for `self.camera.pitch`: CPU 5/7 and GPU 9/14 fail;
    - `draw()` back on `self.camera.pitch`: GPU 9/14 fail.

## Evidence scripts

The one-off measurement scripts aren't committed, since repository policy tests scan every `.py` file. They extend
H-485A's (`evidence/485-shadow-parity`, `docs/reviews/h485_shadow_parity/scripts/`):

- `gameplay485b.py` records gameplay frames, draw calls, framebuffer binds, GL counts and frame time;
- `cmp485b.py` compares those runs;
- `studio485b.py` captures Studio's canvas, the canvas without billboards, and the matched game/Studio pictures.

Their outputs are in `data/`. The permanent checks are the two tests above.
