# Post-M20 repository health checkpoint

**Verdict: CONDITIONAL PASS** (details at the end). **Accepted by the owner** (2026-10-27): #389 and #395 merged;
see "Acceptance" at the end.

- **Integrated:** Stage 20E (#388) merged into `redesign/visual-editor` as `49c2769`. The merged tree is identical to
  the PR head `043d7b8`.
- **Compared with:** the post-M16 Stage 5A checkpoint (#358, merged as `5a759cf`), the last one.
- **Draft PRs for review:**
  - [#389](https://github.com/septimus82/Mesh/pull/389): exported games start their game, not Mesh's project browser.
  - [#395](https://github.com/septimus82/Mesh/pull/395): environmental settings: robust loading, validation,
    consistent AI and Studio edits.
  - The PR carrying this report: the stress study and the roadmap.
- **New follow-up issues:** #390, #391, #392, #393, #394, #396. #373 was updated with new data.
- **Evidence** (`post_m20_repository_health_evidence/`): `stress.json`, `ci_tests_jobs_24h.json` (every `tests` job's
  outcome and worst budget step) and `creator_clean_install.json` (the clean-install run, before #389).
- **Not done:** no new feature, no budget changed, no test deleted, no golden re-recorded, no rerun to get a green
  badge. #344 is still a draft and `main` is untouched. Nothing was merged beyond #388.

## Part A: Stage 20E accepted

| Check | Result |
|---|---|
| PR head and scope | `043d7b8`, 47 files, mergeable, base `1d2501d` |
| Full suite, every CI execution | **9,919 passed, 0 failed** in all five Linux and Windows executions |
| Linux, PR run 40530276385 | **every gate passed**, including the release bundle (5,942 files, 28.1 MB) and its strict verify |
| Linux, push run 40530270399 | step-time budget only: `pytest-fast` 81.0 s > 79.0 s (#373) |
| Windows, PR run 40530276385 | step-time budget only: `pytest-fast` 135.9 s > 121.8 s, plus `exception-policy-scan` (#373) |
| Windows, push run, attempt 1 | `verify-all` passed; then the release bundle's inner `release-check` failed (exit 2). Its report isn't uploaded. |
| Windows, push run, attempt 2 (one diagnostic rerun) | step-time budget only: 125.1 s > 121.8 s. The release bundle didn't run. |
| Merge | `49c2769`, pushed; the evidence is recorded on #388 |

**The Windows release-check failure was investigated, not filed under #373.**

- `mesh release check` fails locally in the same way on the base `1d2501d` and on the 20E head.
- Inside the pipeline, one golden-slice scaffold test fails with `FileNotFoundError`. The same test passes alone,
  with `MESH_REPO_ROOT` pinned, and under `mesh verify-demo` on its own. So state left by earlier steps leaks into it.
- 20E changes no release or verify code, and Linux built the bundle on the same commit.
- It is tracked as **#394**, with a proposal to upload the inner report first.

## Part B: Baseline

| Gate | #358 (`5a759cf`) | Now (`49c2769`) | Reading |
|---|---|---|---|
| Full suite, Linux | 9,609 passed, 0 failed | **9,919 passed, 0 failed** (171 skipped) | +310 tests; green |
| Full suite, Windows | 9,609 passed, 0 failed | **9,919 passed, 0 failed** | green |
| `verify-all` functional steps | all 32 pass | all pass | green |
| Step-time budgets | pass on both | **fail in 4 of 5 jobs, by 1–14 s** | #373: timing only, budgets set in #358 for a fast tier 8 % smaller |
| Release bundle | pass on both (5,854 files) | Linux pass (5,942 files); Windows `release-check` failed once | #394 (pre-existing pipeline leak) |
| Fast tier (local) | 4,467 | **4,814 passed** (6 skipped) | green |
| GPU suites (local, `MESH_GL_SMOKE`) | HD-2D 25/25 | **206/206** (every GL-gated file plus water and weather collisions) | green; still not run in CI |
| Ruff gate | ok | **ok** | |
| mypy, fresh run | gate ok | **73**, the baseline | 53 of the 73 are in four legacy editor overlays (item, dialogue, quest and prefab editors); 38 are `attr-defined` |
| Wheel | (#345 allow-list) | **3.48 MB, 1,271 files**, all 20E assets included | see Part E |
| Clean install and export | — | works; **found and fixed:** exported games opened the project browser (#389) | see Part E |
| Release replays (#359) | 13/13 stale | **13/13**; ep01's actual digest is byte-identical to #359's | no new drift |
| GPU objects, 2D rooms | +5 buffers per load (#356) | **no growth** over 4 reloads (82 ≤ 87); Play/Stop +1 once | #356's fix holds |
| GPU objects, HD-2D rooms | 36 released, +0 per reload | stable over reloads and Play/Stop (the stress room too) | healthy |

**CI performance variability, 24 hours of `tests` jobs (2026-10-26 13:05 to 10-27 13:06; each log read):**

| | Windows | Linux |
|---|---|---|
| Jobs | 48 | 48 |
| Failed **only** on a step-time budget (full suite green) | 14 (29 %) | 9 (19 %) |
| `pytest-fast` over its threshold | by 2.7–20.7 s (median 8.2 s; threshold 121.8 s) | by 0.9–6.6 s (median 2.0 s; threshold 79.0 s) |
| `exception-policy-scan` the worst step | 1 | 3 |

#373 now affects Linux too. The data is recorded on #373; the decision there stays with the owner.

## Part C: Technical debt, by reproducible impact

Each issue's status was checked before anything was investigated.

| Severity | Item | Status now | Evidence | Action |
|---|---|---|---|---|
| **High** | Exported games open Mesh's project browser instead of the game, listing the player's recent Mesh projects | **Found here; fixed** | Clean-venv export, hidden play: the browser showed and the player didn't move. After the fix: the start room shows and the player walks 150 px. | #389 (draft) |
| **High** | A room whose 3D build fails part-way (a ground texture missing) | **Found here; fixed** | `FileNotFoundError` escaped the load, so Studio couldn't open the room; 5 shader programs leaked | #395 (draft) |
| Medium | **#373** CI timing budgets | open; now Linux too | above | owner decision (options in #373) |
| Medium | **#394** release pipeline: `release-check`'s `verify-demo` fails inside the pipeline | new | reproduced locally on base and head | proposal in #394 |
| Medium | **#390** game saves embed the room's terrain and scatter | new | 25 KB → 435 KB per slot (about 1 MB at the scatter limit); re-sculpts never reach old saves | owner decision (it changes what a save restores) |
| Medium | **#391** Studio reloads the whole HD-2D room on every edit | new | the stress room's **undo 1.9 s**, room open 1.2 s | bounded follow-up |
| Medium | Validators blind to environment settings; AI `set_wind` reset the wind; a broken motion block couldn't be repaired | **fixed** | reproduced by the architecture and compatibility QA | #395 |
| Low | **#381** precipitation defects | **unchanged** | `m18b_weather_study.py defects`: snow-edge hops and strong-gust impacts byte-identical to the stored numbers; Studio drag +3.7 / +5.8 ms with weather preview (stored: 4.6 / 7.1) | open |
| Low | **#375** billboard sun shadows | **unchanged** (awaiting the owner's field decision) | renderer code path as described; 20E's canopy casters use the same stretched billboards | open |
| Low | **#357** pip-installed command gaps | **narrowed** | `mesh export` now works from a clean install. Still importing the unpackaged `tooling/`: the main menu's web-demo build and preview, and the developer commands `campaign replay-check` and `replays`. | open |
| Low | **#359** stale replay goldens | **unchanged, no drift** | 13/13; ep01 identical to the recorded actual | owner decision per case |
| Low | **mypy 73** | stable | 53 in the legacy editor's overlays | retire with the legacy editor, or type those four files |
| Low | Large-terrain undo and loading latency | measured | room load 1.29 s, Studio open 1.16 s, undo 1.90 s (128 m, 8,000 things) | #391 |
| Low | **#393** a bad `water_reflections`, sky, camera or unknown key turns a room 2D | new | seen in practice: an older engine opened a 20E room 2D ("unknown keys: motion") | bounded follow-up |
| Low | **#392** maintenance (op registry, module sizes, placement maths, clocks, study helpers) | new | architecture QA | bounded follow-up |
| Low | **#398** 2D Starter Room presentation (purple clear colour, overflowing controls hint, prompt placement, map framing) | recorded at the owner's request | the clean-install screenshots | future UI-polish task, not in this checkpoint |

## Part D: Integration and architecture

Independent architecture QA found the environmental systems **structurally sound**:

- one strict parser per subsystem;
- all 20 environment ops discovered automatically for AI and the CLI;
- Studio, `mesh author` and MCP all go through one authoring session;
- the change review is worded from document diffs, so humans and AI see the same words;
- nothing is migrated on save.

The defects were at the edges:

| Area | Finding | Resolution |
|---|---|---|
| Settings, validation | `mesh validate` / MCP `validate_scene` accepted a bad wind, particles preset, `water_reflections`, motion and water preset | #395: `environment_problems()` checked on file validation (loading still sets aside rather than refuses); all 148 committed rooms clean |
| Studio/CLI/AI consistency | AI `set_wind(gust=…)` reset the rest to calm; Studio kept it | #395: only what is given changes |
| | A broken `motion` block blocked `set_motion` and structure edits | #395 |
| | AI scatter resolves structure footprints against the process's content roots, not the project | #391 |
| Cache invalidation | Lamp shadow maps went stale after a live scatter stroke | #395 |
| | Ground ops re-parsed every scatter row (up to 50,000) several times an edit | #395 |
| Resource ownership | A part-way renderer failure leaked programs; a broken scatter model turned the room 2D | #395 |
| Repeated loading | Studio's reload re-reads every GLB and recompiles every shader per edit; two model caches | #391 |
| Static vs animated paths | 20E already separates them (still and moving programs) | healthy |
| Save/load, old projects | Saves embed the room's settings (#390). Otherwise: 224 rooms, every template and the owner's M14 Check copy load and round-trip with no unrequested rewrite | #390 |
| Runtime vs editor | `renderer.py` carries about 150 lines of Studio-only API; large modules | #392 |
| Evidence tooling | Studies chain-import each other and share private helpers; GL tests import them | #392 |

Independent compatibility QA: **PASS WITH FIXES**:

- **Old content:** all 224 committed rooms in 10 worlds load, validate and save with the same diff as the `5a759cf`
  code.
- **Templates:** every template is byte-identical to `5a759cf`'s; nothing new appears on save.
- **The owner's project:** a scratch copy of M14 Check loads its 4 rooms with nothing rewritten.
- **Settings:** wind and motion ranges agree across Studio, ops, runtime and summary.
- **2D boundary:** 2D games never import the HD-2D renderer.
- **Fixes:** the four medium findings, three in #395 and the saves in #390.

## Part E: Creator installation and export

A fresh wheel built from `043d7b8` (identical to `49c2769`), installed in an isolated venv outside the checkout, with
no `PYTHONPATH` and no `MESH_REPO_ROOT`. Everything was played in hidden windows.

| Step | 2D project (`starter`) | HD-2D project (`hd2d_rpg`) |
|---|---|---|
| `mesh new` | ok | ok |
| `mesh doctor` | exit 0 | exit 0 |
| Play | start room, player walks 150 px | the village, 45 structures, player walks 150 px |
| Studio edit (its own ops), save, reopen | rain and a wind; saved and reloaded | wind, motion on, a Meadow stroke, a torch, saved; reopened: 63 instances moving, `foliage_motion.png` (1,248 × 48) loaded from the package |
| `mesh export build` | ok (1,004 files, 9.4 MB) | ok (1,054 files, 9.9 MB), with every 20E asset |
| The bundle refers to the developer's checkout | no | no |
| The bundle played, with its own engine | **opened Mesh's project browser** (#389) | the same |
| After #389 | starts in its room, rain falling, player walks 150 px | starts, player walks |

- **Packaged assets (wheel, `share/mesh-engine`):** `foliage.png`, `foliage_motion.png`, `tree_small.glb`, the
  rocks, boulder and branch, `PROVENANCE.md`, the creator help (`docs/hd2d_preview.md`). The shaders are inline in
  the engine modules.
- **Provenance:** every 20D/20E starter asset is listed in `assets/hd2d_starter/PROVENANCE.md`, made by repository
  tooling (`scatter_art.py`, `build_scatter_models.py` in headless Blender); no third-party or PixelLab art.
- **Licence:** Mesh's own code and starter-asset licence is still unselected (an owner decision; nothing chosen
  here).
- **Studio and export:** Studio has no export command; creators export with `mesh export build`, as the help says.
- **Version mismatch:** a project saved by this build opened 2D in an engine from before 20E ("unknown keys:
  motion"). That is #393.

## Part F: Performance and stress

`tooling/health_stress_study.py`: one heavy HD-2D room built through the ops. It holds:

- 128 × 128 m of sculpted, painted ground;
- 8,000 scattered things (20E's mix, with trees);
- a pond with full reflections;
- rain (4,000) and snow (1,500);
- six lamps, two of them casting shadows;
- gusty wind, with animation on.

It was run alone, in hidden windows.

| Measure | Result |
|---|---|
| Room load (game) | 1.29 s (stored room 0.55 MB) |
| Frame wall time, decoration still / moving | **9.21 / 9.30 ms** (median, 3 alternations after 600 warm-up frames) |
| CPU's share (the frame issued) | 7.2 / 7.3 ms |
| Draw calls / shadow draws | 136 / 48 |
| GPU memory | shadow maps 36.7 MB, terrain 19.3, precipitation maps 10.5, water 7.6, targets 7.4, scatter 4.5, textures 0.8 |
| Process private memory | 972 MB playing. The GL window alone takes it from 16 MB to 827 MB (driver and context); the room adds about 175 MB, of which about 17 MB is Python. |
| Over 5 room changes | GPU objects identical each time; memory 1.06–1.09 GB, flat |
| Studio: room open / stroke commit / release to next frame / save / undo | 1.16 s / 38 ms / 166 ms / 218 ms / **1.90 s** |
| Over 5 Studio Play/Stop cycles | GPU objects identical; memory 1.264–1.275 GB, flat |

Over 20 room changes (a longer check), memory settles at 1.03–1.05 GB after the third and stays there; GL objects
are a constant 1,764. No leak.

**Independent performance QA** re-ran the study (VALID WITH CAVEATS: identical draws, GPU memory, GL objects and
Studio latencies; CPU 7.35 / 7.42 ms; wall 10.3 ms, the GPU tail varying between runs) and profiled it:

- **The frame is CPU-bound:** 7.3 ms CPU against about 2.5 ms of GPU work (each pass timed alone with timer queries
  round 20 repeats: sun shadows ≤ 0.70 ms, terrain ≤ 0.58, static models ≤ 0.53, scatter sprites ≤ 0.85, water
  ≤ 0.21, rain and snow ≤ 0.06). `wall_ms` serialises CPU and GPU (`finish()` every frame), so it is an upper bound;
  a real loop overlaps them.
- **Where the CPU goes:** box culling in pure Python (`_box_in_view`, about 712 tests a frame: 34 % of profiled
  time) and pyglet's GL error check after each of about 1,460 GL calls a frame (15 %).
- **Studio undo (2.1 s unprofiled):** the whole room is rebuilt. Terrain 652 ms (289 chunk meshes), scatter 338 ms
  (256 chunks), the panel rebuild 253 ms, and the next frame's 1 m grid overlay 301 ms. GLB reads and shader
  compiles are not significant.
- **Measured, not worth it:**
  - lamp shadow maps: drawn once, not per frame;
  - terrain chunks: 357 exist, 51 are drawn;
  - water reflection copy: ≤ 0.2 ms;
  - particles: ≤ 0.06 ms;
  - GPU sway: about 0.1 ms;
  - GPU fill rate: about 30 % busy.

**Recommendations, by measured payoff (#396):**

1. **Turn pyglet's GL error checking off in player and release builds:** CPU 7.32 → 5.30 ms. Keep it in tests and
   development: the "driver refused it" fallbacks rely on errors raising.
2. **Cheaper culling** (skip when the camera hasn't moved; test 32 m blocks first): up to −1.1 ms.
3. **Cache the lighting's derived uniforms:** −0.36 ms.

   1, 2 and 3 together take CPU from 7.32 to 3.97 ms, measured.
4. **Undo in place instead of a full reload** (#391): estimated 2.1 s → 0.1–0.4 s.
5. **Merge in-view scatter sprite chunks per block:** estimated 0.5–0.8 ms, not measured.

**Static versus animated:** the same within noise in every measure (CPU +0.1 ms moving; GPU sway about 0.1 ms).
Stage 20E's still and moving programs leave a still room at 20D's cost.

## Part G: Scope and safety

- **Hidden windows only:** every render, play and Studio session ran in hidden windows; no OS mouse or keyboard
  automation; Blender headless.
- **The owner's state is preserved:**
  - `stash@{0}`, `user_settings.json` and the untracked files in `D:\Games\Mesh` are untouched;
  - the M14 Check project was read only, through a scratch copy that was then deleted.
- **Deletions:** only paths this task created.
- **Regression tests:**
  - #389: `test_an_exported_game_starts_its_game_not_meshs_project_browser`, which fails before the fix;
  - #395: `tests/test_env_robustness.py` (6 tests) and `tests/test_env_robustness_gpu.py` (2 tests).
- **Gates:**
  - #389: fast tier 4,799 passed;
  - #395: fast tier 4,820 passed, ruff ok, mypy 73.

## Part H: Roadmap

`MESH_REBUILD.md` now records:

- the agreed engineering cadence;
- 2D animated tiles, carried forward and not scheduled;
- the roadmap as proposals:
  1. Lakeside Village visual acceptance;
  2. audio and atmosphere;
  3. rivers and waterfalls;
  4. further cinematic and environmental tooling.

## Verdict

**CONDITIONAL PASS.** The integrated branch is functionally healthy:

- the full suite is green on Linux and Windows (9,919 passed);
- the fast tier, all 206 GPU tests, ruff and the mypy baseline pass;
- GPU objects are stable across room changes and Play/Stop, also in a heavy stress room;
- old projects load unchanged;
- the wheel installs cleanly and carries every asset.

The conditions, before the Lakeside Village checkpoint:

1. **Review and merge #389:** exported games don't start (a release blocker for anyone sharing a game).
2. **Review and merge #395:** load robustness and validation of the environmental settings.
3. **Decide #373:** step-time budgets fail 19–29 % of green CI jobs on both platforms.
4. **#394 diagnostics** (release pipeline), before any release work.

Owner decisions also pending: #390 (what a save restores), #359 (replay goldens), #375 (shadow opt-out field).

Stopped for owner review. The Lakeside Village checkpoint has not been started.

## Acceptance (owner, 2026-10-27)

The owner accepted the checkpoint (CONDITIONAL PASS) and the technical direction of #389, #395 and #397. Before each
merge, the head, the scope, the regression tests and the CI were checked again, each CI job read from its log:

| PR | Head (unchanged) | Scope | CI, full suite | CI failures, and their cause | Merged |
|---|---|---|---|---|---|
| #389 | `abdcf1c` | `engine/repo_root.py`, its test | 9,904 passed, 0 failed, all 4 jobs; release bundle built on Windows (twice) and Linux | Linux push: `verify_step_budget` only (`pytest-fast` 81.1 s > 79.0 s) | `798e122` |
| #395 | `4eb6667` | 6 engine files, 2 test files | 9,925 passed, 0 failed, all 4 jobs; release bundle built on Linux | 3 jobs: `verify_step_budget` only (`pytest-fast` 80.8 / 126.4 / 131.8 s; `exception-policy-scan` once) | `a0c43eb` |
| #397 | this report | docs and the stress study | 9,919 passed, 0 failed | `verify_step_budget` only | separately, after this update |

In every failed job the only not-ok verify item was `verify_step_budget` (and its two summary records): #373, timing
only, no functional step failed. No budget was changed and no job was rerun. The merged tree (#389 + #395) was
verified before pushing: fast tier 4,821 passed; the environment robustness, motion and scatter GPU tests 8 passed.

The remaining conditions and the owner's priorities are being worked as separate draft PRs: the saved world (#390),
CI timing reliability (#373), the release-check failure (#394) and test-suite performance. The Lakeside Village and
Audio & Atmosphere work waits for the owner's acceptance of those.
