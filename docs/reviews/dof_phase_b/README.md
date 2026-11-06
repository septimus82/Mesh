# #460 Phase B: HD-2D depth of field — evidence (EVIDENCE ONLY, never merged)

Pictures and raw reports for the Phase B draft PR (`feature/460-dof-phase-b`). Captured on the owner's PC in hidden
windows (no desktop automation), with scratch copies of the HD-2D template and of Lakeside Village (the owner's
project itself untouched), by `tooling/dof_study.py` and `tooling/dof_studio.py` from the PR.

Machine: NVIDIA GeForce RTX 4070, OpenGL 4.6, Windows 11. GPU clocks were not locked (that needs an administrator
change to the system; not made), so absolute GPU milliseconds vary between runs (see "Timing method").

## Pictures (`pictures/`)

- `*_1080p_off_vs_subtle.png`: the same frame, depth of field off (left) and Subtle (right), 1920x1080 scaled to half.
- `*_1080p_same_row.png`: one screen row (yellow), off above Subtle: the white box is in the sharp band, the blue box
  is farther away on the same row.
- `lakeside_bridge_player_closeup_off_subtle_diff.png`: the followed character at the bridge, off | Subtle |
  difference x4: only the outline of the lamp post standing in front of the character changes (near-field spill).
- `studio_preview_off_vs_on.png`: Mesh Studio's editing view with the grid, preview off | Preview here on: the world
  blurs, the grid lines are the very same pixels.

Average brightness is unchanged by the blur (e.g. Lakeside shop 72.39 off, 72.51 Subtle); far grass looks duller
because its bright flower speckles are softened (less local contrast), not darker.

## Reports (`reports/`)

`rtx4070_f_<set>_<size>.json` (dof_study, 120 paired frames per view) and `studio_flow_rtx4070.json` (dof_studio).

## Timing method

`incremental_gpu_ms`: DoF off and on in **alternate frames**, a GL timer query around the renderer's whole draw
(world, then the blit or the depth of field in its place); the per-pair difference, so GPU clock changes fall on both.
`pass_alone_gpu_ms`: the composite drawn again right after the frame, GPU idle first: a lower bound (its inputs are
already resolved). Wall times include the CPU and `glFinish`; they are noisy at these frame times (6-12 ms).

| RTX 4070 | 1280x720 incremental median / p95 | 1920x1080 incremental median / p95 | 1080p pass alone median / p95 |
|---|---|---|---|
| template village (3 views) | 0.27-0.28 / 0.29-0.32 ms | 0.59-0.90 / 2.00 ms | 0.62-0.64 / 0.65-0.68 ms |
| template cottage interior | 0.22 / 0.35 ms | 0.68 / 0.73 ms | 0.72 / 0.77 ms |
| Lakeside (3 views) | 0.27-0.28 / 0.28-0.32 ms | 0.61-0.66 / 1.98-2.14 ms | 0.64-0.65 / 0.67-0.74 ms |
| Lakeside cottage interior | 0.27 / 0.31 ms | 0.64 / 0.66 ms | 0.68 / 0.70 ms |

Steady state (blocks of 40 off frames then 40 on frames, a timer around the whole window draw, template village
1080p): off 0.52-0.56 ms, on 1.66-2.13 ms median (p95 ~3.0 ms); a `glFinish` just before the pass does not change it
(not timer overlap). In Lakeside (whose frames already copy the world for water reflections) on and off are within
noise. Interpretation (not proven: clocks can't be locked here): in these light frames the GPU runs at low clocks and
reading the just-drawn depth and colour costs more than the pass alone; on a heavier frame the difference shrinks.

**Against the provisional target (Subtle <= 1.0 ms at 1080p on the RTX 4070):** met by the pass alone (p95 <= 0.77 ms)
and by the paired medians (0.59-0.90 ms); **not met** by the paired p95 in outdoor views (~2.0 ms) or the light-scene
steady-state difference (+1.1-1.6 ms). See the PR for the bounded options.

## Legacy pictures (off is the original blit)

`--baseline-only` captures of the same 8 views (template and Lakeside, 1280x720) with the old engine (59f171b, checked:
no `engine/hd2d/dof.py` loaded) and with this branch, each twice: old = old, new = new, **old = new** in all 8 views,
pixel for pixel.

## Negative controls (each mutation applied, its test run, the file restored byte for byte)

| Mutation | Caught by |
|---|---|
| depth comparison left on | test_dof_gpu (comparison off, depth test unchanged) |
| strength 0 drawn by the pass (both guards removed) | test_dof_gpu (off/zero are the original blit) |
| (strength 0 with only `active` changed) | equivalent: the radius guard still runs the blit; noted |
| focus on the camera distance | test_dof (focus) and test_dof_gpu (character stays sharp) |
| background bleeding onto sharp edges | test_dof_gpu (character and sharp band stay sharp) |
| Studio lines blurred with the world | test_dof_studio_gpu (preview: lines the same pixels) |
| editing view blurred without the preview | test_dof_studio_gpu (editing view unchanged) |
| software rendering not bypassed | test_dof_gpu and test_dof_studio_gpu (software bypass) |

Not measured here: integrated GPUs (iGPU support is unvalidated), 1440p/4K (the 24-sample cap is sparser there),
macOS, orthographic quality (it draws without error; its look is untested), GL context recreation (Mesh doesn't
recreate contexts in play; not exercised).
