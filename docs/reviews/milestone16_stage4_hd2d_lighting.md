# Milestone 16, Stage 4: HD-2D Lighting and Shadows

**Verdict: PASS.** HD-2D rooms now have real 3D lighting inside Mesh's own runtime:

- **Lights:** ambient light, a coloured sun or moon, and coloured lamps that have a position and a reach in 3D. Every
  surface is lit where it actually is, including structures, the ground and the character sprites.
- **Shadows:** depth-map shadows from the sun, and from up to two lamps.

The shadows are **proven geometric, not taken from a picture**:

- For every spot a character can stand on in the test scene, the GPU's answer (sunlit or shaded, reached by a lamp or
  blocked) was compared with rays cast on the CPU through the structure's actual triangles.
- Sun: **1,316 of 1,316 unambiguous spots agree.** Lamps: **190 of 190 and 241 of 241 agree** (129 of those spots are
  blocked by the stairs or the hut).
- A character walking under the bridge gets **28% of the light it gets with shadows off**. Its drawn pixels are 3.5×
  darker, and walking into the open or onto the bridge changes nothing.

2D rooms and the 2D lighting compositor are untouched. Stage 3's movement, collision, navigation, saves and Studio
play-testing all work in the lit scene.

Branch `feature/m16-stage4-lighting` (from `redesign/visual-editor` at `1a91feb`), with a draft PR to
`redesign/visual-editor`. **Not merged; it is for owner review.** Stage 5 has not been started.

## Phase 0: Stage 3 integration and the tunnelling question

| Step | Result |
|---|---|
| #353 before merge | 29 files, head `8e03620`, mergeable. Required checks green; the full `tests` job had the [#352](https://github.com/septimus82/Mesh/issues/352) baseline of the same 26 failures. |
| Tunnelling | **The defect was confirmed.** Destination-only checks let one long move pass through a 5 cm wall (3 m and 8 m steps), a 10 cm railing, or a 1 m gap between equal-height floors. The game loop doesn't clamp `delta_time`, so a slow frame can do that. |
| Fix (on #353, before merge) | `World.move` splits long moves into steps no longer than half the footprint's smaller side. A normal frame is still one step. |
| New tests | `tests/test_hd2d_world_tunnelling.py`, 16 fast tests: thin walls, railings, gaps, platform edges, overlapping floors, characters on different floors at the same x/y, and the 2D physics kept in rooms without HD-2D floors. |
| Results after the fix | Fast tier 4,413 passed, 0 failed. HD-2D GPU tests 10/10. Type and ruff gates ok. |
| Merge | #353 merged as `1a91feb`; the merged tree is identical to the PR head. #344 is still a draft and `main` is untouched. |
| Pre-existing CI issues | **#351** (the background-layer GPU test) and **#352** (the full `tests` job's 26 failures) stay tracked. Neither changed in this stage, and neither is attributed to it. |

## Architecture

### What lights the scene

All lights reuse settings that Mesh rooms already have. The scene format is backwards-compatible: every Stage 2 and
Stage 3 scene loads unchanged.

| Light | Where it comes from |
|---|---|
| Ambient | `settings.hd2d.ambient` (strength, as before), tinted by the scene's ordinary `{"type": "ambient"}` light, the one 2D rooms use. |
| Sun / moon | `settings.hd2d.sun`. A plain direction still works. The new object form is `{"direction", "color", "intensity"}`. |
| Lamps | **The scene's ordinary `lights`**, the same entries 2D rooms use: `x`, `y`, `radius`, `color` / `color_rgba`, `intensity`, `enabled`, `shadows` (default true, as in 2D). New: an optional HD-2D **`elevation`** in px (default 48 = 1.5 m). The scene schema documents it, and 2D lighting ignores it. |
| Shadow look | The room's existing 2D settings: `lighting_shadow_softness` (sharp / soft / softer) sets the filter width, and `lighting_shadow_strength` sets the darkness. |
| New HD-2D keys | `shadows` (default true) and `shadow_resolution` (1024 / 2048 / 4096, default 2048). |

**Budgets:**
- 8 lamps per room (the shader's loop).
- Of those, 2 cast shadows: the first two that ask for them. The rest still light, without shadows.

Lamp `flicker_*`, polygon lights and lights carried by objects (`LightSource`) are 2D-only for now; see Limitations.

### Shading

One GLSL function, `light_at(position, normal, billboard)`, is shared by the structure, ground, sprite and
light-probe shaders (`engine/hd2d/lighting.py`). It computes:

- ambient;
- plus the sun × N·L × sun visibility;
- plus, for each lamp in reach: colour × intensity × (1 − d/r)² × N·L × lamp visibility.

It is evaluated **per fragment, at the fragment's world position**:

- A character's feet, middle and head are lit separately. One half under a bridge and half in the sun is lit that way.
- **Character billboards** have no real normal. They take a fixed share of each light (0.75 of the sun, 0.85 of a
  lamp), so they read the same from every side.
- They test shadow visibility at their own position, offset 15 cm towards the light so that a sprite never shadows
  itself.
- The texture keeps NEAREST sampling, so pixel art stays crisp.
- With the same formula, Stage 2's defaults (white sun, white ambient) give the same base brightness as before.

### Shadow maps

| Map | Contents | Drawn | Size and memory |
|---|---|---|---|
| Sun | Orthographic depth map fitted to the whole room (structures, ground, plus 2.5 m of headroom for characters). Holds the batched structures and the character billboards (alpha-tested silhouettes). | **Every frame**, so moving characters cast sun shadows. Cost: about 4–5 draws, because structures are statically batched. | 2048² by default, 20 MiB (4 B depth + 1 B colour). Texels are 2.4–2.6 cm in the crossing and 3.5 cm in the village. |
| Lamps | Up to 2 lamps. Each has six 90° faces in one atlas row (512² a face), storing distance to the lamp ÷ radius. | **Once**, on the room's first frame, because lamps and structures don't move. `Lighting.invalidate()` redraws them. Characters don't cast lamp shadows. | 7.5 MiB per shadowed lamp |

How it works:

- Maps are allocated only when a room has shadows enabled, and the lamp atlas is sized to the lamps that actually cast
  shadows.
- They are released with the room. The Stage 2 GL-object test confirms that textures, framebuffers and programs return
  to the 2D baseline.
- arcade 3.3 can't bind `sampler2DShadow` (it raises `Unsupported Uniform type: 35682`), and its depth textures default
  to compare mode. So the maps use `compare_func = None` and are read as plain `sampler2D`, with the comparison done in
  the shader.
- arcade framebuffers also need a colour attachment, so each map carries an unused 1-byte-per-texel colour target.
- **Filtering:** the room's softness maps to percentage-closer filtering. Sharp is 1 sample; soft is 3 × 3; softer is
  5 × 5 for the sun and 3 × 3 for lamps.
- **Acne and detached shadows:** a small depth bias is used (sun: 0.0012 of the map's depth range, about 5 cm; lamps:
  0.6% of the radius). The receiving point is also offset 3 cm along its normal, or 15 cm towards the light for
  billboards.
  - Acne would make sunlit spots read as shaded. None of the **1,178 sunlit spots** did.
  - A detached shadow would leave a gap at a wall's foot. The only spots excluded from the comparison are those within
    12 cm of a shadow edge.

### Render passes (one frame)

1. Build this frame's character quads into one reused dynamic buffer. No allocation.
2. **Sun shadow pass**: structures plus billboards. On the room's first frame only, the **lamp shadow passes** run
   too.
3. **Scene pass** into the off-screen target: ground, the batched structures, and the billboards. All are lit with
   shadows.
4. Blit into the active framebuffer: the screen, or post-processing.

When shadows are on, the Stage 2 painted blob under each character is not drawn, because its real shadow falls from
the sun. With shadows off, the blob returns.

No new library, no second engine, no bloom, tilt-shift or depth of field.

## The demonstration: Stage 3's crossing, lit

`tooling/hd2d_floors_demo.py build` builds the same Blender-authored crossing as before, now with:

- **a warm sun** from the north-east (`#fff0d8`), so shadows fall towards the camera;
- **a dim bluish sky**: ambient 0.35, tinted `#8a96c8` by the scene's ambient light;
- **a warm lamp** (`#ffb060`, 1.5 m up) at the foot of the west stairs;
- **a contrasting blue lamp** (`#5a8cff`, 1.2 m above the east platform) beside the hut, which blocks it;
- soft shadows (the room's `lighting_shadow_softness`);
- **the warden**, who walks from the east platform down its stairs, into the underpass's shade, and back.

The player still climbs, crosses, descends and passes underneath. All 5 Stage 3 floors tests pass on the lit scene.

Pictures, in `docs/reviews/milestone16_stage4_evidence/`, all drawn in-engine in a hidden window:

| Shadows on | Shadows off | What to see |
|---|---|---|
| `overview_shadows.png` | `overview_no_shadows.png` | Platforms, stairs, the hut and the bridge casting onto the ground. Off, only the shading by facing (N·L) remains. |
| `underpass_shadows.png` | `underpass_no_shadows.png` | The deck's shadow across the underpass. The warden is in the shade. |
| `hut_lamp_shadows.png` | `hut_lamp_no_shadows.png` | The hut's sun shadow on the platform. The blue lamp's light stops at the hut. |
| `stairs_lamp_shadows.png` | `stairs_lamp_no_shadows.png` | The warm lamp on the stairs, with the steps' stepped shadow. |
| `player_open.png`, `player_under_bridge.png`, `player_on_bridge.png` | | The player, walked there with held arrow keys, in each light. |
| `walk_stairs_lit.png`, `walk_bridge_lit.png`, `walk_under_bridge_lit.png` | | Stage 3's walk, lit. |
| `studio_play.png` | | Mesh Studio's own Play (F4) of the lit room. The player casts a sun shadow. |
| `village_lit.png` | | 20 separate buildings, 8 lamps, shadows on. |

## Measurements (`check.json`; `tests/test_hd2d_lighting_gpu.py`)

**Geometric agreement (`Lighting.probe`).**

- **How the probe works:**
  - It draws one float pixel per world point with the scene's own `light_at`, its uniforms and its shadow maps.
  - The light terms can be isolated. The ratio "with shadows ÷ without" removes everything except visibility.
  - Each spot is compared with CPU rays (Möller–Trumbore through the structure's drawn triangles).
  - A spot counts only if five rays shifted ±12 cm all agree.
- **Spots:** every standable position on a 0.5 m grid over the crossing's floors, 1,392 in total. The sun map was
  drawn without characters for this comparison.

| Source | Agree | Disagree | Shaded or blocked | Lit or reached | Skipped (edge) |
|---|---|---|---|---|---|
| Sun | **1,316** | **0** | 138 (ground 106, east platform 19, bridge deck 13) | 1,178 | 76 |
| Warm lamp (stairs) | **190** | **0** | 11 | 179 | 3 |
| Blue lamp (hut) | **241** | **0** | 118 | 123 | 36 |

**Named cases** (luminance of the arriving light, shadows on / off):

| Case | On | Off |
|---|---|---|
| Underpass ground in the deck's shadow (16, 10.8) | 0.207 | 0.722 |
| Ground in the west platform's shadow | 0.207 | 0.694 |
| East platform in the hut's shadow | 0.420 | 0.907 |
| Open ground (16, 5) | 0.694 | 0.694 |
| Blue lamp's light behind the hut | **0.000** | 0.016 |
| Blue lamp's light in front of the hut | 0.153 | 0.153 |

**Character.** The player is walked there with held arrow keys. Light is probed on its billboard at its feet, middle
and head:

| Where | Light on (feet / middle / head) | Light off | Drawn sprite pixels, on / off |
|---|---|---|---|
| Open ground | 0.669 / 0.669 / 0.669 | 0.669 / 0.669 / 0.669 | 53.4 / 53.4 |
| **Under the bridge** | **0.207 / 0.207 / 0.207** | 0.745 / 0.769 / 0.793 | **18.1** / 63.4 |
| On the bridge (2 m up) | 0.799 / 0.808 / 0.810 | the same | 84.5 / 84.5 |

- Off, the light under the bridge still rises from feet to head; that is the warm lamp's falloff.
- On the bridge it is lit consistently at its new height.

**Camera moves.** One spot in the deck's shadow and one in the sun were drawn with the camera at two positions (the
screen positions differ). **The colour of each spot is identical**: shaded RGB (14, 26, 18) and sunny (52, 88, 45).
This is because the maps are in world space.

**The warden.** Over its route, the light on it ranged from **0.21 in the shade to 0.71 in the sun**.

## Performance

`bench.json`: the village of 20 separate buildings (statically batched into 3 material draws), the whole village in
view, 1280×720, RTX 4070, 120 frames each.

| Configuration | CPU median ms | GPU median ms | Scene draws | Shadow draws / frame | Shadow memory |
|---|---|---|---|---|---|
| Shadows off, 0 lamps | 1.12 | 0.022 | 6 | 0 | 0 MiB |
| Shadows on, 0 lamps | 1.42 | 0.081 | 5 | 4 | 20 MiB |
| Shadows on, 1 lamp | 1.49 | 0.086 | 5 | 4 | 27.5 MiB |
| Shadows on, 2 lamps | 1.54 | 0.090 | 5 | 4 | 35 MiB |
| Shadows on, 4 lamps (2 shadowed) | 1.51 | 0.092 | 5 | 4 | 35 MiB |
| Shadows on, 8 lamps (2 shadowed) | 1.67 | 0.233 | 5 | 4 | 35 MiB |
| Shadows off, 8 lamps | 1.19 | 0.078 | 6 | 0 | 0 MiB |
| Shadows on, 2 lamps, 1024² sun | 1.58 | 0.147 | 5 | 4 | 20 MiB |
| Shadows on, 2 lamps, 4096² sun | 2.16 | 0.697 | 5 | 4 | 95 MiB |

- **The lamp shadow maps** are drawn once: 36 draws (2 lamps × 6 faces × 3 batched materials). That adds about
  2 ms to the room's first frame (first frame 7.2 ms against 5.2 ms without lamps).
- **The GPU objects created during 120 frames** are **0** in every configuration (buffers, textures, framebuffers,
  geometry). There is no per-frame allocation.
- **Measurement method.** "CPU" is submitting the renderer's frame, shadow pass included. "GPU" is a
  `GL_TIME_ELAPSED` query around it.
- **Measurement noise.** GPU times this small are noise-level; the 1024² run measuring slower than 2048² is noise.
  The whole crossing game frame, HUD included, ran at about 3 ms.
- **The default budget** (2048² sun, up to 8 lamps, 2 shadowed) keeps HD-2D under 0.25 ms of GPU and about 1.7 ms of
  CPU in this village. 4096² is available, but costs 95 MiB and about 0.7 ms.

## Regression

| Check | Result |
|---|---|
| Fast tier (`tooling.test_tiers tier0`, `-W error`) | **4,423 passed, 0 failed** (8 skipped) |
| Targeted (lighting, shadow, HD-2D, behaviour, player, save/persistence, scene loader, lifecycle, tick, Studio, play, HUD, dialogue, animation, transitions, templates, docs, MCP) | **2,824 passed, 0 failed** (69 skipped: GL-gated, run in the GPU tier) |
| GPU tier (`MESH_GL_SMOKE=1`, every GL-gated file, including the 2D shadow compositing, corner, geometry and character-shadow suites that cover Sharp / Soft / Softer) | **80 passed, 1 failed, 1 skipped**. The failure is #351, which also fails on the base. The skip is the NumPy-gated Stage 1 lab. |
| HD-2D Stage 2 and Stage 3 GPU tests (render, occlusion, resize, release, walk, stairs, bridge, saves, warden) | 10/10, on the lit renderer |
| New tests | `tests/test_hd2d_lighting_settings.py`: 10, fast. `tests/test_hd2d_lighting_gpu.py`: 7, GPU. |
| Mesh Studio | Edit view of the lit room ok. Studio's own **Play** draws it lit with shadows (`studio.json`). Stop returns to edit. |
| `tooling/visual_polish_check.py` (2D game and Studio render) | **10/10** |
| Type gate / ruff gate / `type: ignore` | ok / ok / 0 |

## Known limitations and visual defects

- **Characters cast sun shadows as their sprite's silhouette, as seen by the camera.** When the sun is low and to one
  side, the shadow is that flat shape at an angle, not a 3D body's. This is the usual HD-2D compromise.
- **Characters don't cast lamp shadows**, because the lamp maps are static. A character also casts no shadow onto
  itself.
- **Sprites take a fixed share of each light**, with no back-lighting or rim: a character lit from behind reads as lit
  from the front.
- **Only static scene lamps are supported.** Lamps carried by objects (`LightSource`), flicker and polygon lights are
  still 2D-only.
  - Lamps are fixed when the room loads; a scripted lamp change needs `Lighting.invalidate()`.
  - At most 8 lamps, 2 of them shadowed; the rest light without shadows.
- **The sun map covers the whole room.** That is fine at these sizes (2.5–3.5 cm texels), but a much larger map would
  need cascades or a camera-fitted map.
- **Shadows near edges** are about one filter width soft (2.5–7.5 cm). There is no contact hardening.
- **The underpass is shaded by the slanted shadow of the deck,** not simply beneath it. With this sun, the ground
  directly below the deck's north edge is sunlit. That is correct, as the CPU rays confirm, but it can look
  unexpected.
- **2D lighting features don't apply in HD-2D rooms:** the 2D compositor's polygon occluders, light shafts and
  day/night tint. Studio still edits HD-2D rooms in 2D (Stage 5).

## What I did not do

- No Stage 5 work: no Studio 3D viewport, and no HD-2D launcher template.
- No bloom, tilt-shift or depth of field.
- Stage 4 is not merged, and nothing went into `main`.
- **Filesystem:**
  - Work happened only in this task's worktrees (`D:\Games\Mesh-s3fix` was removed after #353 merged;
    `D:\Games\Mesh-hd2d4`) and in new, named scratchpad folders.
  - The scene builders refuse to write into existing folders, and the check tools never delete.
  - Your projects, stash, settings and untracked files were not touched.
- **Desktop:** no visible windows, no OS input, no focus taken.
