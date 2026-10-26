# Milestone 18B plan: weather that meets the world

**Status:** the owner accepted this direction on 2026-10-26, with the refinements folded in below. It builds on
Stage 18A (`engine/scene_particles.py`, #377) and keeps 18A's model: stateless GPU particles, one instanced draw call
per effect, and no per-particle work on the CPU. The long-term aim is an environmental toolkit that creators control
without editing JSON. 18B builds the collision foundation for it.

## The problem: hidden is not sheltered

In 18A, a raindrop behind the cottage's roof is hidden only because the camera's depth buffer says the roof is in
front of it. That is right for drawing, but it is not shelter:

- **Under the bridge,** drops fall through the deck and keep falling in the underpass. Wherever the camera sees
  under the deck, they show.
- **Roofs** don't stop rain. A drop that passes behind a roof comes out below the eaves, still falling.
- **Nothing lands,** so nothing splashes.
- **The cottage interior** fills with rain or snow if a room asks for it, and particles fill the void around the
  room.

Shelter depends on where the sky is blocked along the fall direction, independent of the camera. 18B needs its own
map of that.

## The precipitation map

The precipitation map is an orthographic depth map looking along a fall direction (down, tilted by the effect's
mean wind). It is drawn from the room's real environmental geometry: the ground, every structure (roofs, decks,
stairs, terraces, walls), and structures being dragged in Studio.

- **Built like the sun's shadow map, but not coupled to it.** It uses the same building blocks (`sun_matrix` fitted
  to the room, a depth texture and framebuffer, the caster shaders), but it has its own matrix, resolution (1024²,
  about 6 cm a texel over the village), programs and lifecycle. Sun direction, intensity, shadow softness or
  shadows switched off never change it.
- **Cutaways open nothing.** The cutaway is a discard in the camera pass only (`MESH_FS`); the map's caster draws
  every structure whole. A roof that is cut away or see-through for the camera still shelters.
- **Billboards are not in it.** Characters, doors and lamps are left out, so people don't shelter rain. This is
  documented as a limitation.

### Lifecycle (a cached environmental resource)

- **Owner.** The renderer owns a small cache: one map per distinct fall direction in use (at most one per falling
  effect, so at most 4). The cache is keyed by the fall direction quantised to 0.5°, together with the structure
  version.
- **Built when first needed.** A map is built on the first frame that a falling effect is drawn. It costs about the
  same draws as one sun shadow pass, once.
- **Invalidated by structure changes.** Anything that changes structures invalidates every map: the hooks the lamps'
  maps already use (`set_live_ids`, `set_live` during a Studio drag), and room reloads, which make a new renderer
  (Studio's commits, undo/redo, reimport). An invalidated map is rebuilt before the next frame that needs it.
- **Direction changes can't reuse a stale map.** A different wind or speed gives a different key, so a new map. A
  map not used by any current effect is freed.
- **Freed explicitly.** Maps are released on `set_particles`, room change, `release()` and window close, and counted
  in `gl_objects()` / `stats()`. A failure while building one frees what it made (as 18A's layer does).

### In the particle vertex shader (still stateless)

1. **The particle's position** `p(t)` is computed as in 18A, as a pure function of its seed and the time.
2. **Project it along the fall:** `q = M_precip * p`. The map's depth at `q.xy` is the first surface the fall meets
   along that column. `s = (q.z − d_surface) × depth_scale` is how far past that surface the particle is, in metres
   along the fall direction.
3. **Sheltered or above the surface:**
   - If `s < 0`, the particle is still above the surface and is drawn as in 18A.
   - If `s ≥ 0`, it has met the surface; this applies under a roof and beneath the deck. A drop below a roof had
     already landed on the roof, so it is not drawn.
4. **The impact point follows the fall, not the particle's XY.**
   - The landing time is `t_c = t − s / v_fall`, and the impact point is `p(t_c)` moved back onto the surface along
     the fall direction.
   - A wind-slanted drop therefore lands where its own slanted path meets the surface. It is not at the XY where it
     is now.
   - Because `t_c` is a function of the seed only, the splash stays fixed in the world for its whole short life.
5. **The impact shows** for a moment, in the same quad and the same draw call:
   - **rain:** a 2–3 frame pixel-art splash for about 0.15 s;
   - **snow:** a settled flake that fades over about 1.5 s. It is not accumulation.

   Splashes and flakes stand on the surface, facing the camera, and are depth-tested like the drops.
6. **Room boundary:** particles whose XY is outside the room's rectangle are discarded.
7. **Leaves** (the windborne preset) are carried horizontally, not falling. They skip shelter and impacts but are
   clipped to the room.

### Wind, gusts, mixed effects and moving structures

| Change | What happens |
|---|---|
| Wind direction or speed, fall speed | A different mean fall direction, so a different map key and a rebuilt map. A stale map is never sampled. |
| Gusts | The map uses the mean direction. Gusts change a drop's horizontal speed by up to ±`gust` × wind, which moves its landing point by at most `height_fallen × gust × |wind| / fall`. With the rain defaults over 12 m that is up to 0.2 m, inside the 1.5 m edge fades, and documented. The landing point stays consistent: the splash appears where that drop ends. |
| Mixed effects (rain + snow) | Each falling effect samples the map for its own direction, so rain and snow get separate maps. |
| Moving structures | Studio drags invalidate the maps each frame of the drag; the map follows the structure. The game has no moving structures yet. |
| Map unavailable (it failed to build) | Rain and snow fall as in 18A, with no shelter and no impacts. The reason is kept on the renderer and shown in Studio. |
| Out of bounds | A sample outside the map means "no surface". Room clipping discards those particles first. |

### Indoors

- A per-room setting, `settings.weather_exposure`, takes `"outdoor"` (the default) or `"indoor"`.
- An indoor room draws no rain or snow, so weather being active elsewhere never wets an interior. Studio shows why
  if the room asks for them anyway.
- The HD-2D interior template rooms (the cottage among them) are indoor.
- Windborne leaves follow the same rule, since they are outdoor weather too.

### 2D rooms

- 2D maps have no 3D structure. 18B gives them clipping to the room's map rectangle and splashes and settling at
  ground level, in the same draw call, using the same "time since it met the ground" approach.
- 2D roof shelter would need a separate roof mask and is **not** claimed in 18B.

## Studio

- **Preview Weather:** a toggle in the 3D view's panel. When on, the editing view draws the room's particles,
  sheltered, with impacts, through the same renderer, and their clock runs in Studio's edit tick. It is on by
  default when the room has `settings.particles`.
- **Errors:** invalid particle settings, or an indoor room asking for rain, show in Studio's status line instead of
  only in the log.
- **The AI review panel:** `authoring.summarize` gains a settings line, for example "Village: particles rain ×3000
  (wind 0.8 m/s east) → snow ×2000". A proposal that changes weather is then readable before it is accepted.
- **Later stages:** a full Weather panel (visual controls, presets, transitions, combinations) and event-driven
  weather transitions.

## Why this, and not the alternatives

| Option | Verdict |
|---|---|
| Per-raindrop collision in Python (ray-cast each drop) | Rejected. 10,000 ray casts a frame in Python, plus state and buffer uploads, would give up everything 18A won. |
| Analytic boxes (each roof, deck and wall as an AABB in uniforms) | Rejected as the primary method. It doesn't follow real meshes and needs hand-made data per model. |
| Stateful GPU particles (transform feedback / compute) | Unnecessary. Shelter and impact are functions of position, which the stateless shader already has. Keep it in reserve for water. |
| Precipitation depth map (chosen) | It reuses proven shadow-map techniques and real geometry, costs one cached render per room and direction plus a texture fetch per vertex, and needs no new dependencies. |

## Acceptance proof (Stage 18B)

The proof is rendered in hidden windows from the starter village. It uses reusable systems; nothing is tied to
village coordinates.

- **A world-position readback.** A diagnostic mode writes each drawn particle's world position and id into a float
  target. Shelter is then judged in world space, with camera-depth occlusion disabled, so being hidden behind
  something can't pass for shelter.
- **Ray casts against the real geometry.** Every sampled splash is cast along its own fall direction against the
  actual model triangles. Nothing may be above it, and it must sit on a surface.
- **Checks:**
  - rain splashes on the roof;
  - a dry patch under the eaves;
  - splashes on the bridge deck and none in the underpass;
  - splashes on the ground and terraces at their heights;
  - wind-angled rain landing at the right positions;
  - snow settling at the right elevation;
  - a dry interior;
  - impacts that stay put while the camera moves;
  - Studio's preview matching the game.
- **Negative controls:** the same renders with shelter off (18A behaviour).
- **Performance:** the 18A table rerun at 1k, 5k, 10k and 20k. Also measured: map build time, map memory,
  invalidations, room changes, Play/Stop, and recovery from failures. The target is a particle pass of about
  0.2 ms or less at 20,000 on the RTX 4070.

## Out of scope (later stages)

- Puddles, ponds, rivers, wet surfaces and ripples (the lightweight-water stage).
- Accumulating snow cover.
- Thunderstorms.
- Characters sheltering under umbrellas, or rain on characters.
- Weather events and transitions, and the full Studio weather panel.
