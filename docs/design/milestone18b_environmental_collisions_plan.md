# Milestone 18B plan: weather that meets the world

Status: **plan for owner review. Nothing is implemented.** It builds on Stage 18A (`engine/scene_particles.py`,
merged with #377) and keeps 18A's model: stateless GPU particles, one instanced draw call per effect, and no
per-particle work on the CPU.

## The problem: hidden is not sheltered

In 18A, a raindrop behind the cottage's roof is hidden only because the camera's depth buffer says the roof is in
front of it. That is the right thing for drawing, but it is not shelter:

- **Under the bridge,** drops fall through the deck and keep falling in the underpass. Wherever the camera sees
  under the deck, they show.
- **Roofs** don't stop rain. A drop that passes behind the roof comes out below the eaves, still falling.
- **Nothing lands,** so nothing splashes.
- **The cottage interior** fills with rain or snow if a room asks for it, and particles fill the void around the
  room.

Shelter depends on where the sky is blocked along the fall direction, independent of the camera. 18B needs its own
map of that.

## Recommended architecture: a precipitation map

The renderer already makes exactly this kind of map for the sun (`engine/hd2d/lighting.py`):

- `sun_matrix(direction, world_lo, world_hi)` gives an orthographic view-projection along a direction that fits the
  room;
- `_depth_target` gives a depth texture and framebuffer;
- the `caster` program draws the batched structures (buildings, the bridge, stairs, terraces) into it. The renderer
  passes `self.static + live` to it; the sun pass leaves the ground out (it receives shadow and never casts).
  The precipitation map must include `self.ground` too, so drops land on it.

18B adds one more such map, the **precipitation map**: depth along the fall direction (straight down, tilted by the
effect's mean wind), drawn from the room's static structures.

| | Sun shadow map | Precipitation map |
|---|---|---|
| Direction | towards the sun | the fall: down, tilted by the mean wind (one map per room, or per effect if two winds differ a lot) |
| Contents | structures and billboards (not the ground), every frame | the ground and the structures (roofs, decks, terraces, walls), no billboards, **once per room**, and again only when Studio edits a structure (an `invalidate()` like the lamps' maps have) |
| Size | 2048² | 1024² is about 6 cm per texel over the village (about 4 MB of depth) |
| Cost | about 30 draws, every frame | the same draws, once |

### In the particle vertex shader (still stateless)

For each particle at its world position `p` (computed as in 18A):

1. **Project `p` into the precipitation map:** `q = u_precip_vp * p`. The map gives the depth `d_surface` of the
   first surface the fall meets there.
2. **Sheltered:** if `q.z > d_surface + bias`, something above stops this drop (a roof, the deck). It isn't drawn.
   That is the real underpass and eave shelter, whatever the camera sees.
3. **Landing:** the surface height under the drop is reconstructed from `d_surface` (an affine depth, so it is
   exact). How long ago the drop crossed it is `age = (h_surface - p.z) / fall_speed`.
   - **Rain:** for `age < 0.15 s` the quad is drawn as a **splash**: 2–3 atlas frames chosen by age, laid flat on
     the surface at `(x, y, h_surface)`. After that it isn't drawn until it wraps back to the top.
   - **Snow:** for `age < settle_time` (about 1–2 s) the flake rests on the surface and fades. It is a settled
     flake, not accumulation.
   - **Leaves:** unchanged. They are carried by the wind, not falling, and skip the shelter test.

   Splashes therefore appear exactly where drops meet roofs, the bridge deck, terraces and the ground. They come
   from the same draw call, at the cost of one texture fetch per vertex. There is no second particle system and no
   CPU collision.
4. **Room boundary:** particles outside the room's world rectangle (the renderer's `world_lo`/`world_hi`, already
   known) are discarded. That removes the "stars" around the cottage and the backdrop in 2D rooms.

### Indoors

- An interior has walls and is seen from above, so its precipitation map would show open sky.
- Room-level exposure decides instead. Add `settings.weather_exposure`: `"outdoor"` (the default for rooms with
  ground) or `"indoor"` (the HD-2D interior template's default, the cottage among them).
- An indoor room draws no precipitation, even when a future world-level weather event is active. 18A's per-room
  `settings.particles` keeps working; an author can still ask for leaves indoors.
- This also prepares event-driven weather. The world says "rain", and each room's exposure decides whether it
  shows.

### 2D rooms

- 2D maps have no 3D structure, so 18B gives them a boundary clip and splashes on the ground only.
- 2D roofs, using map regions or a "covered" tile layer as a 2D precipitation mask, are a possible later
  extension. They are not in 18B.

## Why this, and not the alternatives

| Option | Verdict |
|---|---|
| Per-raindrop collision in Python (ray-cast each drop) | Rejected. 10,000 drops means 10,000 ray casts a frame in Python, plus state and a buffer upload per frame. It gives up everything 18A won. |
| Analytic boxes (each roof, deck and wall as an AABB passed as uniforms) | Workable only for a handful of boxes. It doesn't follow real meshes (pitched roofs, stairs, terrain) and needs hand-made data per model. Rejected as the primary method. |
| Stateful GPU particles (transform feedback / compute) | Unnecessary. Shelter and landing are functions of position, which the stateless shader already has. Keep it in reserve for puddles or flowing water. |
| Precipitation depth map (recommended) | Uses the existing shadow-map code and the real geometry. It costs one static render per room and one texture fetch per vertex, and needs no new dependencies. |

## Studio preview (the 18A usability gap)

- **Studio's HD-2D view:** draw the layer in the edit camera too. `draw_3d` already works for any camera; 18A
  limited it to the game view (`camera is None`). Put it behind a **"Preview weather"** toggle in Studio's View
  menu, on by default when the room has `settings.particles`, and advance the clock from Studio's tick.
- **Studio's 2D view:** call `draw_2d` under the editor camera with the same toggle.
- **Errors:** show the room's `scene_particles_error` in Studio's status line instead of the log only.
- **AI review card:** add a settings line to `authoring.summarize`, for example "Start: particles rain ×3000". The
  same change fixes the existing `set_room_lighting` gap.
- **No weather panel yet.** Editing stays with the `set_particles` operation (AI) and JSON until the owner asks for
  the panel.

## Acceptance proof for 18B (planned)

The proof would be rendered by the 18A study tool, extended.

| Check | Measure |
|---|---|
| Underpass sheltered | With depth testing off (so camera occlusion doesn't count), no rain pixels under the deck. Rain on top of the deck splashes. |
| Roofs stop rain | No rain below the cottage eaves inside the roof's footprint; splashes on the roof. |
| Ground and elevated splashes | Splashes counted on the ground, the terraces, the deck and the roof, each at the surface's height (checked against the map). |
| Snow reaches surfaces | Flakes settle at surface height under open sky and not under cover. |
| Indoors and boundaries | The cottage interior shows zero precipitation pixels. No particles outside the room rectangle in either 2D or HD-2D. |
| Performance kept | The 18A table rerun. Targets: under 0.2 ms of GPU time for the particle pass at 20,000 with shelter, and under 50 ms of precipitation map render per room load. Still one draw call per effect. |
| Lifecycle | The map is freed with the room, and the GL counts are stable over room changes and Play/Stop, as in 18A. |

## Out of scope (later stages)

- **Puddles, ponds, rivers, wet-surface darkening and ripples:** the lightweight-water stage.
- **Accumulating snow cover:** that needs state, a texture painted over time.
- **Characters sheltering under umbrellas, or rain on characters:** the map holds structures only.
- **Weather events and transitions** (fade in and out driven by events), and **the Studio weather panel**.

## Size estimate

The work is one new map in `lighting.py`, shelter, splash and settle code in the particle shader, a splash atlas
row (procedural, as in 18A), the exposure setting, Studio preview wiring, and tests extending the 18A suites. It
fits one stage and one draft PR.
