# #500: the Linux HUD check failure (Extended 43179853473, gpu ubuntu shard 1/2)

`test_the_hud_is_never_hazed` failed on CI's Linux llvmpipe at `6cf0f5b` with
`{"hud_pixels": 2653, "hud_same": false, "world_changed": true}`. That run is kept as it was; nothing was rerun.

## What the pixels were

A diagnostic copy of the check (branch `diag/500-hud-linux` @ `7eef3c6`, never merge) ran on the same runner type
(Extended run 43188531417, Linux gpu shard 1/2, `llvmpipe (LLVM 21.1.8)`). It recorded every pixel
(`hud_diag_linux.json`; crops in `crops/`).

- **28 pixels differed, each by exactly 1 level**, all inside the controls hint's white text (`crops_stacked.png`,
  bottom row: red).
- **None was fully opaque.** Each lets 0.4–0.8% of what's behind show through: 249 over black, 251 over white. Linux's
  fallback font anti-aliases its glyphs that way; Windows' font leaves no such pixels in this hint.
- **Over the dark meadow** (30–57) that sliver rounded to the same byte as over black, so the mask ("the window equals
  the HUD alone over black") counted them as opaque. The hazed ground behind them (about 130) tips the rounding by one.
- **Repeat captures** of each frame were identical: no animation, no changing text.
- **The HUD composited over the hazed world** (its coverage from the black and white frames) predicts every one of the
  28 within 1 level. No fully opaque pixel changed.

## Verdict on the five questions

| | Answer |
|---|---|
| HUD affected by the haze? | No. Only its translucent pixels show the world behind them, as they always did. |
| Mask includes non-opaque pixels? | Yes. 57 of the 2,653 masked pixels are nearly opaque (rounding coincidences), and 28 of those changed. |
| Changing text or animation? | No. Repeats are identical. |
| Transparency and anti-aliasing? | Yes. This is the cause. |
| A Linux rendering-order or framebuffer problem? | No. Opaque pixels are identical, and the translucent ones match the composite over the hazed world. |

## The correction (test methodology only)

`hud()` now draws the HUD alone over pure black and over pure white:
- **Opaque pixels** are those identical in both. No world can show through them, and they must keep the same bytes with
  and without the haze (and match the HUD alone).
- **Translucent pixels:** the coverage recovered from the two frames, laid over the plain and over the hazed world, must
  give each window within 2 levels, and the haze must have changed what is behind them.

Locally (RTX and llvmpipe): 3,168 opaque, 18,360 translucent, error 1.

**Regressions it catches** (`hud_mutations.json`, engine/game_runtime/tick.py mutated temporarily):

| Mutation | Result |
|---|---|
| The haze pass re-run over the window after the HUD | caught: all 3,168 opaque pixels change, composite error 123 |
| The HUD drawn before the world | caught: no HUD at all |
