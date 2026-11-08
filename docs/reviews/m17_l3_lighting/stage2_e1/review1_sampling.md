# E1 review round 1: emission texture sampling (evidence; never merged)

**Fix:** `feature/m17-l3-e1` `e27a1a8` (after `9855eb2`).

**Fixture:** `tooling/hd2d_emissive_demo.py` `sampling_glb`, imported "as exported" (not sharpened), in the game's
hidden window at night. All panels have a black base and a white emission factor, so each pixel is the emission
alone.

| Panel | Texture | Sampler | uv across the panel |
|---|---|---|---|
| `repeat_u_clamp_v` | the 2×2 test texels | Nearest, wrapS REPEAT, wrapT CLAMP_TO_EDGE | 0..2 both ways |
| `mirror_u_clamp_v` | same | Nearest, MIRRORED_REPEAT / CLAMP_TO_EDGE | 0..2 |
| `clamp_u_repeat_v` | same | Nearest, CLAMP_TO_EDGE / REPEAT | 0..2 |
| `linear_black_white` | 2×1 black, white | Linear, clamped | 0..1 |
| `linear_black_grey` | 2×1 black, grey 128 | Linear, clamped | 0..1 |

Measured on `9855eb2` (as submitted) and on `e27a1a8`. Data: `data/sampling_before_fix_9855eb2.json` and
`data/sampling_after_fix_e27a1a8.json`.

## 1. Wrap modes per axis

Red channel at the middles of the 4 × 4 texel cells (rows top to bottom). Texels: red 200 (top left), green 40,
blue 40, grey 128.

| Panel | 9855eb2 | e27a1a8 | glTF |
|---|---|---|---|
| repeat U / clamp V | [200,40,40,40] [40,128,128,128] ×3 (both axes clamped) | [200,40,200,40] [40,128,40,128] ×3 | U repeats, V clamps: = e27a1a8 |
| mirror U / clamp V | same (both clamped) | [200,40,40,200] [40,128,128,40] ×3 | U mirrors: = e27a1a8 |
| clamp U / repeat V | same | [200,40,40,40] [40,128,128,128] [200,40,40,40] [40,128,128,128] | V repeats: = e27a1a8 |

**Before:** one repeat flag for both axes. It clamped both if either axis clamped, and drew MIRRORED_REPEAT as
REPEAT.

**Now:**
- an emission texture keeps wrapS and wrapT separately, and all three glTF wrap modes work on each axis;
- any other value is refused when the model is read, naming the material.

**Not supported (unchanged, per the review):** base colour textures still use the single flag. Mixed modes clamp
both axes, and MIRRORED_REPEAT is drawn as REPEAT. No shipped model uses either (all use the default REPEAT).

## 2. Linear filtering of an sRGB emission texture

Across the panel (texel middles at 0.25 and 0.75). The glTF reference decodes texels to linear light, blends, then
the frame shows sRGB.

| At | Black / white: 9855eb2 | e27a1a8 | Reference | Black / grey 128: 9855eb2 | e27a1a8 | Reference |
|---|---|---|---|---|---|---|
| 0.1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0.375 | 62 | 135 | 137 | 33 | 67 | 66 |
| **0.5** | **128** | **188** | **188** | **63** | **92** | **93** |
| 0.625 | 188 | 223 | 225 | 96 | 112 | 112 |
| 0.9 | 255 | 255 | 255 | 128 | 128 | 128 |

- **Before:** the stored sRGB bytes were blended and decoded afterwards. Gradients in a smooth emission texture
  came out too dark through the middle: the halfway grey of a black/white edge showed 128 instead of 188.
- **Now:** a Linear-filtered emission texture is uploaded as `SRGB8_ALPHA8`, so the GPU decodes each texel before
  it blends. The shader takes the result as linear. The reference is met within the sample pixel's position on the
  panel (±2).
- **Unchanged:** a Nearest emission texture keeps the decode in the shader (no blending, so nothing differs). The
  E1 evidence frames rendered again on `e27a1a8` are byte-identical to `9855eb2`'s (all 9).
- **Limit (unchanged, as base colour textures):** there are no mipmaps, so a Linear emission texture seen much
  smaller than its texels can shimmer, exactly as base colour textures do.

## Tests on e27a1a8 (Windows, RTX 4070, Python 3.13, scratch user folders)

- **New fast tests:** wrap per axis read; a base colour texture's wrap reads as before; an unknown wrap refused
  (`tests/test_hd2d_emissive.py`, 17 in all).
- **New GPU tests:** each wrap panel at all 16 points; black/white and black/grey Linear blends against the
  reference (`tests/test_hd2d_emissive_gpu.py`, 19 passed and 1 skipped in all).
- **All 59 GPU test files:** 377 passed, 1 skipped.
- **Full default suite:** 11,085 passed. 2 environmental failures (`test_ci_shards_plugin`, as before).
- **ruff:** clean. **mypy:** 73, as the base.
- **Mutations:** 11, all caught (`data/mutations_*_r1.log`). New ones:
  - wrap read as one axis (fast);
  - one wrap for both axes in the renderer;
  - the as-submitted Linear path (blend sRGB bytes, decode after);
  - bytes read as linear without an sRGB texture (only the black/grey panel can catch this one).
