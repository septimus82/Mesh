# Milestone 20A: terrain feasibility

- **Branch:** `feature/m20a-terrain`.
- **Draft PR:** [#384](https://github.com/septimus82/Mesh/pull/384), into `redesign/visual-editor`.
- **Builds on:** Stage 19B (#383, merged as `4cffa32`).
- **A bounded feasibility stage, not a terrain editor.** No terrain painting, foliage, erosion or full landscape UI;
  Stage 20B is not started.

**Verdict: PASS** (details at the end).

## Summary

Mesh can now hold **editable physical terrain height** under an HD-2D room:

- **Storage.** A sculpted heightfield over the room's ground, stored in the scene, deterministically and sparsely.
- **Rendering.** It draws in the existing HD-2D viewport and game loop, casts and receives the sun's shadows, and
  takes the rain.
- **Movement.** Characters walk up and down its slopes at the right elevation, and are stopped by faces too steep to
  stand on.
- **Coexistence.** Structures, stairs, bridges and underpasses work on and over it.
- **Water.** A Stage 19B pond sits in a sculpted basin at its own level, its shoreline the ground itself.
- **Editing.** One validated operation edits it, the same for Studio, the CLI and AI. A Studio prototype sculpts it
  a click at a time with undo, redo, save and reopen.
- **No regressions.** Rooms without terrain are pixel-identical to the base, and 2D projects are untouched.

## Part A — Architecture study

### What exists, and where terrain fits

| System | Today | With terrain |
|---|---|---|
| Ground | One textured quad (`settings.hd2d.ground`: texture, extent, elevation), drawn first | The same ground, optionally carrying `terrain` heights; drawn as chunks instead of the quad only when sculpted |
| Structures | Blender GLB models, placed with x, y, elevation, rotation, scale; collision authored in Blender (`mesh_collision`: solid, floor, wall) | Unchanged. They stand on the terrain as on the flat ground: at their own elevation |
| Collision | `engine.hd2d.world.World`: walkable triangles (structures' solids and floors, the ground's two triangles) in a 2 m spatial index; walls as boxes; one rule, `stand` | The ground's two triangles give way to the terrain, read straight from its heights where asked (`Terrain.surface_at`: the drawn triangle under the point, unless too steep); `stand`, movement, navigation and picking use it unchanged |
| Height-aware movement | Feet must find a walkable surface within a step (0.35 m) of their elevation; nothing solid inside the body | Unchanged: walking up a slope is that rule, frame by frame |
| Lighting | Sun shadow map over the room's box (structures cast, the ground receives); lamps' cube maps made once | Terrain chunks cast too (hills shade valleys); the room's box includes the terrain's height range |
| Precipitation (18B) | Maps drawn from the ground and structures, along the fall | Drawn from the terrain chunks: rain stops on the sculpted surface; invalidated on edits |
| Water (19A/19B) | An entity whose elevation is its level; one instanced pass | Unchanged; plus an opt-in shore "terrain" that reads the ground's heights |
| Studio | 3D view picking: a ray against the ground plane or the World's walkable surfaces | `Terrain.ray` for the ground; objects are placed on the terrain by the World's `walkable_hit` |

### The representation: a chunked heightfield

- **Heights at cell corners**, `cell` px apart (16 px = 0.5 m by default; 8 or 32 allowed), offset from the ground's
  elevation. Each cell is two triangles split along one diagonal: the same triangles are drawn, walked on and
  ray-picked, and `Terrain.height` interpolates exactly those.
- **Real elevation, not draw order.** Heights are world metres in the 3D view. A character's elevation (its
  `elevation`, saved with the game) becomes the ground's height as it walks, as on floors. `depth_z` (2D draw order)
  is untouched.
- **Collision from the geometry, without storing it.** Where the World asks for walkable heights, the terrain answers
  from its corners: the drawn triangle under the point, its height and its slope (`Terrain.surface_at`, about 2 µs).
  Faces steeper than `MAX_SLOPE` (normal z < 0.7, about 46°) are left out: nobody can stand on them, so they stop
  characters from above and below, a cliff. No physics engine; the rule is the existing one. (A first version stored
  every terrain triangle in the World's index; QA measured it growing to 85 MB and seconds of navigation work at
  128 m, so the ground is now a lookup and an edit has nothing to rebuild in the World.)
- **Pixel-art materials.** Gentle cells take the ground's own texture with uv = world metres, so texels keep the art's
  32 per metre, as on the flat ground. A cell either of whose faces is steeper than `STEEP` (about 41°) takes the
  starter dirt texture (one material a cell, so the boundary follows the cells, not a sawtooth of triangles),
  box-mapped onto the face's side so its texels keep their size on a cliff. Nearest filtering, as everywhere.
- **Chunks for partial rebuilds.** 16 × 16 cells (8 m) a chunk. A stroke reports the chunks whose drawing it
  changed (a corner on a chunk's edge belongs to its neighbours, and a corner's normal reads the corners either side,
  so one corner further out). The renderer remakes only their buffers (the new ones first: a refused upload leaves
  the old drawing), the World just takes the edited heights, and the precipitation maps are remade when next needed.
  Chunks out of the picture are skipped in the main pass.
- **The room's border.** Where sculpted ground meets the edge of the room above or below its base level, a dirt
  skirt closes it (a hill cut by the border is a solid, not a paper shell). Level border stays exactly as before.
- **Deterministic storage.** Each chunk's corners are little-endian int16 heights in quarter-px steps (0.78 cm,
  ±256 m), base64, keys sorted, all-zero chunks left out. The same heights always write the same text: flat ground
  stores nothing, and a room made flat again loses its `terrain` key and is the plain ground exactly. The 32 × 24 m
  proof room stores 8,892 characters.
- **Compatible with flat scenes.** No `terrain` key, or one with no heights, means the old code path everywhere.
  Unknown ground keys are still ignored as before. Broken heights in a scene file load as flat ground with the reason
  logged and shown in Studio; the rest of the room (structures, floors) is unaffected.
- **No new dependency.** Pure Python (no NumPy in the engine); GPU buffers through arcade as for structures.

Alternatives considered and set aside for this stage:

| Option | Why not now |
|---|---|
| Voxels or marching cubes | Would allow caves and overhangs, but much more geometry, collision and storage than Mesh's HD-2D rooms need; structures already provide those |
| Terrain as a generated GLB structure | Reuses the structure path, but every edit would rewrite a model file; no partial rebuild, no per-cell queries |
| A height texture sampled in the vertex shader | Cheap to draw, but collision, picking and precipitation would still need the heights on the CPU; two sources of truth |
| Per-vertex smooth normals vs per-face flat shading | Smooth normals chosen: rolling hills read as hills at this pixel scale; faceting looked noisy |

### What a heightfield cannot represent

One height per place: **no caves, no vertical overhangs, no stacked walkable surfaces** (a tunnel under a hill, an
arch, a cliff ledge over a path). Those stay the job of structures, as they are now:

- a bridge spans a sculpted valley (proved below: walked over and under);
- stairs and platforms stand on the terrain;
- a cave entrance or an arch would be a Blender model placed against a hillside.

Vertical faces exist only as steep slopes between two corners, so a "cliff" is at least one cell (0.5 m) wide in
plan, drawn in dirt. A sheer stone wall is better as a structure.

## Part B — The proof room

A disposable room ("Hills", 32 × 24 m) added to a project made from the HD-2D RPG template; the template's own village
is untouched. Its ground is sculpted only through `project_ops.sculpt_terrain`, in 336 strokes (3.5 ms each, checked
and in saved form):

- **A gentle hill** (west, 1.5 m, 4 m radius), the Elder on its top.
- **A terrace** (north-east, 1.5 m) with a **ramp** up its west side and a **cliff** on its south side.
- **A shallow valley** (north-south, 0.55 m deep) running **under the template's bridge**, which spans it between two
  platforms with stairs up to the west one.
- **A pond basin** (south-east, 1.2 m deep).
- The cottage on flat ground; the player in the south-west.

`sculpt_steps.png` shows it flat, then with each part added; `overview_dry.png` and `overview_rain.png` from above.

### Walking (the game's own key events, `walking`)

| Walk | Result |
|---|---|
| Over the hill (south to north) | Rises to 1.475 m on its 1.5 m top, back to 0.04 m beyond it; feet always on the ground (`walk_hill.webp`) |
| Up the ramp onto the terrace | 0 → 1.5 m, then across the terrace at 1.5 m (`walk_ramp.webp`) |
| Into the terrace's cliff from the south | Stopped at its foot (y 15.47 m, 0.37 m up its lower slope): the steep face can't be stood on |
| Along the valley, under the bridge | At −0.55 m the whole way, under the deck (headroom kept), never on it (`walk_valley.webp`) |
| Up the stairs, across the bridge | Stairs to the platform (2.0 m), across the deck over the valley to the far platform at 2.0 m (`walk_bridge.webp`) |
| Into the pond's basin | Down to −1.19 m on its floor, wading (`walk_pond.webp`) |

At every end the character's elevation equals the ground's height there (to a millimetre) when standing on the
ground.

### Anchoring: sculpting moves nothing

**Rule:** the terrain never moves anything:

- structures keep their elevation;
- characters and objects keep theirs (saved in the scene);
- water keeps its level.

What an edit leaves out of place is reported, never corrected silently:

- **In the operations:** `project_ops.terrain_anchoring(scene, before)`, for Studio, the CLI and AI. Objects are
  judged by the ground under their feet, structures across their middle. Given the room before an edit, it lists only
  what that edit moved off the ground (not a bridge over a valley or someone on a platform, which never stood on it):
  "'cottage' is 0.6 m into the ground", "'Elder' is 1.5 m above the ground".
- **An explicit fix:** `settle_on_ground(scene, ids)` stands the named objects on the ground under their feet, as one
  undoable edit; Studio offers it after a stroke as **Settle on the ground (n)**. It is never done by itself.
- **In the AI review:** a terrain edit reads "Hills: ground sculpted over about 25 m²: raised up to 0.75 m (now 0.00
  to 0.75 m)", followed by "left out of place (not moved): ..." lines.
- **In Studio:** the existing "buried" report already lists characters that can't stand where they are.
- **In play:** a character with no ground within a step stays where it was saved and can't move until placed again
  (proved: the Elder after his hill was flattened).

Raising the ground under the cottage and flattening the hill under the Elder: neither moved, and the edit's report
listed exactly those two (not the bridge). Choosing what to do is the creator's or AI's.

## Part C — Water in a real basin

A natural pond (Stage 19B) is placed over the basin, its **shore "terrain"**. This is one narrow, opt-in addition to
the water renderer:

- **Its own data.** The water reads a small float texture of the ground's heights (12 KB here), made when the room
  loads or the ground changes.
- **What it draws.** It draws only where the ground lies below its level, so its shoreline is the terrain's own
  contour.
- **Shallows from depth.** It takes its shallow-to-deep colour from the water's real depth, and draws a crisp
  waterline where it meets the ground.
- **Nothing else changes.** Other shores and all other water are unchanged.

| Check | Result |
|---|---|
| Independent, editable level | The water's level is its object's elevation (−0.6 m). At −0.9, −0.6 and −0.3 m it covers 10,874, 20,572 and 34,979 px: the shore moves out up the basin's sides (`water_levels.png`) |
| Shoreline from the terrain | Its outline (7 × 6.25 m) is larger than the basin; the ground decides where the water ends |
| Submerged ground doesn't obscure it | 20,572 px drawn, and with its depth test off still 20,572: nothing under the surface hides any of it |
| Characters | The player walks into the basin to −1.04 m and wades: the water covers his legs (2,332 px around him change; `water_wading.png`) |
| Reflections | The Elder on the far shore is mirrored at reflection 0.8 (20,551 px; `water_reflection.png`) |
| Rain | Rings it (5,674 px) |
| Shadows | Fall on it as on any 19B water (it is lit by the room) |
| Procedural banks stay optional | The same pond with Stage 19B's grass bank (its own outline as the shore) beside the terrain shore (`water_shores.png`) |

The basin is walkable (the pond is set "walk through it"), so characters wade. A deeper pond that should stop them
can be set not walkable, as in 19A; a depth-based rule is a 20B question.

## Part D — Environmental systems

| System | Result |
|---|---|
| Sun shadows | Terrain chunks cast into the sun's shadow map. Under a low evening sun the hill throws a crisp shadow down its lee side: 2,394 px darkened against the same frame with the ground left out of the casters (`shadows.png`). Gentle hills under a high sun mostly shade by their normals |
| Precipitation | The rain's precipitation map, read back, puts the surface where the ground is: hill top 1.473 m (ground 1.477), terrace 1.511 (1.5), ramp 0.874 (0.898), valley −0.544 (−0.547), basin floor −1.199 (−1.195), open ground 0.0 (0.0); under the bridge's deck it stops at the deck (2.016 m), so the valley under it is sheltered |
| Picking | 19 rays from the game camera meet the ground at exactly its height (0.0 mm error), through `Terrain.ray` and the World's `walkable_hit` alike |
| Invalidation | A stroke reports its chunks; the renderer remakes those buffers; the World has nothing to rebuild (it reads the heights); the precipitation maps are remade when next needed, the water's height texture when the ground's version changes. The sun's shadow box and the lamps' cube shadow maps are made once per load (a full reload refreshes them; Studio reloads on every edit) |

### Measured cost (RTX 4070, hidden windows; `m20a_terrain_study.py perf`, the Hills room)

| Measure | Result |
|---|---|
| Size | 3,072 cells (0.5 m), 20 chunks, 6,186 triangles drawn; 594 KB of GPU buffers; 3,185 heights on the CPU; 8,892 characters stored |
| One stroke (a 2 m brush) | The operation on the scene (checked, saved form) 4.4 ms; 4 chunks to redraw in place 20 ms; collision 0.004 ms (it reads the heights) |
| Every chunk | Redrawn in 61 ms; the collision World made from scratch in 0.8 ms |
| One chunk's mesh | 4.2 ms (pure Python) |
| Standing (`World.stand`) | 16 µs on sculpted ground against 8 µs on flat ground; a height lookup is 1.8 µs |
| NPC navigation grid | 66 ms to build, once, on the first route (flat ground: 37 ms) |
| Frame on the GPU | 0.946 ms sculpted against 0.954 ms with the same room's ground flat (interleaved rounds): no measurable cost |
| Frame on the CPU | About 1 ms more (5.4 against 4.2 ms, performance QA): the chunks' draws and shadow draws |
| Room load | 219 ms (performance QA: about 81 ms of that is the terrain) |
| GL objects | Level over 5 rebuilds of every chunk and 5 room changes (buffers, framebuffers and programs equal; textures 30 → 29, one fewer, made before the first count) |

Scale (performance QA, the ground sculpted all over, after the fixes below):

| Ground | 32 × 24 m | 64 × 64 m | 128 × 128 m |
|---|---|---|---|
| Collision World made | 1.0 ms | 4.1 ms | 15 ms |
| Collision memory | — | — | 2.1 MB (85 MB before the fix; the plain room 0.76 MB) |
| Navigation grid | 66 ms | 315 ms | 1.26 s |
| Draw calls in the main pass (culled / all) | 38 / 40 | 46 / 144 | 46 / 528 |
| Room load | 0.22 s | 0.63 s | 1.6 s |

Large rooms still pay for every chunk in the sun's shadow pass (527 shadow draws at 128 m) and in loading, and
the sculpt operation re-encodes the whole ground (69 ms a stroke at 128 m). These are Stage 20B items (below), not
blockers for a feasibility stage.

## Part E — Studio workflow

### The prototype

In the 3D view's panel:
- **Sculpt ground** turns sculpting on;
- **Raise, Lower, Smooth, Flatten** choose the tool;
- **Smaller / Bigger** and **Softer / Stronger** set the brush.

A yellow ring follows the ground under the mouse at the brush's radius, draped over the terrain. The 1 m grid follows
the ground too. Each click is one checked edit (`project_ops.sculpt_terrain`), so it undoes, redoes and saves like
any other. After an edit, Studio says what it left out of place.

Proved through Studio's own buttons, keys and clicks in a hidden window (`studio`):

| Step | Result |
|---|---|
| Hills room, Sculpt ground on, hover | The ring on the ground at (20.0, 6.0, 0.0) m (`studio_1_brush.png`) |
| Four Raise clicks, then Flatten, Bigger, a click | Raised 0.91 m, then flattened (`studio_2_sculpted.png`) |
| Ctrl+Z five times / Ctrl+Y four times | Back exactly to the room before / exactly to the raised ground |
| Ctrl+S, reopen | Saved; reopened identical |
| F4, F4 | Plays on the sculpted ground; back to editing |

**What it shows about usability:** each click takes **0.38 s** (0.38–0.50). Almost all of that is Studio's reload of the
room after every edit, not the sculpting: the operation itself is 4 ms, and rebuilding the changed chunks in place is
about 20 ms (4 chunks) and collision has nothing to rebuild (performance QA: reload 241 ms,
Studio's interface rebuild 139 ms, the operation 4.6 ms). Clicking works; painting with a held mouse button needs the in-place path.

### Stage 20B design (proposed, not built)

1. **Live strokes.**
   - While the mouse is held, each step applies `Terrain.sculpt` to the loaded room's terrain and rebuilds only the
     dirty chunks in place (`Hd2dRenderer.update_terrain`; the World just takes the heights), about 20 ms a step at
     this size, less with faster chunk meshes.
   - On release, one `sculpt_terrain`-equivalent edit commits the whole stroke to the scene: one undo step a stroke.
   - A batched operation (`sculpt_terrain_strokes(scene, strokes=[...])`) so Studio, the CLI and AI still share one
     validated edit.
2. **Brush feel.** Strength per second rather than per click; a radius slider and the `[` `]` keys; Shift to lower,
   Ctrl to smooth; a flatten target picked from the ground (or typed); the ring coloured by tool; a height readout
   under the cursor.
3. **Anchoring actions.** Built in 20A: the edit-relative report and Settle on the ground for objects. For 20B:
   settling structures (to the ground across their footprint), the out-of-place list as clickable entries, water left
   dry or flooded by an edit reported too.
4. **The rest of the in-place path.** Grow the sun's shadow box and remake the lamps' maps when an edit raises the
   ground above the room's box; update only the dirty part of the water's height texture and Studio's grid; build
   chunk meshes faster (4 ms each in pure Python).
5. **Materials.**
   - A chosen steep texture per room (the dirt texture is the starter kit's, with a plain-earth fallback).
   - A blend band between grass and dirt.
   - Painting materials later (out of scope now).
6. **Scale.** Merge chunk draws into fewer buffers for large rooms. Keep the lamps' shadow maps in step with edits
   (remade on commit).
7. **Water.** Water can be placed by clicking a basin: its size and level from the basin. Optionally walkability by
   depth.

## Compatibility and regressions

- **Rooms without terrain are pixel-identical to the base (`4cffa32`).** Each was rendered with both trees:
  - the template's village and cottage;
  - the Stage 19A water village (puddle and pond, dry and rain);
  - a 2D room with a natural pond.

  0 px differ in all 7 pictures. The village's walkable places (6,800) and a scripted walk end in the same place and
  elevation in both.
- **Saves:** `terrain` is optional; older scenes load unchanged; malformed terrain data fails the room's HD-2D
  settings with the reason (the room draws 2D, as for any bad HD-2D setting) instead of crashing.
- **2D projects:** never build a World or terrain.

## Part F — QA and gates

Local results (Windows), on the final code:

| Gate | Result |
|---|---|
| Fast tier | 4,721 passed |
| Terrain fast tests (`tests/test_terrain.py`) | 26 passed |
| GPU suites (`MESH_GL_SMOKE=1`): terrain, floors, runtime, starter, Studio, lighting, particles, water, weather | 78 passed |
| ruff gate | ok |
| Generated docs verify | passed (`docs/behaviours.md` regenerated) |
| Rooms without terrain against `4cffa32` | 0 px different in 7 pictures; walkable places and a scripted walk identical |

- **mypy gate:** no new errors; the two known local `tooling/hd2d_lab` numpy errors are also on the base.
- **Linux and Windows CI:** see #384.

### Independent QA (Opus, hidden windows, real in-engine output)

Each reviewer first gave a CONDITIONAL PASS on `6975d48`. Their findings were fixed, and each re-checked them on the
fixed code: **all three now give PASS.**

**Rendering.**
- **Major, fixed: ground cut by the room's border was a paper shell** (the sky showed through a hill at the edge). A
  dirt skirt now closes it where the ground leaves its base level. Level borders are unchanged.
- **Minor, fixed:** the grass/dirt boundary was a sawtooth of triangles; now one material a cell.
- **Nits, fixed:**
  - A faint shading step at chunk edges: 3,249 px before, 0 px now.
  - A hand-written empty terrain block wasn't pixel-exact to the plain ground: now 0 px.
- **Verified:**
  - Chunk culling changes 0 px over 360 frames (edges, corners, camera turned all round).
  - No T-junction cracks.
  - No shadow acne from terrain casting.
  - Rain lands within a few centimetres on hills, pits and slopes, and the bridge shelters the valley.
  - The terrain shore follows the water's level and is never hidden by submerged ground.
  - Rooms without terrain are pixel-identical to the base in more templates (the 2D adventure template, the village
    in rain and snow, lamp views, 19B ponds).
- **Kept as limits:** an uphill boot clipped on side slopes, and the shore's blended heights (not visible).

**Collision and navigation.**
- **Majors, fixed:**
  - **The AI review said nothing about terrain edits.** It now describes them and what they leave out of place.
  - **A character whose ground moved more than a step is frozen in play.** This is kept by design (no silent moves),
    with an explicit `settle_on_ground` op and Studio button added.
  - **Settling the shared player wrote its elevation into every room.** Found in the re-check: the player's starting
    elevation is now each room's own (`ROOM_PLAYER_FIELDS`), verified through AI and Studio, with save and reopen.
- **Minors, fixed:**
  - **The anchoring report was noisy and missed a partly buried cottage.** It now judges under the feet and across
    structures, relative to the edit.
  - **An int16 overflow at the height limit.**
  - **The navigation grid was 10× slower than on flat ground.** It is now about 1.8× (66 against 37 ms).
  - **One bad terrain chunk turned the whole room 2D.** The ground now loads flat with the reason and the structures
    stay.
- **Verified:**
  - Feet always on the ground (0.000–0.001 m).
  - Cliffs block from below and above, and diagonal moves slide along them.
  - No tunnelling at frame times up to 3 s or with any cell size.
  - Ground edges hold.
  - Stairs, bridge and underpass work.
  - NPC routes take the ramp, not the cliff.
  - Validation, determinism, save and reopen.
- **Kept as limits:** slopes right at the 45° limit are uneven. A hand-made shared player that carries an elevation
  moves it to the room it is next saved in.

**Performance.**
- **Major, fixed:** a stroke's dirty chunks missed neighbours whose normals it changes (stale lighting after an
  in-place rebuild). They are now included: 4 chunks for a 2 m brush.
- **Major at scale, fixed:** the World stored every terrain triangle (85 MB, seconds of navigation work at 128 m).
  It now reads the heights.
- **Minor, fixed:** chunks out of view are culled in the main pass (frame CPU 15.4 → 8.9 ms at 128 m).
- **Minor, fixed:** a failed chunk upload left a hole. The new buffers are now made first.
- **Verified:**
  - The author's numbers within about 10%.
  - Lifecycle clean over strokes, rebuilds, room changes, Studio undo and redo, Play/Stop and release.
- **Remaining for 20B:** the shadow pass over every chunk, whole-ground re-encoding per stroke, and Studio's 0.38 s
  click (reload and UI rebuild).

## Known limits

- **Heightfield limits:** no caves, overhangs or stacked walkable ground (structures provide them). A cliff is at
  least one cell wide and drawn in dirt.
- **Characters on side slopes:** a sprite stands upright at its centre's height, so on a steep sideways slope the
  ground cuts its uphill boot by a few pixels (rendering QA).
- **Slopes right at the limit** (about 45°) are walkable along the axes but not quite along the feet box's diagonal,
  and patchy when stored heights round them across it (collision QA).
- **The terrain shore** reads the ground's heights blended between corners while the ground is drawn as triangles:
  at most 0.6 px apart, a sliver of shore drawn dry (not visible).
- **Studio sculpting is a click at a time** (about 0.38 s each: the room reloads): fine for shaping, not for painting.
  Stage 20B's live strokes address it.
- **Lamps' shadow maps** are made once per room load; in-place rebuilds don't refresh them.
- **The steep texture** is the starter kit's dirt (a plain earth colour without it); per-room choice is 20B.
- **Structures** don't follow the ground: one on a slope keeps its elevation (reported if it ends up buried or
  floating).

## Verdict

**PASS.**

Mesh demonstrates editable physical terrain height that:
- **renders correctly** in the HD-2D viewport and game loop: with sun shadows cast and received, rain landing on it,
  pixel-art materials, a closed border, and nothing different in rooms without it;
- **supports character movement**: walking up and down slopes at the right elevation, cliffs blocking, NPC routes
  over it;
- **holds an existing water surface**: a Stage 19B pond in a sculpted basin at its own editable level, its shoreline
  the ground, with characters wading, reflections and rain;
- **keeps everything else working**: bridges, structures, saves and traditional 2D projects.

It is one validated operation for Studio, the CLI and AI, with determinism, anchoring reports and an explicit settle,
and a Studio prototype that sculpts with undo, redo, save and reopen. The limits are those of a heightfield (caves
and overhangs stay structures' job) and of a click-at-a-time prototype; Stage 20B's design above addresses the
editing speed.

Stage 20A stops here for owner review. Stage 20B has not been started.
