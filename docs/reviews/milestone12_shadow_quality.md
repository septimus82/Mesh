# Milestone 12: Physically Coherent 2D Lighting & Shadow Rendering

**Goal:** a shadow blocks the light that casts it, and nothing else. It never paints darkness over the finished
scene, never removes the room light, and never touches another lamp's light.

Branch `redesign/visual-editor` (draft PR #344, unmerged). Commits: see "Commits" at the end.

## Stage A: how lighting worked, and why shadows were wrong

**The lighting pass.**
- Both the game (`game_runtime/tick.on_draw`) and Mesh Studio's edit view draw a room inside
  `lighting.begin()` and then call `lighting.end()`, so they share one renderer.
- `begin()` redirects drawing into Arcade's `LightLayer`, a diffuse render target.
- `LightLayer.draw()` adds every point light into an 8-bit light buffer in one instanced, additive draw. A light's
  falloff is `1 - distance + attenuation` (Mesh's lights are "soft": attenuation 0).
- It then combines: `final = diffuse * ambient / 255 + diffuse * lights`.

**The active hard-shadow path** was `shadow_pipeline.end_hard_shadows_overlay`.
- It drew the lit scene, then filled shadow polygons in black at alpha 180 *on top of it*.
- The polygons were cast from one light, chosen by `shadow_selection.select_shadow_light`: the player's carried
  light, else the first light.
- So a shadow darkened the room light under it, and every other lamp's light there. It even appeared where its own
  light didn't reach: lamp B's shadow fell across ground lit only by the room light.

**The framebuffer composite path** (`end_hard_shadows_composite` with `hard_shadows_backend.py`) is unreachable;
nothing calls it.
- Its formula is right for one light: `ambient_part + (lit - ambient_part) * mask`.
- Its mask is global and built for one chosen light, so it would still remove every lamp's light inside one lamp's
  shadow. It also assumes the clamped 8-bit light buffer can be split back into ambient and lamps.
- Adapting it would have meant replacing the one part that matters (one mask for all lights). It was not reused.

**The GL stack.**
- Arcade 3.3.3 on OpenGL 4.6, NVIDIA GeForce RTX 4070. Timer queries, scissor, half-float textures and depth
  textures are available.
- Arcade itself needs GL 3.3. The new renderer uses only GL 3.3 core features: framebuffers, blending, depth testing.

**Baseline** (`tooling/shadow_bench.py --renderer legacy`, flat grey floor, exact pixels; evidence:
`milestone12_evidence/bench_before_legacy_overlay.json`):

| Example | Probe | Legacy overlay | Correct |
|---|---|---|---|
| A: one lantern, one wall | behind the wall | (12, 12, 16) | the room light alone, (25, 25, 38) |
| B: two lanterns | behind the wall, lit by B | (14, 15, 19) | lantern B alone, (32, 34, 51) |
| B with only lantern B | open floor across from B | (7, 7, 11) | the room light, (25, 25, 38) |
| C: no lights | anywhere | (25, 25, 38) | the same (no light was chosen) |
| D: daylight | behind the wall | (41, 41, 40) | daylight, (125, 125, 119) |

Legacy lighting pass, measured: 0.3–1.0 ms CPU and 0.02–0.04 ms GPU per frame. It shadowed one light only.

## Decision: per-light occlusion masks (the smallest robust fix)

    final = diffuse * (ambient + sum over lights of light_i * (1 - occlusion_i))

`engine/lighting/light_compositor.py` replaces only `LightLayer.draw()` when shadows are on. The scene still
renders into the LightLayer's diffuse target, unchanged.

1. **Lights with nothing to block** (no wall within reach, or set not to cast shadows) are added together in one
   instanced draw. It uses Arcade's own falloff shader code and the same 8-bit buffer, so they look exactly as
   before.
2. **Each light that casts shadows**, nearest the middle of the view first:
   - its shadow polygons go into an occlusion mask (a half-float texture);
   - the light is added scaled by `1 - mask`;
   - so its shadow removes its own light and nothing else.
3. **Combine:** Arcade's own combine maths, so the room light is present everywhere.

**Why this and not alternatives:**
- A stencil buffer would need a depth-stencil attachment Arcade doesn't offer.
- A visibility-polygon light per lamp would be a second light model.
- Patching the overlay's colour can't make it right: it acts after the lights are summed.

**Budget and honesty.**
- Up to 16 shadow-casting lights per frame. The rest are drawn lit, without shadows, and the stats say how many
  (`lights_over_budget`).
- Lights entirely off screen are skipped.
- If the GPU can't build or run the renderer, the room is drawn lit without shadows. The stats carry
  `shadows_unavailable` with the reason, and the event is logged once. It never falls back to black overlays.
- The pre-Milestone-12 overlay stays selectable with `MESH_SHADOWS_RENDERER=legacy`, for comparison only.

## Stages B–D: what was built

**Correct compositing for one light, then for many** (`e979ed4`):
- `engine/lighting/light_compositor.py` and its hook in `LightManager._end_frame`.
- Lights with nothing to block go in one instanced draw. Each shadow-casting light has its own mask.

**Geometry** (`91e354a`, `201edf9`): `shadows.light_shadow_polygons`.
- Every edge facing away from the light throws an arc-ended shadow, for rectangles and polygons alike. A wall never
  shadows itself; a wall behind it is still shadowed.
- All of a light's shadows end on one arc beyond the farthest corner in play, so shadows meeting along a ray share
  end points: no cracks.
- An occluder that contains the light casts nothing.
- The old builders (one chord per rectangle; straight-ended polygon quads that left a lit wedge) remain for the
  legacy overlay only.

**Soft edges** (`201edf9`): the lamp is treated as a small disc.
- A soft shadow averages the shadows seen from 12 ("soft", disc 10 px) or 16 ("softer", disc 22 px) points on it.
- So the edge is sharp where the shadow touches the wall and widens with distance: a penumbra, not a blur. The room
  light stays in the core.
- Each sample's triangles carry their own depth, so overlapping shadows of one sample count once. Joined wall tiles
  cast exactly the shadow of one wall.
- All of a light's samples are one cached array and one draw.

**Room and light settings:**
- `lighting_shadow_softness` per room (`sharp`, `soft`, `softer`), with the project's as fallback (new config key,
  default `sharp`).
- `"shadows": false` on a light makes it shine through walls.
- Canonical ops: `set_room_lighting(softness=…)` and `set_light(shadows=…)`. Undoable, saved, and available to AI
  authoring through the same path as every lighting edit.
- **Fixed on the way:** a room without its own shadows setting kept the previous room's. It now follows the
  project's, unless `MESH_SHADOWS_MODE` overrides it.

**Studio** (the same renderer as Play; no Studio-only lighting):
- Lighting panel: **Shadow edges: Sharp / Soft / Softer**.
- Per light: **On** (switch it off without deleting it) and **Casts shadows**.
- The panel's note now reads: "Walls on the map block each light: a wall's shadow takes away only that light,
  never the room light."

## How to try it

1. Start `Mesh Engine.bat` and open or create a game.
2. In a room with walls, click **Lighting**, then **On**, choose a room light (e.g. **Night**), and **Shadows on**.
3. **+ Add light** twice, on either side of a wall.
4. Behind the wall each lamp's light is cut, but the room light and the other lamp's light remain.
5. Try **Shadow edges: Sharp / Soft / Softer**, a light's **On** and **Casts shadows**, and F4 to play.
6. For the old look, start with `MESH_SHADOWS_RENDERER=legacy`.

## Verification

**Exact pixels** (GL-gated; `MESH_GL_SMOKE=1`, and run by the lab inside the runtime gate):
- `tests/test_shadow_compositing_gpu.py`, 16 tests:
  - examples A–D;
  - shadows off is identical, pixel for pixel, with nothing to block;
  - a lamp with `"shadows": false`;
  - the over-budget path;
  - scroll and zoom;
  - the GPU-failure fallback;
  - soft cores keep the room light;
  - joined tiles equal one wall when soft;
  - the penumbra is narrow at the wall and wider far away.
- `tests/test_shadow_geometry_gpu.py`, 10 tests. Every floor point on a grid is classed by a ray test:
  - a lit point must equal shadows-off;
  - a blocked point must equal the room light alone.
  - Scenes: an L corner, a diagonal wall, a short block, a wall past the reach, a lamp against a wall and by a
    corner, joined tiles, a pentagon, a lamp by a long slanted wall, and a lamp moving past a pillar in six steps.
  - **0 wrong points.** The legacy overlay fails every scene (18–466 wrong points each). The old polygon builder
    leaves 370 points lit beside the slanted wall.

**Real window: the Shadow Quality Lab** (`tooling/shadow_lab.py`, in the runtime gate as `shadow_lab`):
- A disposable four-room project built with the engine's operations, opened in Mesh Studio, driven by OS-level
  input.
- Every visual check compares the window's pixels at the same place under two settings, so the floor texture
  cancels out.

| # | Required | Lab check (new renderer) | Result | Legacy overlay, same check |
|---|---|---|---|---|
| 1 | One point light, no occluders | Even all round (99–105 at 60 px), falling with distance (109 → 31) | PASS | not judged (an outside cursor lock refused the click) |
| 2 | One wall casts a hard shadow | Lamp side 152 vs behind the wall 36 | PASS | PASS |
| 3 | Ambient stays in that shadow | Behind W1, lamp A only = no lamps, exactly (35.6, 29.0, 26.2) | PASS | **FAIL**: 27.7, darker than the room light |
| 4 | Two lights on one area | Both brighter than either alone | PASS | PASS |
| 5 | A wall blocks only one lamp | R with both lamps = R with only B | PASS | **FAIL**: 38.2 vs 72.2 (B's light erased) |
| 6 | A second wall blocks the other | S with both = S with only A | PASS | **FAIL** |
| 7 | Disable one lamp, the other unaffected | B's contribution the same with A on and off (per light **On** toggle) | PASS | PASS |
| 8 | Move a light; its shadow moves | Lamp dragged 3 tiles; 242 points by ray test, 0 wrong | PASS | **FAIL**: 21 wrong, shadow darker than the room light |
| 9 | Flicker without detachment | Behind the wall stays exactly the room light over 8 frames; lit side varies by 13 | PASS | **FAIL**: drops to 28.8 vs 35.6 |
| 10 | A wall crossing the reach | Beyond the reach nothing changes (18 points) | PASS | **FAIL**: shadow beams past the reach |
| 11 | A corner, no malformed beam | L corner, part of the 264-point ray-test check, 0 wrong | PASS | **FAIL** |
| 12 | A diagonal / polygon occluder | Slanted wall (entity `occluder_poly`), in the same check | PASS | **FAIL** |
| 13 | Camera scrolling | Play: R, S, lamp side the same after the camera follows the player | PASS | PASS |
| 14 | Camera zoom | Studio zoomed to 1.42: the same values | PASS | **FAIL** |
| 15 | Room change and return | The Open room shows only its own lamp; back: the same pixels | PASS | PASS |
| 16 | Lighting off and on | Off: the floor as drawn (106); on: back to the same pixels | PASS | **FAIL** |
| 17 | Save and reopen | Soft edges set in the panel, saved, Studio closed, reopened: 0 difference | PASS | PASS |
| 18 | Studio preview = Play | Edit vs Play at the same places: within 1 level | PASS | PASS |
| 19 | No lamps: no darkening | Shadows on vs off, 24 points: 0 difference | PASS | PASS |
| 20 | Performance vs before | See Performance | PASS | measured |

New renderer **14/14** (the 20 items plus the GPU pixel tests). Legacy overlay **6/13**: it fails exactly the checks
about what a shadow does to light. Before/after screenshots of the same views:
- `b1_lamp_a_only_before_after.png`;
- `b2_two_lamps_before_after.png`;
- `b3_corner_reach_slant_before_after.png`;
- `b4_play_before_after.png`.

What they show:
- **Before:** black shapes across the floor and over the walls, darker where two overlap, walls darkened by their
  own shadow, beams past the light's reach.
- **After:** the room's blue night light everywhere a lamp can't reach, walls lit on their lamp's side, each
  shadow cut from its own lamp's light.

## Performance

**Test machine:** Windows 11, NVIDIA GeForce RTX 4070, OpenGL 4.6, Arcade 3.3.3, Python 3.13. `MESH_LIGHTING_PROFILE=1`
times `lighting.end()`: CPU wall time, and a GL timer query for the GPU.

**Bench** (`tooling/shadow_bench.py`, 640x480, 240 frames). Lighting-pass time in ms:

| Scene | New CPU | New GPU | Legacy CPU | Legacy GPU | Shadowed lights (new / legacy) |
|---|---|---|---|---|---|
| One light, 3 walls | 0.56 | 0.02 | 0.85 | 0.02 | 1 / 1 |
| 5 lights overlapping, 3 walls | 1.04 | 0.07 | 0.41 | 0.02 | 4 / 1 |
| Crowded: 10 lights, 42 pillars | 2.07 | 0.18 | 1.02 | 0.04 | 10 / 1 |
| Crowded at zoom 2 | 1.72 | 0.14 | 1.00 | 0.04 | 8 / 1 |
| Crowded, soft | 2.61 | 0.43 | (no softness) | | 10 / 1 |
| Crowded, softer | 3.07 | 0.61 | (no softness) | | 10 / 1 |
| 5 lights, shadows off | 0.31 | 0.03 | 0.29 | 0.02 | 0 / 0 |

**Real window** (Shadow Lab in Mesh Studio, 1280x720, CPU / GPU ms):

| Room | New (final, with scissor) | New (before scissor) | Legacy overlay |
|---|---|---|---|
| Two lamps, sharp | 2.17 / 0.36 | 2.18 / 0.57 | 1.64 / 0.11 |
| Two lamps, soft | 2.39 / 0.69 | 2.78 / 1.06 | – |
| Two lamps, softer | 2.62 / 0.83 | 2.98 / 1.42 | – |
| Shapes (one lamp, 9 occluders) | 1.97 / 0.26 | 2.21 / 0.69 | 2.50 / 0.16 |
| Open (one lamp, border walls) | 1.76 / 0.24 | | |
| No lamps | 1.47 / 0.13 | 1.55 / 0.13 | |

The final column is the combined runtime gate's run. The scissor (`7ea4894`) limits each shadowed light's mask
clear and fill to its own square on screen; it cut the real-window GPU time by about 40%.

**Reading it:**
- The new renderer costs more because it does more: every light in view casts its own shadow, where the old one
  shadowed one light and painted it over everything.
- Per shadowed light it adds roughly 0.1 ms CPU (Python: gather, cached triangles, a few GL calls) and, at 720p,
  0.05–0.25 ms GPU. Soft edges add GPU fill (12 or 16 shadow passes in one draw).
- Static lights and walls are cached: a light's triangles are rebuilt only when it moves.

**Limits:**
- 16 shadow-casting lights a frame (`LightManager.shadow_light_budget`), nearest the middle of the view first.
- Beyond that, lights are drawn lit without shadows, and the stats report `lights_over_budget` (logged once).
- Lights entirely off screen are skipped.

## Remaining limitations

- **Softness has light banding** in "softer" on wide penumbrae (16 samples), seen in the comparison picture
  `e1_sharp_soft_softer.png`. More samples cost GPU fill.
- **Overlapping occluders' self-shading.** Separate occluder rectangles that touch, such as hand-made `occluders`
  entries, shade each other's tops along their shared edge. Painted wall tiles are merged into one rectangle first,
  so Studio maps don't show this.
- **Shadows fall on the ground plane only.** A wall's own face is lit by any lamp on its side; there is no height.
  That is the 2.5D elevation system, out of scope.
- **The pause menu's "Soft Shadows" setting still does nothing.** It fed only the unreachable composite path.
  Softness is the room's or project's setting.
- **Studio has no tool to draw a polygon occluder.** The engine reads entity `occluder_poly` and scene `occluders`;
  the lab writes one directly.
- **Post-processing:** like Arcade's LightLayer, the lighting pass draws to the window. Lighting with the
  post-process pipeline was not examined.
- **Known from Milestone 11, unchanged:** a loaded save reports the save file as its scene path. It didn't block
  verification: the lab tells rooms apart by their lamps.
- **CPU cost per shadowed light is Python.** A room with many moving lights pays it every frame.

## Engine changes: reused, replaced, retired

**Reused:**
- Arcade's LightLayer, as the diffuse target and for unshadowed rooms.
- Its falloff and combine maths, copied into the compositor's shaders.
- The occluder builders (tile walls merged into rectangles; entity `occluder_poly`).
- `cull_occluders_for_light` and `_shadow_behind`.
- The existing room settings and lighting ops.

**Replaced** (when shadows are on): `end_hard_shadows_overlay` (black polygons over the lit scene, one chosen
light). `light_compositor.render_shadowed_lighting` does the job now.

**Kept, not deleted:**
- `MESH_SHADOWS_RENDERER=legacy` selects the old overlay, for the before/after comparison.
- The unreachable composite path, `direct` mode and `shadow_selection` are unchanged.
- The legacy and composite paths can be retired once the owner has seen the new shadows (listed in
  `MESH_SALVAGE.md`).

## Regressions

- **Runtime gate, one combined run, no retries: 11/11 suites.**

  | Suite | Result |
  |---|---|
  | first workflow | 15/15 |
  | map building | 23/23 |
  | map tools | 15/15 |
  | launcher | 20/20 |
  | event authoring | 17/17 |
  | AI co-authoring | 14/14 |
  | persistence | 12/12 |
  | lighting | 15/15 |
  | creator | 21/21 |
  | **shadow lab** (new) | **14/14** |
  | capability lab | 36/36 |

  The lighting suite of Milestone 10 still passes as it was: its shadow check reads "darker behind the pillar than
  in the open", which the new renderer meets without the black.
- **Full suite:** 9,400 passed, 34 skipped (the GL-gated tests skip without `MESH_GL_SMOKE`), 4 failed on the
  first run:
  - 3 import-policy tests (Arcade reached directly instead of through `optional_arcade`);
  - the type-ignore ratchet.
  - All fixed in `b693cfe`, and their files pass.
- **Slow/e2e:** 34 failed. The Milestone 9 known 31, plus 3 tests that pinned the old overlay as the hard-shadow
  path. Those now select the overlay explicitly (`MESH_SHADOWS_RENDERER=legacy`) and pass, so the known list is
  not extended.
- **GL-gated pixel tests:** 26/26, run by the lab inside the gate.
- **Ruff gate and mypy island:** clean. **Type gate:** 259 beyond the baseline, the same as after Milestone 11.
- **Contract baseline moved:** `test_pipeline_lighting_no_silent_pass_contract.py` pins exception handlers in
  `engine/lighting/__init__.py` by line number. It now lists the same handlers at their new lines; none was added
  or removed.

## Commits

| Commit | What |
|---|---|
| `e979ed4` | Shadows that belong to their light: per-light occlusion, the room light kept |
| `91e354a` | Shadow shapes checked pixel by pixel: no gaps, no lit wedges |
| `6ba2ab0` | Shadow geometry test: import order |
| `201edf9` | Soft shadow edges, walls that don't shadow themselves, room shadow settings |
| `7ea4894` | Shadow Quality Lab in the real window; shadow masks only where the light is |
| `b693cfe` | Shadow renderer follows the import and type policies; legacy tests say so |
| (this commit) | The report, MESH_REBUILD and MESH_SALVAGE |
