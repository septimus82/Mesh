# H-485A: Studio vs game HD-2D shadow parity (#485), investigation

Evidence only: branch `evidence/485-shadow-parity`, never merged. Baseline `redesign/visual-editor` @ `49c330d`.
The proposed correction (`proposed_fix.patch`) was tried in a scratch worktree only; no production change is
committed anywhere.

## Finding

#485's mechanism is **not** the sun's shadow fit. `Lighting.sun_vp` is `sun_matrix(sun, world_lo, world_hi)`:
an orthographic box around the room, with no camera input. This was already the case at `0fa2f25`, where #485 was
filed. Across every probe, the sun view-projection never changed, whatever the game camera did.

**Root cause.** The renderer stands its billboards up with the drawing camera's *right* vector but the **game
camera's pitch**:

- `Hd2dRenderer.draw()` computes `stretch = 1 / cos(self.camera.pitch)`. `self.camera` is the renderer's own
  (game) camera even when Mesh Studio passes `camera=`.
- That stretch is used by:
  - characters, signs and doors (`_sprite_quads`): their upright quads, drawn in the picture and into the sun's
    shadow map;
  - tree canopies cast into the sun's map (`scatter.draw_casters`);
  - grass, flowers, bushes and reeds (`scatter.draw_sprites`) and campfire sprites (`fire_sprites.draw_sprites`).
- `dof_focus` also uses `self.camera.pitch`. It is only reached with `cam is self.camera` today, so it has no
  effect now.

The game camera's pitch is the room's (30° outdoors and 55° in the cottage in the template). Studio's is its own
(40° by default, adjustable 15–85°). So Studio draws billboards, and their sun shadows, at the wrong height for its
own view. They also change when the unseen game camera's pitch changes.

The 0.23% in #485 came from #483's study moving all the game camera's fields to Studio's at once. **Only the pitch
mattered**: the same 1,077 pixels change with pitch alone, and 0 change with every other field moved
(`all_but_pitch_to_studio`).

The changed pixels are the billboards themselves (886 of 1,077 with sun shadows off) plus their sun shadows (sun
map texels change through `sprite_quads` and canopy casters only). Structure shadow edges are not involved; see
`pictures/village_game_pitch_change_base.png`.

The camera-dependence dates from M16 Stage 2 (`2f76899`); M20D (`0280765`) carried it into scatter.

## Reproduction (RTX 4070 and Mesa llvmpipe give the same shares)

`scripts/probe485.py` opens a fresh `hd2d_rpg` project in Studio (hidden window). It freezes motion, weather,
water and the player, then changes **one** unseen game-camera property at a time under a fixed Studio camera.

Instrumented each time:

- Studio's picture;
- the sun VP and every sun shadow-map texel (via `glGetTexImage`);
- the character billboard vertices;
- the canopy-caster and scatter-sprite right vector and stretch;
- the fires chosen, the cameras, `last_vp`;
- live GL objects.

Results:

| room (pose) | changed by game **pitch** → Studio's (base) | target, yaw, fov, distance, ortho, aspect, ready | after the fix |
|---|---|---|---|
| village, default (#485's case) | **0.230%** (1,077 px) | 0 | 0 |
| village + trees/meadow (scratch scatter) | **8.1%** | 0 | 0 |
| cottage (interior, game pitch 55°) | **30.4%** | 0 | 0 |
| moving Studio camera (orbit 35°, orbit −60° at pitch 25°, pitch 65° zoomed, pan), 3 rooms | up to 12% (cottage), 10.5% (scatter) | 0 | 0 in every pose |

Data: `data/{rtx,mesa}_{base,fix}_probe_*.json`. With a matching camera, the game path and Studio's path were
byte-identical in every case, on base and fix.

`scripts/minimal_repro.py` (village, Studio fixed, game camera pitch +30° only) prints:

- base: 0.9915% of the picture changed, sun VP unchanged;
- with the fix: 0.0000%, sun VP unchanged.

Results are identical on the RTX and Mesa.

## Proposed correction (smallest; `proposed_fix.patch`, `engine/hd2d/renderer.py` only, +10 −8)

Billboards stand up for **the camera drawing the frame**:

- `draw()` computes `stretch` from `cam.pitch`, where `cam` is `camera or self.camera`, as `right` already comes
  from `cam`;
- it passes that one stretch to `_sprite_quads` (new keyword `stretch`), the canopy casters and the scatter and
  fire sprites;
- `dof_focus` uses `cam.pitch`.

The shadow system, shadow resolution, sun fit and lighting are not touched.

In play, `cam is self.camera`, so every value is unchanged.

## Validation of the correction (scratch worktree)

| check | RTX 4070 | Mesa llvmpipe |
|---|---|---|
| gameplay frames, base vs fix (HiddenGame, game camera; village, cottage, village+scatter; settled + 24 moving-camera frames + arrived; 78 frames, all distinct) | byte-identical (2 base + 2 fix runs) | byte-identical |
| fixed Studio camera, unseen game camera moved (pitch, every field), probe: 3 rooms × 5 poses × shadows on/off | 0 px changed, all cases (base: up to 30%) | 0 px |
| Studio's own canvas (`view.draw()`, read from the window), game camera pitch 60 / moved far away | 0 / 0 (base: up to 19.6% / 38.7%) | 0 / 0 |
| game path vs Studio path, same camera and state | identical | identical |
| live GL objects (all kinds) after each case and at the end | flat; identical to base | flat; identical to base |
| renderer and DoF unit tests (124) | pass | — |
| full `gl` GPU suite, `-W error` | 442 passed + 1 skipped, same as the 49c330d tree; no outcome changes; test time +0.9% | — |

Campfire sprites take the same `stretch` but are not in these rooms, so they were not exercised here.

**Intended visible change, Studio only.** Studio's default picture changes where billboards are in view: village
0.23%, village+scatter 8.1%, cottage 30.4%. Its billboards and their sun shadows now have their drawn proportions
for Studio's own pitch. Before, they were stretched for the room's pitch: the cottage door was about 1.34× too
tall and hid the character behind it (`pictures/studio_canvas_base_vs_fix_*.png`: base | fix | changed in
magenta). That is the same picture the game draws from that camera.

## Scripts

`scripts/`, Python 3.13, run from anywhere with `WORKTREE` as the first argument. `--mesa` needs
`mesa_preload.py` beside them with a Mesa `mesa/x64` copy.

- `probe485.py WORKTREE OUT [--room start|cottage] [--scatter] [--poses] [--mesa]`, summarised by `summ485.py`.
- `exact485.py WORKTREE PROJECTS OUT.json`, compared by `cmp_exact.py`.
- `studio485.py WORKTREE PROJECTS OUT`.
- `minimal_repro.py WORKTREE`.
