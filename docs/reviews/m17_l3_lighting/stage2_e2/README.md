# M17-L3 Stage 2, E2: a lamp lights its own lamp head (validation evidence; never merged)

**Implementation:** branch `feature/m17-l3-e2`, commit `752c38f`, on `redesign/visual-editor` `e817746` (C1–C3 and E1).
**Base for comparison (E1):** `D:\Games\Mesh-l3e` at `e27a1a8`, whose tree is identical to `e817746`.
**Scenes:** scratch projects only, rebuilt from the hd2d_rpg template's starter kit (`tooling/hd2d_lamp_glow_demo.py`);
the Lakeside timing uses Stage 1's scratch copy. Lakeside Village, its backup, the L1b scene and the dirty checkout
are untouched. No scene, asset or serialization change.

## How it works

1. **Association** (`engine.hd2d.lighting.lamp_head`, the investigated part rule):
   - **Fixture:** the lamp's own fixture, by C1's `lamp_fixtures`: at most 1 m across, a node box within 0.15 m.
   - **Head node:** of that fixture, the drawn node nearest the lamp, within 0.15 m.
   - **Glowing parts:** of that node, the parts whose material no other node of the model uses (the kit lamp post:
     `lantern`, not the `iron` shared by its post, cap and frame), and that have no glTF emission of their own.
   - **Fail-safe, nothing glows:** no fixture; two nodes or two fixtures equally near (for example a lamp exactly on
     the lantern/cap boundary, or two posts in one place); the node has no material of its own; or its material has
     authored emission (E1's emission is drawn as it is, never doubled).
2. **Which lamps:** only the lamps the room draws (`settings.lights`: its first `MAX_LIGHTS` enabled lamps), with
   intensity above 0. A lamp without a shadow map glows like any other.
3. **Drawing:**
   - The head's parts are drawn as their own draw: the batch key gains the head's structure id. Every other part is
     batched exactly as before.
   - Each head draw gets a per-draw uniform `u_glow`: the lamp's colour (sRGB to linear) × its intensity, summed if
     two lamps share one head.
   - `MESH_FS` adds `linear(texel) × u_glow` in E1's linear emission step. The head's own texture shapes it, so the
     glass glows and the dark frame texels stay dark.
   - Shadows are unchanged: the head draw keeps its structure span, so C1's own-fixture exclusion still applies.
4. **No per-fragment box tests** (the rejected Stage 1 prototype).
5. **Lights change only by rebuilding the renderer** (any Studio edit does), so the association is worked out once
   per renderer. While a structure is being dragged in Studio, its head doesn't glow; it glows again when the drag
   is committed.

## Association: the four investigation rooms (`tests/test_hd2d_lamp_glow.py`)

| Room | Lamps | Head found | Glows |
|---|---|---|---|
| Template village | west, east | `lamp_west`, `lamp_east` | `lantern` node, `lantern` material only |
| Lakeside (kit cottage + 4 posts at Lakeside's places) | 4 | `lamp_post` … `lamp_post_4` | `lantern` only; never the cottage (lamp 4 is 0.2 m inside its corner) |
| #459 fixture room | lamp A, lamp B | `lamp_a`, `lamp_b` | `lantern` only; never `near_panel` (0.23 m from lamp A) |
| Template cottage interior | ceiling lamp | none (in no fixture) | nothing |

All 8 lamps resolve to their own lantern glass. The uncertain cases (boundary, two posts in one place, shared
material, authored emission), intensity 0 and the 9th lamp past `MAX_LIGHTS` light nothing.

## Real frames: only the heads change (`tests/test_hd2d_lamp_glow_gpu.py`, `data/demo_report.json`)

Each room is drawn as E2 draws it and with the association off (E1's frame), comparing the renderer's own pixels:

| Room | Head draws | Changed pixels | Outside the heads |
|---|---|---|---|
| Village (lamps on) | 2 | 720 | **0** |
| Lakeside rebuild (lamps on) | 4 | 424 (only lamp 1 is in view; lamp 4's lantern is hidden inside the cottage wall) | **0**, and 0 inside lamp 4's box |
| #459 fixture room | 2 | 218 (lamp B out of view) | **0** |
| Cottage interior | 0 | **0** (byte-identical) | — |
| Village, every lamp off | 0 | **0** (byte-identical, same draws and buffers) | — |

## Before / after (`frames/`, `sheets/`, `sheet_e2_closeups.png`, `data/compare.json`)

Real game frames, 1280 × 720, E1 base vs E2:

| Scene | Result |
|---|---|
| Village, lamps on: noon / evening / night | 1,284 px changed, all on the two lanterns (luma 63→114 / 44→106 / 27→103) |
| Village, lamps off: noon / evening / night | **byte-identical** |
| Village night: east lamp blue | the east head turns blue; 1,284 px |
| Village night: west lamp intensity 0.5 / 3 | the west head dimmer / brighter |
| Village night: west lamp intensity 0 | only the east head changes (642 px) |
| Lakeside rebuild, night | 784 px, the visible heads only |
| #459 fixture room, night | 393 px, lamp A's head |
| Cottage interior | **byte-identical** |

**Glass and frame** (the west lantern, the most common colour in the brightest and darkest quarter of its changed
pixels):

| Scene | Glass: E1 → E2 | Frame texels: E1 → E2 |
|---|---|---|
| Noon, lamp 1.6 #ffb060 | (147,124,75) → (255,213,91) | (26,28,35) → (66,50,43) |
| Evening | (103,79,46) → (255,195,71) | (19,18,22) → (63,45,33) |
| Night | (55,52,37) → (255,188,66) | (10,12,17) → (61,43,30) |
| Night, intensity 0.5 | → (194,118,48) | → (35,25,22) |
| Night, intensity 3 | → (255,245,82) | → (82,58,38) |
| Night, blue lamp #5080ff (east) | → (114,141,153) | → (19,31,74) |

**Reading:**
- The glass glows in its lamp's colour (amber (255,188,66) for the amber #ffb060 light) and isn't washed to
  white: blue stays well below red even at intensity 3.
- The light pools on the ground and the post and cap are unchanged.
- A blue lamp seen through amber glass gives a cool grey-blue, as tinted glass would.

**Asset limitation (not changed):** the kit lantern's UV layout puts its dark frame texels across the middle of each
face, so only the side strips are glass. Those frame texels, multiplied by the glow, take a dark warm tint (61,43,30
at night) rather than staying black. A lantern texture with more glass would show more of the glow, but that is a
content change, not made here.

## Performance (`data/perf_e2_summary.json`, `perf/`, `data/perf_pair_*.json`)

**Draws and memory:**

| Shot | Draws, E1 → E2 (main pass) | Sun shadow pass | Lamp-head draws | Buffer / texture bytes |
|---|---|---|---|---|
| Village, lamps on | 31 → 32 | 30 → 31 | 2 | identical |
| Village, lamps off | 31 → 31 | 30 → 30 | 0 | identical |
| Lakeside rebuild | 14 → 17 | 13 → 16 | 4 | identical |
| #459 fixture room | 5 → 6 | 4 → 5 | 2 | identical |
| Stage 1 Lakeside, lamps on | 61 → 64 / 65 → 68 | 29 → 32 | 4 | identical |
| Stage 1 Lakeside as L1b ships it (lamps off) | 65 → 65 | 29 → 29 | 0 | identical |
| Cottage | 7 → 7 | — | 0 | identical |

- **Batching:** each lit head leaves its material's batch and becomes one draw, in the main pass and in each shadow
  pass that draws it (the sun's every frame; a lamp's shadow map only when it is redrawn). When every lamp post of
  a material is lit, that batch empties, so the net cost is heads − 1 per pass.
- **Memory:** head vertices move out of the batch rather than being copied, so buffer and texture memory are
  unchanged.

**GPU time, interleaved in one process** (`scripts/perf_pair.py`): the game's E2 renderer and a twin built with no
heads (E1's batches), drawn alternately 600 times each on the same settled frame. Both see the same clock state; the
median of the per-pair differences is shown, over 3 runs:

| Shot | E2 − E1 (ms, median of pairs) |
|---|---|
| Village, lamps on | 0.000, 0.000, −0.001 |
| Lakeside rebuild | 0.000, 0.000, 0.000 |
| #459 fixture room | 0.000, 0.000, 0.000 |
| Village, lamps off | 0.000, 0.000, 0.000 |
| Stage 1 Lakeside, lamps 1–2 view (4 heads) | +0.009, +0.008, +0.008 |
| Stage 1 Lakeside, lamps 3–4 view (4 heads) | +0.011, +0.009, +0.007 |
| Stage 1 Lakeside, L1b (lamps off; the two renderers draw the same) | +0.024, +0.056, +0.038 |

The L1b row is the method's own bias in that scene: no heads, the same batches and the same shader, yet
+0.02–0.06 ms. The Lakeside lamp rows sit below that bias. **The heads' cost is under this harness's resolution
(about 0.01–0.05 ms), against the rejected prototype's +0.53 ms.**

**Process-per-run alternating (6 rounds, base E1 vs E2)** were run too (`perf/base-*`, `perf/e2-*`), but they're not
a clean comparison. The GPU sat in power-saving states for these light frames (P8 / P5, 210–555 MHz, memory 405
or 810 MHz, recorded per shot), and the state differed between processes. For example, in the Stage 1 Lakeside lamps
1–2 view, base ran at P5 / 810 MHz and E2 mostly at P8 / 405 MHz, which gave an apparent +0.13 ms.

**With every lamp off:** E2's only difference from E1 is one extra uniform compare per structure fragment
(`u_glow != 0`); batches and draws are identical. Cross-process, the cottage (no heads) read +0.014 ms in 6 of 6
rounds at similar P5 clocks, and the village and L1b with lamps off were within ±0.4 ms with mixed signs. At most a
few hundredths of a millisecond. Clocks weren't locked: locking them needs a system setting, which wasn't changed.

## Tests

Windows, RTX 4070, Python 3.13, scratch APPDATA, XDG and Mesh folders:

- **New:**
  - `tests/test_hd2d_lamp_glow.py` (7, no GPU):
    - the eight lamps of the four rooms;
    - Lakeside lamp 4 and the cottage; #459's panel;
    - the ceiling lamp;
    - uncertain heads (boundary, two posts, out of reach);
    - shared and authored materials;
    - the glow's colour × intensity in linear light, intensity 0, two lamps in one lantern;
    - the 9th lamp past `MAX_LIGHTS`.
  - `tests/test_hd2d_lamp_glow_gpu.py` (10, real frames and Studio):
    - per room, only head pixels change;
    - no head: E1's frame with E1's draws;
    - draws and memory;
    - colour; intensity, 0 and off;
    - a lit lantern, not a white box (pixel art kept: the brightest tenth of a head over 2.5 × its darkest);
    - Studio edit, undo / redo, Ctrl+S, reopen.
- **All 60 GPU test files:** **387 passed, 1 skipped.** E1's emissive tests pass unchanged: authored emission
  behaves exactly as in E1.
- **Full default suite:** **11,092 passed.** 2 environmental failures (`test_ci_shards_plugin`: no pytest subtests
  here, as on the base).
- **ruff:** clean. **mypy:** 73, as the base. No `# type: ignore`.
- (A first GPU run by `scripts/regress.sh` expanded `tests/*_gpu.py` in the wrong folder and ran only 300 tests. It
  was rerun from the E2 worktree over all 60 files; the result above is that rerun.)

**Mutation checks** (each change reverted after; `data/mutations_*.log`):

- Association (no-GPU tests):
  - no unique-material rule: 4 fail;
  - a tie not refused: 1 fails;
  - intensity 0 kept: 1 fails;
  - lamps past `MAX_LIGHTS` glowing: 1 fails.
- Frames (GPU tests):
  - glow not multiplied by the head's texture (a flat box): 1 fails;
  - heads left in their material's batch (glow on the whole batch): 6 fail;
  - every node in reach glowing: 5 fail.
