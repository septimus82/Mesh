# Milestone 16, Stage 1: True HD-2D Architecture and Rendering Feasibility

Branch `feature/m16-hd2d-feasibility` (from `redesign/visual-editor`, `2e5fe87`). Draft PR to `redesign/visual-editor`.
**No production code changed.** The experiment lives in `tooling/hd2d_lab/`; the engine doesn't import it (a test
checks this). Nothing ran on the desktop: everything rendered off-screen in hidden windows. Blender ran
`--background`, with factory settings.

## Gate assessment: **PASS** (rendering feasibility), with stated limits

**Demonstrated in actual renders:**
- **Geometry:** real 3D geometry exported by Blender (GLB), with pixel-art textures mapped onto it.
- **Camera:** an angled perspective camera.
- **Characters:** animated 2D characters standing in the scene, one of them on a 1 m raised platform.
- **Occlusion,** measured, not just shown: 100% of the hero visible in front of the building, 86% at its corner, **0%
  behind it**.
- **Spatial proof:** a walk around the building and a camera orbit.
- **Speed:** 1.8 ms a frame on an RTX 4070.
- **Isolation:** all of it through Arcade's own OpenGL layer, with no new engine or dependency, and the 2D engine
  untouched.

**Not proven yet**, all of it for later stages:
- the lab running inside Mesh's game loop and window (it renders off-screen);
- a hand-modelled Blender asset (the GLB came from a Blender script and Blender's own exporter);
- height-aware movement;
- 3D lighting and shadows matching Mesh's 2D lighting;
- Studio editing in 3D.

## 1. Current architecture

| System | Today | For HD-2D |
|---|---|---|
| Window, GL context | Arcade 3.3.3 on pyglet 2.1; OpenGL 3.3 core (RTX 4070, 32k textures) | **Reuse unchanged.** `arcade.gl` gives shaders, buffers, framebuffers with depth, depth test and face culling, all proven in the lab |
| Game loop, scenes, entities, behaviours, events, prefabs, flags, save/load | 2D-agnostic logic over entity data (`x`, `y`) | **Reuse unchanged**: behaviours don't care how an entity is drawn. Adding `z` (height) is an extension |
| Authoring layer (`project_ops`, `authoring.apply`, MCP) | Validated ops on scene JSON | **Reuse; extend** with structure placement (`model`, position, rotation) and entity height |
| Sprites, animation (Animator, sheets) | Arcade `SpriteList`, 2D quads, frames from sheets | **Reuse the data** (sheets, clips, frame selection). Drawing becomes billboards in 3D (lab: one draw per sheet) |
| Camera | Arcade `Camera2D` (orthographic), follow, zoom, areas, shake | **Extend:** a 3D camera that follows in the ground plane (the lab's camera); follow and area logic carries over. Arcade 3 also ships a `PerspectiveProjector` |
| Draw order | y-sort, or `explicit_z` (`render_layer` + `depth_z`), then batching | **2D-only.** In 3D, a depth buffer replaces sorting. **`depth_z` is a draw-order key, not a height**; it must not be reused as `z` |
| Lighting and shadows | 2D per-light screen-space occlusion masks (M12), tile occluders, character shadows | **2D-only** as it stands. 3D needs its own lights in the shaders, then shadow maps. The 2D lighting engine stays for 2D projects (not rewritten) |
| Existing "HD-2D" (depth tint, outlines, contact shadows / AO, presets in the legacy editor) | 2D post-effects on flat sprites | **2D-only.** These are looks, not geometry. Some carry over as ideas (tilt-shift, bloom, outline) |
| Collision and physics | 2D boxes and circles swept against tile collision | **Extend:** the ground plane stays 2D (x, y); add a height per walkable surface and floor transitions (stairs, bridges) |
| Navigation | 2D grid A* with portals | **Extend:** a grid per floor, joined by stairs and ramps |
| Templates, scaffolding | `project_templates` generates 2D tile scenes | **Extend:** a separate HD-2D template, kept hidden until ready |
| Studio map viewport | 2D tile painting, picking by world rectangle, pan/zoom | **2D-only today.** HD-2D editing needs a 3D viewport mode (ray picking, gizmos), a later stage |

## 2. Recommended architecture: a 3D scene path beside the 2D one, sharing everything above the renderer

```
            (unchanged) scenes, entities, behaviours, events, prefabs, saves, authoring ops, MCP
                                            |
              project type "2d" (today)     |     project type "hd2d" (new, opt-in)
     +-------------------------+            |      +---------------------------------------------+
     | 2D renderer (unchanged):|            |      | 3D scene renderer on arcade.gl:             |
     | y-sort, SpriteList,     |            |      |  - static structures from GLB (one buffer   |
     | 2D lighting compositor  |            |      |    per material, depth-tested)              |
     +-------------------------+            |      |  - characters/props as billboards from the  |
                                            |      |    same sprite sheets (alpha-test, depth)   |
                                            |      |  - perspective follow camera                |
                                            |      |  - 3D lights + shadow maps (later stage)    |
                                            |      +---------------------------------------------+
```

1. **One engine, one window, one game loop.** HD-2D is a different *scene renderer*, chosen by the project or
   scene type, drawing through the same `arcade.gl` context. The lab proves that path.
2. **Coordinates:** keep Mesh's ground plane and add height.
   - Mesh `x` (east) and `y` (north) become world x and y, and a new optional `z` is height.
   - One 32 px tile is one metre (world unit) in 3D.
   - 2D projects never see `z`, so their data, saves and tools are unchanged.
   - A scene's existing `x`/`y` keep their meaning; `z` defaults to 0.
3. **Structures are glTF 2.0 / GLB** made in Blender (Y-up in the file, converted to Z-up on load). Each is placed as
   an entity with `model`, position, rotation and scale; modular pieces, not one baked scene.
4. **Characters stay 2D.** Their sheets and animations are drawn as upright quads facing the camera. Transparency
   is binary in pixel art, so alpha testing (discard) plus the depth buffer gives correct occlusion with no sorting.
5. **Logic stays 2D-plus-height.** Collision and navigation run in the ground plane per floor; height comes from the
   floor a character stands on.

**Rejected:**

| Alternative | Why not |
|---|---|
| Fake it in the 2D pipeline (`depth_z`, layered sprites, painted backdrops) | No real perspective, occlusion or elevation, which is the point of HD-2D. The existing "HD-2D" effects are this approach |
| A second engine (Godot, Panda3D, Ursina, a moderngl app) | Two engines, two game loops, all of Mesh's systems duplicated or bridged. Excluded by the constraints and by "one operation layer" |
| Arcade `SpriteList` sprites in 3D | Arcade's sprites are quads in the x/y plane. They can't stand upright in a Z-up world without their own shader, which is what the lab's billboards are |
| pyglet's own model loader and graphics (`pyglet.model`) | A second graphics path beside `arcade.gl`, with less control over pixel-art filters. A small GLB reader is about 150 lines |
| A glTF library (`pygltflib`, `trimesh`) | Workable, but a new dependency (trimesh is heavy) for what static meshes need. Worth revisiting for skins or animation |
| Full 3D characters | Not the HD-2D look; it would discard Mesh's sprite and animation pipeline |

## 3. The experiment (Phase B)

**Source**, all in `tooling/hd2d_lab/`:

| File | What it does |
|---|---|
| `textures.py` | The pixel-art textures: stone wall, flagstones, roof slates, grass. 32 × 32 px, original, deterministic |
| `blender_build.py` | Runs inside Blender. It builds a raised stone platform (4 × 3 × 1 m), three steps, a hut and a pyramid roof, each its own object, with per-metre UVs and "Closest" sampling, and exports `assets/stone_outpost.glb` (13.6 KB) with Blender's glTF exporter |
| `gltf.py` | A minimal GLB reader: nodes and transforms, triangles, normals, UVs, embedded PNGs, samplers; Y-up to Z-up |
| `lab.py` | The renderer: an off-screen framebuffer with a depth attachment; a perspective (or orthographic) camera; a lit mesh shader; alpha-tested billboard characters from Mesh's own `starter_hero` / `starter_villager` sheets, animated (4-frame walk), one draw per sheet; blob shadows; the occlusion measurement; timings |

**Reproduce** (from the repo root; no window opens):

```
py -3.13 tooling/hd2d_lab/textures.py
"D:\program\blender.exe" --factory-startup -noaudio --background --python tooling/hd2d_lab/blender_build.py -- tooling/hd2d_lab/assets/stone_outpost.glb
set PYTHONPATH=tooling
py -3.13 tooling/hd2d_lab/lab.py OUT_DIR            (add --ortho for the orthographic camera)
```

**Evidence** ([`milestone16_evidence/`](milestone16_evidence/)):

| File | Shows |
|---|---|
| `hd2d_front.png`, `hd2d_corner.png`, `hd2d_behind.png` | The hero in front of the outpost, half behind its corner, fully hidden behind it. The villager stands on the raised platform |
| `hd2d_walk_around.gif` | The hero walking a loop round the outpost, animated, passing in front of it and behind it |
| `hd2d_camera_orbit.png` | The camera swinging from −40° to +40° round the scene: the building turns in perspective, the characters keep facing the camera, and the occlusion changes with the view |
| `hd2d_projection_compare.png` | Perspective vs orthographic, same view |
| `hd2d_textures.png` | The four textures |
| `results_*.json` | The measurements below |

**Measured** (hidden window, 960 × 540, GPU-synchronised, no pixel read-back):

| Case | Result |
|---|---|
| Hero in front of the building | **3,864 / 3,864** pixels visible (100%) |
| Hero half behind its corner | **2,100 / 2,440** (86%) |
| Hero behind the building | **0 / 2,236** (0%): the depth buffer hides it |
| Villager on the 1 m platform | **3,531 / 3,531** visible; feet drawn more than 20 px higher than on the ground |
| Lab scene (outpost, 2 characters, ground) | **1.8 ms** a frame |
| 1 outpost, 1,000 characters | **2.8 ms**: batched billboards are nearly free |
| 25 outposts (275 draw calls), 300 characters | **12.5 ms**, almost all of it per-draw-call overhead (about 40 µs each). It's solved by merging static geometry per material (275 draws become about 3): a known technique, for Stage 2 |
| Orthographic camera | Same costs (1.8 ms / 12.6 ms) |

**Tests:**
- **`tests/test_hd2d_gltf.py`** (fast, 3):
  - the Blender GLB loads as Z-up modular geometry with exact bounds (−2…2, −2.2…2.1, 0…4.2 m);
  - every sampler is NEAREST and repeating;
  - upward faces point up;
  - a non-GLB file is refused;
  - nothing in the engine imports the lab.
- **`tests/test_hd2d_lab_gpu.py`** (GPU tier, 3):
  - occlusion in front (100%), behind (0%) and at the corner (partial);
  - the platform villager is fully visible and drawn higher;
  - an unlit wall shows only the texture's own colours (no bilinear blending).

## 4. Technical questions (Phase C)

**Proven** = shown in the lab; **prototype** = works in the lab but needs production work; **future** = designed only.

| Question | Status | Finding |
|---|---|---|
| Orthographic vs perspective | Proven | Both work at the same cost. **Recommend perspective**, narrow FOV (25–35°), pitch about 30°: real depth with little distortion, as HD-2D does. Keep orthographic as an option |
| Mapping 2D coordinates into 3D | Prototype | x east, y north, z up; 1 tile = 32 px = 1 m. Existing `x`/`y` keep their meaning; `z` defaults to 0. `depth_z` is unrelated (draw order) |
| Billboards vs fixed camera-facing quads | Prototype | **Upright quads turned about the vertical axis** (cylindrical billboards), height scaled by 1/cos(pitch) to keep drawn proportions. Fully camera-facing quads lean back into walls and clip; upright ones stand where they are |
| Transparent sprites and occlusion | Proven | Pixel art's binary alpha means alpha testing plus the depth buffer, with no sorting. Soft-edged effects (shadows, particles) are drawn afterwards with blending and no depth writes, as the blob shadows are |
| Pixel filtering, mipmaps, bleeding | Proven / future | NEAREST magnification is proven. Repeat wrap tiles per-metre UVs. **Open:** minification shimmer far away (NEAREST without mipmaps), and atlas bleeding once textures are packed. Fix with mipmaps (Blender already writes NEAREST_MIPMAP_NEAREST) and padded atlases |
| Geometry and material import | Proven (static) | Blender 5.2's glTF exporter writes one primitive per material, embedded PNGs, and the "Closest" filter as NEAREST. The reader handles nodes, transforms, triangles, normals, UVs, images and samplers. **Not yet:** skins and animation, vertex colours, `.gltf` with external files, KHR extensions |
| Collision geometry and walkable surfaces | Future | Mark collision and walkable pieces in Blender (object-name prefixes, or custom properties, which export as glTF `extras`). Build per-floor 2D collision and height grids from them at import |
| Height-aware movement, stairs, bridges, underpasses | Future | A floor stack per cell (ground, bridge deck…). A character keeps a current floor; stairs and ramps are transition zones. Navigation runs per floor, linked at transitions. Rendering already handles any `z` (the platform villager) |
| Current lighting and shadows | Future | The 2D compositor works in screen space with 2D occluders, so it doesn't carry over. Stage 1 uses a sun plus ambient light in the shader. Next: Mesh's point lights (position, radius, colour, plus height) in the shaders, then shadow maps for the sun and key lamps. The 2D engine isn't touched |
| Blender reimport and prefabs | Future | Reference the GLB by path. Re-export replaces it, and prefabs keep their placement and overrides. The "one file = one module" convention keeps reimport local |
| Studio selecting and manipulating 3D objects | Future | A 3D viewport mode: ray picking against bounds and triangles, a ground-plane drag (like today's 2D drag), height and rotation handles, snapping to the 1 m grid. The same `project_ops`, extended with `z`, `model` and rotation |

## 5. Starter content (Phase D, design only)

A **modular kit**, 1 m grid, one Blender file per piece. Exported GLBs and textures are generated or original, with
provenance recorded (like `docs/starter_art.md`):

| Piece | Notes |
|---|---|
| Ground tiles: grass, path, stone, sand | Flat 1 × 1 / 2 × 2 tiles, or a ground mesh, painted per tile |
| Cottage: walls, corner, door frame, window, roof halves | Snap together; a door piece marks the interior transition |
| Stairs (straight, 1 m rise) and a ramp | Their walkable surface and the floor link they create |
| Raised platform (1 m) and its edges | The second floor for height tests |
| Bridge (deck plus supports) | Walk over and under: the underpass test |
| Props: fence, crate, barrel, lamp post, tree, rock, sign | Low-poly, pixel-textured |
| Characters | The existing generated `starter_hero` / `starter_villager` sheets (owned art), plus the replacement monster sprites the packaging decision needs |
| One NPC interaction | Reuses today's dialogue, events and behaviours unchanged |

**Rule:** no Octopath assets, no proprietary samples, nothing without a recorded origin. Textures come from the
generator (`textures.py`) or the owner's own work, or from PixelLab output whose terms are checked and recorded.

## 6. Risks and limitations

- **Draw calls:** the measured cost is per draw call, not per triangle. Static batching is needed before larger
  scenes (Stage 2).
- **Lighting:** HD-2D's mood comes largely from lighting, depth of field and bloom. 3D lighting and shadow maps are
  real work, and the 2D lighting engine won't serve 3D scenes.
- **Studio:** a 3D viewport (picking, gizmos, camera) is the largest single piece of HD-2D work.
- **OpenGL 3.3 core only:** no compute shaders and no bindless resources. That's fine for this style, but it limits
  some modern techniques.
- **Off-screen only so far.** The lab draws to a hidden framebuffer and reads it back. Presenting in Mesh's real
  window, with input and the game loop, is Stage 2's first step and wasn't tried here, as the brief required.
- **Blender:** validated as an exporter, through a script on the owner's install (5.2.0 LTS). A hand-made asset round
  trip, and other Blender versions, are untested.
- **NumPy:** used by the lab, installed here, but not a declared Mesh dependency. Production code would need it
  declared, or written without it.

## 7. Proposed later stages

| Stage | Scope | Done when |
|---|---|---|
| 2: In-engine 3D scene path | The lab's renderer inside Mesh's game loop and window for a hidden `hd2d` scene type; static batching; follow camera; entity `z`; GLB structures as entities; billboards from existing sprites and animators | A hidden test scene runs in the real window at 60 fps with the existing player, input and behaviours |
| 3: Floors and movement | Walkable surfaces and floor stacks from Blender markers; collision and navigation per floor; stairs, ramps, bridges and underpasses | A character walks up stairs, over a bridge and under it, and pathfinding agrees |
| 4: Lighting | Mesh lights in 3D (point plus sun), shadow maps, fog, simple bloom and tilt-shift | Lamps light walls and characters, shadows fall on geometry, at budget |
| 5: Studio 3D viewport | Picking, moving, rotating and height for structures and entities; asset browser for GLBs; reimport | A creator places a cottage and stairs and walks it with F4 |
| 6: Starter kit and template | The modular kit from §5; an HD-2D template behind a flag, then in the launcher | A new HD-2D project plays the small starter scene; owner acceptance |
