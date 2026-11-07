# M17-L2 Stage 4: the implemented cutaway, before and after (evidence; never merged)

**Implementation:** branch `feature/m17-l2-cutaway`, commit `0cfe567`, on `redesign/visual-editor` `f9f1f81`. It
reproduces this folder's 27-shot baseline (`../before/`).

**Harness:** `scripts/cut_capture_impl.py`, the same as `../scripts/cut_capture.py` except that it imports the
implementation and asserts so. It uses the same shots (`../scripts/shots.json`), the same scratch copy of the
installed L1b Lakeside and its village, the same feet placement, clocks and settling, and asserts no door was taken.

## Results (`data/comparison_impl.json`)

| | |
|---|---|
| Implementation frames vs the approved prototype (`../prototype/`) | **identical in 27 of 27** |
| Frames with the cutaway off vs before | **byte-identical in 27 of 27** (only the cut changed) |
| Player visibility with the cut | **unchanged in every shot** |
| Cut where nothing hides the player | a3 1,151 → **0**; b1 497 → **0**; b5 483 → **0**; indoor partly hidden 6,472 → **0**; village beside the shop 3,352 → **0** |
| Doorway (d2), the documented margin limitation | 4,642 → 1,899 px (the awning edge and a post within 0.25 m of the player's box; the player isn't hidden) |
| Hole size where a cut is needed | **43–64% smaller** |
| Cut outside the player's box +16 px, where needed | **65–93% less** |
| All 27 shots | cut 379,410 → 173,102 px (**−54%**); outside the box 272,457 → 66,914 px (**−75%**) |

**Sheets** (`sheets/`, one per shot): 1:1 crops of cutaway off | BEFORE | AFTER. Full-frame pairs are in `full/`:
- [a2 beside the shop](full/a2_beside_shop.png)
- [b3 behind the cottage](full/b3_behind_cottage_x608.png)
- [c1 partly hidden](full/c1_partly_hidden.png)
- [d3 inside the shop](full/d3_inside_shop.png)
- [close preset](full/e_close_behind_cottage.png)
- [indoor preset, partly hidden](full/e_indoor_partly_hidden.png)
- [village beside the shop](full/v4_village_beside_shop.png)

## GPU performance (`data/perf_summary.json`, `data/perf_runs/`)

The renderer's whole draw was timed on the GPU with a timer query: 240 frames per shot after 60 warm-up frames, on 8
cutaway shots. The old engine (`f9f1f81`) and the new one ran in separate processes, alternating
old/new/old/new/old/new, with clocks not locked. Ranges are p50 ms across the three runs:

| Shot | Before | After |
|---|---|---|
| a1 in front (no cut) | 1.86–1.91 | 1.85–1.91 |
| a2 beside the shop | 1.90–2.00 | 1.82–1.89 |
| b3 behind the cottage | 1.81–1.89 | 1.87–2.08 |
| c1 partly hidden | 2.68–2.72 | 2.66–2.71 |
| d3 inside the shop | 1.00–1.06 | 1.04–1.08 |
| close behind | 0.45–0.51 | 0.41–0.75 |
| indoor behind | 0.33–0.42 | 0.26–0.38 |
| village behind | 0.29–0.34 | 0.22–0.35 |

Every after-range overlaps its before-range. The median of the runs moves by −0.06 to +0.07 ms, within the run-to-run
spread, so **no material regression**. The shader adds about 10 ALU operations per fragment on cutaway structures
only, and no pass or read-back.

## Tests run locally (Windows, RTX 4070, Python 3.13, scratch APPDATA, XDG and Mesh user directories)

- **Full default suite** (pytest.ini addopts, `-W error`, no `MESH_GL_SMOKE`): **11,024 passed**, 358 skipped,
  **3 failed**. All three also fail on the unchanged baseline under the same conditions, so they're environmental:
  - `test_ci_shards_plugin` ×2: this machine's pytest is 8.4.2, which lacks the built-in `subtests` fixture the nested
    runs use; CI's pytest has it.
  - `test_export_bundle::test_a_project_exports_as_a_standalone_game`: a copy fails past Windows' path-length limit
    under the long scratch base path. It **passes** on this branch with a short base path.
- **GPU subset** (`MESH_GL_SMOKE=1`, per file, never the full run): **189 passed.** Files covered:
  - cutaway, starter, Studio, room Studio, runtime, floors, lighting, lamp fixture, visual standard, lab, room expand;
  - weather collisions, Studio 3D selection, character shadows, DoF, DoF Studio, gameplay viewport and HUD, new-game
    isolation, saved world;
  - shadow compositing, corners and geometry; water, scatter, interaction debugger, campfire.
- **New tests:** 10 CPU-reference unit tests (`tests/test_hd2d_cutaway.py`) and 2 GPU tests over 8 placed spots
  (`tests/test_hd2d_cutaway_gpu.py`). **Mutation check:** run against the previous shader (new Python helpers only),
  both new GPU tests fail: 3,348 px cut where nothing is hidden, and 8,629 cut px outside the opening.
- **Lint and types:** `ruff` is clean on the changed files. `mypy` reports the same 75 errors as the baseline, none in
  the changed files. No new `# type: ignore`.
