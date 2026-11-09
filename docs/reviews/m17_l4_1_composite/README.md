# M17-L4-1: shared HD-2D final composite (evidence only, never merge)

**What this is:** the evidence for draft PR `feature/m17-l4-1-composite` (one final-composite stage in
`Hd2dRenderer`, identity only, no visible change), on `redesign/visual-editor` `0fa2f25`.
**Machines:** NVIDIA RTX 4070 (Windows 11), and Mesa 26.0.3 llvmpipe loaded locally from CI's pinned, hash-checked
archive (`../m17_l4a_postfx/scripts/mesa_preload.py`).
**Scenes:** the scratch copy of the installed Lakeside Village (L1b, `dd850648…`). Nothing installed was changed.

## Exactness against 0fa2f25 (`exactness/`)

**Method:** `scripts/exact.py` ran three times, then the results were compared:
1. in `0fa2f25`'s worktree (`rtx_base.json`);
2. in the PR's worktree with the composite off (`rtx_off.json`);
3. in the PR's worktree with the forced identity (`rtx_identity.json`).

**What each run rendered:**
- Lakeside village, shore and cottage at authored / evening / night with lamps (E2 heads), plus the interior, each with
  and without DoF Subtle.
- Every frame read back as RGBA from an offscreen target.
- Studio's canvas of the start room, with and without its lines.

**Results** (`compare.txt`):
- **Off:** 22 / 22 identical, with the same draw calls, renderer GL objects and live GL objects per kind.
- **Identity:**
  - 21 / 22 identical;
  - +1 program, and +1 texture and +1 framebuffer with the DoF (the chain target);
  - the only different frame is `studio_canvas_lines`: 235 of 23,037 line pixels differ, each by 1 level, and none
    off the lines (lines drawn after the picture, premultiplied, as the DoF has done since #460).

## Timing (`perf/`)

**Final stage alone** (`mixed_*Mesh-l4c*.json`, "passes"):
- identity = blit on the GPU (0.0072 vs 0.0072 ms at 720p P0; 0.0143 vs 0.0138 at 1080p), +0.012 ms CPU submission;
- DoF → chain → identity = DoF +0.01 ms GPU (+0.8 ms on llvmpipe), +0.07 ms CPU.

**Off, base vs PR** (`samemodes_*`: alternating processes, the same modes): indistinguishable (`table_samemodes.txt`).
- **llvmpipe off:** base 25.37 / 25.51 / 26.03 ms, PR 25.14 / 25.22 / 25.28 ms.
- **RTX off:** GPU base 1.94 / 1.86 / 1.97, PR 1.97 / 1.88 / 1.93; CPU 6.90 / 6.83 / 6.85 vs 6.88 / 6.86 / 6.88.

**Earlier mixed-mode runs** (`mixed_*`, the PR's process also timing the identity modes): the PR seemed +0.3–0.6 ms on
llvmpipe. That came from the different work in that process, not the off path: the same-modes rerun above removes it.

**RTX clocks:** unlocked, P0 to P8 (`*_clocks`); compare within a run.

## Tests

- **`data/study_report_llvmpipe.json`:** `tooling/hd2d_composite_study.py`'s report under llvmpipe (CI's renderer):
  the DoF is bypassed and the identity is identical.
- **`data/mutations.log`:** 11 mutations, all caught.

## Pre-existing, found here (not changed)

- **`scripts/probe_visits.py`:** GL buffers grow by ~428 per village↔cottage pair at `0fa2f25` and in the PR alike.
  Textures, framebuffers and programs are flat.
- **`scripts/probe_gamepath.py`:**
  - Mesh Studio's game camera is never placed: a camera-less draw first moves it over the player.
  - The sun's shadow fit follows the game camera and aspect whichever camera draws, so a Studio picture's shadow
    edges (~0.2%) depend on where the game camera is.
