# M17-L3 Stage 2, E1: glTF emissive materials in HD-2D rooms (validation evidence; never merged)

**Implementation:** branch `feature/m17-l3-e1`, commit `9855eb2`, on `redesign/visual-editor` `bc547f9` (C1, C2 and C3
merged).

**Base for comparison:** `D:\Games\Mesh-l3s` at `6d8d69d`, whose tree is identical to `bc547f9` (the C3 merge).

**Scenes:** scratch projects only. Lakeside Village, its backup, the L1b scene and the dirty checkout are untouched;
the Lakeside timing uses Stage 1's existing scratch copy.

## What E1 does

| glTF | Read | Drawn |
|---|---|---|
| `emissiveFactor` | yes; default black; each channel clamped to 0–1 as the base colour factor is | unlit, added in linear light to the lit colour, re-encoded to sRGB |
| `emissiveTexture` | yes: its embedded image, its sampler (Nearest / Linear, Repeat / Clamp), on the first UV map; sRGB | multiplied per texel (decoded to linear) by the factor |
| texture without a factor | glTF's default factor is black: no emission (the texture isn't even read) | nothing |
| `KHR_materials_emissive_strength` | yes: multiplies the factor | above full brightness it clips (the import report says so: no bloom) |
| `emissiveTexture.texCoord` ≠ 0 | not read: Mesh reads one UV map | the material doesn't glow, and the report says why |
| malformed emission (not three numbers, NaN, a negative or non-number strength) | refused with a GlbError naming the material | — |
| other `KHR_materials_*` (transmission, unlit, clearcoat, ...) | not drawn | named in the import report: "Material extensions Mesh doesn't draw: ..." |
| "Keep pixels sharp" | also sharpens an emission texture with its own Linear sampler | — |

- **Unlit and independent of lights:** the emission term never reads the sun, the lamps or the shadows. Switching a
  lamp off, or day to night, changes nothing it draws (tested in frames). It doesn't light anything else either: a
  glowing lantern still needs a Mesh lamp for its light pool.
- **One uniform per draw:** statics are batched per material, so the emission is a per-draw uniform (and, for a
  textured emission, one texture on unit 3). A draw without emission takes the shader's old path exactly: the frame
  is byte-identical.
- **Colour space:** Mesh's frame holds sRGB values (the base colour is sampled and lit as stored). The emission is
  added in linear light, `srgb(linear(lit) + factor × linear(texel))`, so a factor of 0.5 shows as glTF viewers
  show it (188, not 128), and an emission texture with a white factor shows its own texels.
- **No new passes, no bloom, no exposure change.**
- **Not changed:** the base colour factor is still ignored when a base colour texture is present (as before), and the
  CPU preview picture in the model browser doesn't draw emission.

## Frames (`frames-base/`, `frames-e1/`, `sheets/`, `sheet_e1_crops.png`, `compare.json`)

The hd2d_rpg template village, noon / evening / night, 1280 × 720, the game's own hidden window, base vs E1:

| Scene | Noon | Evening | Night |
|---|---|---|---|
| Village as shipped (no emission in any shipped model) | **byte-identical** | **byte-identical** | **byte-identical** |
| Village, its lamp posts using a copy whose `lantern` has `emissiveFactor` [1, 0.8, 0.55] | 1,284 px changed, all on the two lanterns (luma 63 → 241) | 1,284 px (44 → 237) | 1,284 px (27 → 236) |
| Village with E1's test panels | 23,240 px: the four emitting panels only (5,802–5,831 each); zero-emission and ordinary panels **0 px** | same | same |

**Kit art:** with a factor and no texture, glTF's emission is one colour, so the lantern glows evenly (its
pixel-art frame isn't kept). An emission texture keeps per-texel detail (the panels show it). Stage 1's prototype
multiplied the emission by the base colour instead, which isn't glTF's meaning and was not kept.

## Test panels in real frames (`tooling/hd2d_emissive_demo.py`, `tests/test_hd2d_emissive_gpu.py`)

Six upright panels, one material each, imported through the catalogue as Mesh Studio imports a model:

| Panel | Expected (glTF) | Noon | Night | Night, lamp on | Night, lamp off |
|---|---|---|---|---|---|
| factor only [1, 0.5, 0.25], black base | (255, 188, 137) | exact | exact | exact | exact |
| texture only (white factor): texels (200,40,40) (40,200,40) (40,40,200) (128,128,128) | the texels, each in its quarter (uv 0,0 at the top left) | exact | exact | exact | exact |
| factor [0.5, 1, 0.25] × texture | (146,40,16) (26,200,16) (26,40,106) (92,128,66) | exact | exact | exact | exact |
| zero emission, grey base | = ordinary | equal | equal | (lamp nearer one) | equal |
| ordinary, grey base | lit as before | (93,91,88) | (38,39,44) | (52,50,50) | (38,39,44) |
| grey base + factor [0.25, 0.1, 0] | srgb(linear(ordinary) + emission), ±1 | ✓ | ✓ | — | ✓ |

- **Reimport:** the factor-only panel's emission changed to [0, 0.25, 1] and reimported: every copy is drawn
  (0, 137, 255).
- **Mesh Studio:** the edit view draws the same pixels; an edit saved with Ctrl+S and the project reopened in a new
  Studio window: still drawn.
- **Import report:** "Glows (emission, unlit): factor_only, texture_only (texture 2x2), factor_and_texture (texture
  2x2), lit_and_glowing."

## Performance (GPU timer query, RTX 4070, clocks not locked)

The renderer's whole draw: the same settled frame drawn 660 times, the first 60 dropped, one process per run, runs
alternating base / E1. p10 in ms (range over the rounds), and the median of each round's E1 − base difference:

| Shot | Base p10 | E1 p10 | E1 − base (median of paired rounds) |
|---|---|---|---|
| Village night, as shipped (5 rounds) | 0.239–0.310 | 0.236–0.276 | −0.034 |
| Village night, emissive lanterns (5) | 0.245–0.332 | 0.238–0.300 | −0.057 |
| Village night, test panels (5) | 0.229–0.323 | 0.225–0.287 | −0.009 |
| Village noon (5) | 0.231–0.281 | 0.214–0.285 | −0.011 |
| Stage 1 scratch Lakeside, lamps 1–2 (6) | 1.651–1.794 | 1.607–1.844 | +0.096 (round diffs −0.10 to +0.18) |
| Stage 1 scratch Lakeside, lamps 3–4 (6) | 0.556–0.639 | 0.531–0.614 | −0.028 |
| Stage 1 scratch cottage (6) | 0.120–0.167 | 0.108–0.170 | +0.000 |

No measurable cost: every difference is within the run-to-run spread, in both directions. GPU clocks moved between
1005 and 1185 MHz (P0 / P3) during the runs and are recorded per shot. Village: `data/perf_village/`, `data/perf_village_summary.json`. Lakeside and cottage: the same runs as E2's re-measurement, `../e2_investigation/perf_runs/` and `perf_summary.json`.

## Tests

Windows, RTX 4070, Python 3.13, scratch APPDATA, XDG and Mesh folders:

- **New:**
  - `tests/test_hd2d_emissive.py` (14, fast): each panel's emission as glTF means it; a texture without a factor;
    the strength and the brighter-than-full note; clamping; malformed emission refused (6 cases); a second UV map;
    the report's Glows line and the extensions Mesh doesn't draw; Keep pixels sharp; every shipped model has no
    emission.
  - `tests/test_hd2d_emissive_gpu.py` (15, real frames of the game and of Studio): exact pixels at noon, night,
    lamp on and lamp off; unchanged by the sun and the lamp; zero emission = ordinary; lit + glow; reimport; Studio's
    view, save with Ctrl+S, and reopen.
- **All GPU test files** (59, `MESH_GL_SMOKE=1`): **372 passed, 1 skipped** (`data/gpu_suite_tail.log`).
- **Full default suite:** **11,082 passed**, 390 skipped. The 2 failures are the known environmental
  `test_ci_shards_plugin` ones (this machine's pytest has no subtests; the base fails them the same way)
  (`data/full_suite_tail.log`).
- **ruff:** clean. **mypy:** on the changed files, 73 errors, as the base (none new). No `# type: ignore`.

**Mutation checks** (each change reverted after):

- Reader (fast tests, `data/mutations_fast.log`):
  - the strength ignored: 1 fails;
  - glTF's default factor taken as white: 4 fail;
  - a second UV map read: 1 fails;
  - Keep pixels sharp sharpening the base colour only: 1 fails.
- Shader (GPU test, `data/mutations_gpu.log`):
  - the emission added in sRGB instead of linear light: 9 fail;
  - the emission texture not decoded from sRGB: 5 fail;
  - the emission multiplied by the scene's light: 10 fail.

## Review round 1

Emission texture sampling (wrap modes per axis; Linear filtering in linear light), fixed in `e27a1a8`: `review1_sampling.md`.
