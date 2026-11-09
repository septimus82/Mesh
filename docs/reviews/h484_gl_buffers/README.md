# H-484A: HD-2D GL buffer lifetime across room changes (#484). Evidence only, never merge

**Baseline:** `redesign/visual-editor` `10bcee1`; historical check on `0fa2f25`.
**Branch:** `evidence/484-gl-buffers` (instrumentation, data, and a prototype regression test; nothing here is meant to
merge).
**Machines:** RTX 4070 (Windows 11, NVIDIA driver); Mesa 26.0.3 llvmpipe, loaded locally from CI's pinned archive.
**Libraries:** arcade 3.3.3, pyglet 2.1.11, Python 3.13.

## Verdict

**Not a GL resource leak in Mesh.** #484's growth is arcade's deferred deletion, counted by a loop that never ends a
frame.

**The mechanism:**
- Arcade's windows use `gc_mode="context_gc"` (its default; Mesh doesn't change it).
- A dropped `Buffer`, `VertexArray`, `Texture`, `Framebuffer` or `Program` is not deleted when Python collects it. Its
  `__del__` puts it in `ctx.objects`, and it is deleted only in `ctx.gc()`, which arcade runs at the start of every
  `Window.flip()`.
- #484's probe (`scripts/probe_visits.py`, from the L4-1 evidence) loads a room, dispatches `on_update` 30 times and
  draws once with `Hd2dRenderer.draw()`. It never calls `flip()` or `ctx.gc()`, so every buffer dropped since the window
  opened is still in the queue. `ctx.stats` created − freed counts those queued buffers as live, and they really are
  live in the driver: every one passes `glIsBuffer`.
- In ordinary play, Mesh runs `arcade.run()` (`GameWindow.run`, the launcher, `mesh play`, Studio). pyglet's event loop
  flips the window every frame, so the queue is emptied every frame and the counts stay flat.

**Where the 214 dropped buffers per visit come from** (the whole of the +168/+260):

| Source | Buffers per visit | Why |
|---|---|---|
| `engine/particles.py:351 _sync_sprites` | 150 | `self.particles.clear()` every update frame: arcade 3.3.3's `SpriteList.clear()` throws away all 5 of the list's GL buffers and makes 5 new ones (5 × 30 frames) |
| The room load | 64 | Replacing the old room's SpriteLists (`tilemap.load_map`, `_build_tile_layer`, `scene_controller_core._clear_layers`, `tilemap_state._clear_tilemap_layers`) and its lighting layer (`lighting._create_layer`) |

The net change per visit is those 214 minus or plus the difference between the rooms' own live buffers (village 123,
cottage 77): 214 − 46 = **+168** entering the cottage, 214 + 46 = **+260** returning.

## 1. Reproduction

**Setup:**
- A fresh `hd2d_rpg` project: `py -3.13 -m mesh_cli new game --dest <DIR> --template hd2d_rpg`.
- 2D comparison: a `blank` project with a second room `other` (a copy of `start` with two soft lights and lighting on).

**Commands:**
```
py -3.13 -I scripts/probe_visits.py <WORKTREE> <DIR>/game                               # #484's original probe
py -3.13 -I scripts/probe484.py <WORKTREE> <DIR>/game OUT.json --mode harness|loop|real [--visits N] [--gl mesa]
                                 [--rooms start,cottage]
py -3.13 -I scripts/minimal_repro.py [--mesa]                                              # arcade only, no Mesh
py -3.13 -I scripts/clear_cost.py [--mesa]
```

**Modes** (each visit: load the room, then 30 frames):
- `harness`: as #484's probe: `on_update` ×30, then one `Hd2dRenderer.draw()`; never flips.
- `loop`: each frame `on_update`, `on_draw`, `flip()`.
- `real`: the room changes are driven from inside `arcade.run()` (pyglet's own event loop) every 30 clock ticks.

**What the probe records:**
- After every load and every settle: live objects per kind (`ctx.stats` created − freed).
- The queued garbage in `ctx.objects`, by type, and the newly queued buffers by allocation site.
- Every arcade buffer's creation site (a stack sample) and deletion, its byte size, and `glIsBuffer` on each "live" id.
- Python object count, process private bytes and working set, and NVIDIA free video memory
  (`GL_NVX_gpu_memory_info`; not available on llvmpipe).
- At the end: counts after `ctx.gc()`, after `gc.collect()` + `ctx.gc()`, after `Hd2dRenderer.release()`, and after
  the window is closed.

`--gl mesa` needs Mesa's DLLs in `scripts/mesa/x64`, extracted from CI's pinned archive (not committed).

## 2. Counts and memory (`data/*.json`)

| Run | GL | Visits | Live buffers, visits 0–4 | Last two | Queued at end | `glIsBuffer` true | Traced buffer bytes |
|---|---|---|---|---|---|---|---|
| `harness` @ `10bcee1` | RTX | 21 | 312, 480, 740, 908, 1168 | 4332, 4592 | 4469 (+650 VAOs) | 4592 / 4592 | 8.98 MB |
| `harness` @ `10bcee1` | llvmpipe | 21 | identical | 4332, 4592 | 4469 | 4592 / 4592 | 8.98 MB |
| `harness` @ `0fa2f25` | RTX | 21 | identical | 4332, 4592 | 4469 | 4592 / 4592 | 8.98 MB |
| `harness`, 2D rooms | RTX | 21 | 280, 528, 772, 1016, 1260 | 4920, 5164 | 4774 | 5164 / 5164 | 9.60 MB |
| `loop` @ `10bcee1` | RTX | 21 | 123, 77, 123, 77, 123 | 77, 123 | 0 | 123 / 123 | 0.25 MB |
| `loop` @ `10bcee1` | llvmpipe | 21 | same | 77, 123 | 0 | 123 / 123 | 0.25 MB |
| `loop` @ `0fa2f25` | RTX | 21 | same | 77, 123 | 0 | 123 / 123 | 0.25 MB |
| `loop`, 2D rooms | RTX | 21 | 86, 90, 90, 90, 90 | 90, 90 | 5 (queued after the last frame; freed at the next) | 90 / 90 | 0.22 MB |
| `real` (`arcade.run`) | RTX | 21 | 123, 77, 123, 77, 123 | 77, 123 | 0 | 123 / 123 | 0.25 MB |
| `real` (`arcade.run`) | llvmpipe | 21 | same | 77, 123 | 0 | 123 / 123 | 0.25 MB |
| `loop`, long | RTX | **201** | 123, 77, … | 77, 123 | 0 | 123 / 123 | 0.25 MB |

**Textures, framebuffers, programs and geometries:** each room returns to the same counts in every mode (village
42 / 6 / 27 / 49, cottage 18 / 6 / 27 / 26). In harness mode, vertex arrays grow with the queue (to 705); in the other
modes they stay at 57 / 12.

**Memory:**

| Run | Private bytes (MB) | Working set (MB) | Python objects |
|---|---|---|---|
| `harness`, RTX, 21 visits | 836 → 1041 (+205) | 196 → 222 | 163k → 193k (+30k: pinned by the queue) |
| `loop`, RTX, 201 visits | 823 → 906 by visit 20, then 891–926 to visit 200 | 198 → 208 by visit 20, then 211.9 at 200 | 156k–177k sawtooth (cycle collector; alternating rooms), no trend |
| `real`, llvmpipe, 21 visits | 756 → 763 | 270 → 277 | 165k → 167k |

- **Loop/real modes:** NVIDIA free video memory moves between 4,543 and 4,844 MB, with no downward trend across 201
  visits.
- **Harness mode:** the dead queue also keeps Python objects alive (arcade's SpriteList data, each buffer's `GLuint`).
- **The NVIDIA private-bytes rise in the first ~20 visits of loop mode** is driver and allocator warm-up. From visit 20
  to visit 200 it moves within ±16 MB with no slope larger than the noise (+16 MB over 180 visits, inside the sawtooth).

**At the end of each run:**
- One `ctx.gc()` takes harness mode from 4592 to **123** live buffers, the current room's own.
- `gc.collect()` then frees nothing more: nothing is held only by a reference cycle.
- `Hd2dRenderer.release()` frees the renderer's 57 buffers, leaving 66.
- Closing the window doesn't change `ctx.stats`: arcade skips its counters when no context is current. The driver frees
  every object with the context, and a deleted context can't be queried, so that last step is not measurable from
  Python.

## 3. Ownership traces (`created_sites`, `survivor_sites`, `pending_new_by_site` in `data/*.json`)

**Created over 21 harness visits** (top sites; 5 buffers per arcade SpriteList):
- `engine/particles.py:351 _sync_sprites` → `SpriteList.clear()` → `_init_deferred`: 630 SpriteLists' worth of buffers
  (3,150 buffers). One SpriteList per update frame.
- `engine/hd2d/renderer.py:591 _buffer` (geometry; 695 buffers). Survivors after `ctx.gc()`: 55, the current room's
  renderer. The rest are previous rooms' renderers, freed by `Hd2dRenderer.release()` → queued → `ctx.gc()`.
- Each 63 SpriteLists' worth: `scene_controller_core.py:437 _clear_layers`, `tilemap.py:196 load_map`,
  `tilemap.py:397 _build_tile_layer`.
- `lighting/__init__.py:791 _create_layer` (`arcade.future.light` render targets): 43 × 3.

**Survivors after `ctx.gc()`:** only the current room's renderer geometry (55), its tile and layer SpriteLists, and
arcade's own context buffers (`arcade/context.py`, made with the window).

**New queued buffers per visit, harness mode** (identical every visit):

| Site | Buffers |
|---|---|
| particles `_sync_sprites` | 150 |
| `tilemap.load_map` | 15 |
| `scene_controller_core._clear_layers` | 15 + 5 |
| `tilemap._build_tile_layer` | 15 |
| `tilemap` `<lambda>` (line 73) | 5 |
| `tilemap_state._clear_tilemap_layers` | 5 |
| `lighting._create_layer` | 4 |
| **Total** | **214** |

## 4. Minimal reproduction (`scripts/minimal_repro.py`, arcade only)

| Step | RTX: live buffers / queued / queued still in the driver | llvmpipe: live / queued / in the driver |
|---|---|---|
| Start | 13 / 0 / 0 | 13 / 0 / 0 |
| 20 SpriteLists replaced, no flip | 113 / 75 / 75 | 113 / 0 / 0 |
| + 100 `SpriteList.clear()`, no flip | 613 / 575 / 575 | 613 / 595 / 595 |
| One `Window.flip()` | 38 / 0 / 0 | 18 / 0 / 0 |
| 100 × (replace + clear + flip) | 38 / 0 / 0 | 18 / 0 / 0 |

- **Queued buffers exist in the driver until `ctx.gc()`:** every queued id answers `glIsBuffer` true.
- **Python's cycle collector timing differs between the two runs:** on llvmpipe, at step 2 the replaced lists were not
  yet collected, so not yet queued. Either way they're freed by the first flip after collection.
- **Steady state is flat.** The 38 vs 18 after a flip is lists still waiting for the cycle collector.

## 5. Is it a real leak?

**What was checked:**

| Question | Finding |
|---|---|
| Are deleted buffers counted correctly? | Yes: `delete_glo` decrements `stats.buffer` when it runs. The queue is counted as live because it is live: deletion hasn't happened yet. |
| Delayed destruction or Python GC? | Arcade's queue is the delay. `gc.collect()` after `ctx.gc()` frees nothing more (no cycle-only garbage remained). |
| References kept after room changes? | None found. After `ctx.gc()` only the current room's objects remain (survivor sites above), in every mode and on both drivers. |
| Context ownership and resource caches | One context. Arcade's default atlas and context buffers are made once with the window. Lighting resources warm up once in 2D (textures 5 → 8 on the first lit room, then flat). |
| Gone on window or context destruction? | The driver frees them with the context; not measurable from Python (counters skipped, ids unqueryable). |
| Does buffer memory grow with the count? | In harness mode yes: 8.98 MB of buffer data after 20 visits, +205 MB private on NVIDIA. In loop/real modes no: 0.25 MB, flat for 201 visits. |
| Live ids in the driver | `glIsBuffer` matches the count in every run (4592/4592 in harness; 123/123 in loop/real). |

**Conclusion:** the counts are accurate. The objects they report are real but transient: deleted at the next frame end
in any real event loop.
- **HD-2D only?** No: 2D rooms show the same pattern (harness +~245 per visit; loop flat at 90).
- **Gameplay or harness only?** Only where frames never end: hidden-window harnesses that dispatch `on_update` /
  `on_draw` and never flip. The deferred memory in a long harness run is real: ~10 MB private bytes per visit on
  NVIDIA, all returned at the next `ctx.gc()`.
- **Historical:** `0fa2f25` is identical in both modes, so this predates L4-1.

## 6. Recommended correction (not implemented)

**No engine change is needed for a leak.** The correction is a regression test that measures the way the game runs, and
an optional harness fix so long GPU tests don't hold dead GL objects.

### A. Regression test (required)
- **New file:** `tests/test_room_transition_gl_lifetime_gpu.py`. The prototype is on this branch; it is GL-gated
  (`MESH_GL_SMOKE=1`, gpu lane).
- **What it does:**
  - 8 round trips `start ↔ cottage` in a fresh `hd2d_rpg` project;
  - each frame: `on_update`, `on_draw`, `ctx.gc()` (what `Window.flip()` does, without swapping buffers, so read-backs
    still work);
  - after every visit: the queue must be empty;
  - after a one-round-trip warm-up: every kind (textures, framebuffers, programs, buffers, geometries, vertex arrays)
    must equal its value at the previous visit to the same room. No tolerances.
- **Results:** passes at `10bcee1` on the RTX (11 s) and on llvmpipe (25 s).
- **Planted leaks** (`scripts/mutate484.py`), all caught:
  1. the HD-2D renderer never released and still referenced on a room change;
  2. every frame's dropped particle SpriteList buffers kept;
  3. frames that never end (#484's probe).

### B. Shared harness frame end (recommended)
- **Files:** `tooling/hd2d_demo.py` (`HiddenGame.step` / `draw`) and `tooling/hd2d_studio_demo.py`
  (`StudioDriver.advance`).
- **Change:** end each frame with `window.ctx.gc()`, as arcade's loop does. Not `flip()`: the harnesses read the back
  buffer after drawing.
- **Why:** a long GPU test then holds the same GL memory as the game (~0.25 MB of buffers instead of growing ~0.45 MB of
  buffers and ~10 MB of driver/private memory per room change).
- **Risk:** low. It only deletes objects that are already garbage. If anything still used a dropped object's raw GL
  id, that would surface as a real bug.
- **Already doing this:** several harnesses (`hd2d_demo.py` checks, `health_stress_study.py`,
  `lakeside_village.py`, `dof_study.py`, `gpu_lifetime_probe.py`) call `ctx.gc()` before counting. #484's probe didn't.
- **Scope:** about 22 more tooling/test files dispatch `on_draw` without flipping. Only the two shared drivers above
  need it for the GPU lanes.

### C. Separate and optional (performance, not a leak)
- **The cost:** the particle layer's per-frame `SpriteList.clear()` reallocates 5 GL buffers every update frame while
  particles are active.
  - `scripts/clear_cost.py`: 0.30 ms per `clear()` on the RTX and 0.16 ms on llvmpipe (40 sprites, deletion included).
  - The baseline (`ctx.gc()` alone) is ~0.2 µs.
- **A fix** would reuse the list (remove and append sprites, or keep a fixed pool) instead of `clear()`.
- **Scope:** it changes particle code, so it belongs in its own reviewed PR with a frame-time measurement. Not part of
  #484.

### Compatibility
- Arcade, renderer, Studio and Play/Stop lifecycles are unchanged: A and B touch only tests and tooling.
- `Hd2dRenderer.release()` already frees its objects explicitly; arcade deletes them at the next frame end.
- **Software GL:** llvmpipe keeps buffers in host memory, so B matters most there. The same 20 harness visits held
  4,469 dead buffers under llvmpipe. The test runs on llvmpipe in 25 s.

## 7. Limitations and open questions

- **Driver-side free on context destruction** is asserted by the GL spec, not measured: Python can't query a destroyed
  context, and arcade skips its counters then.
- **Process private bytes on NVIDIA** include the driver's own heaps. The 201-visit run shows them flat after warm-up,
  within noise. A longer soak (thousands of visits) and Studio Edit → Play → Stop cycles were not run here; `tooling/
  gpu_lifetime_probe.py` already covers Play/Stop with `ctx.gc()`.
- **NVIDIA free video memory** is coarse (driver-wide, other processes included). llvmpipe has no equivalent.
- **pyglet's own GL buffers** (text batches, pyglet shapes) aren't in arcade's `ctx.stats`. The probe traces arcade
  buffers only. In loop/real modes the Python object count, private bytes and video memory don't trend upward, which
  bounds any pyglet-side growth, but it wasn't traced per buffer.
- **Particle churn** (C) was measured in isolation, not as whole-frame time in a room.
