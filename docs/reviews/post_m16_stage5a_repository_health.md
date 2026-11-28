# Post-M16 Stage 5A: repository health checkpoint

**Verdict: PASS.** Stage 5A is hardened and integrated (#355). Every gate of the normal CI job now passes on Linux and
Windows: the full test suite, all 32 `verify-all` steps, the enforced per-platform step budgets, the artifact baseline
diff, and the release bundle build and strict verification.

- **This had never happened before.** Each gate after pytest was being reached for the first time, at some point in
  this checkpoint.
- **Where it is.** The work is in draft PR [#358](https://github.com/septimus82/Mesh/pull/358), head `b697b6f`, CI
  runs `40195573992` (push) and `40195576678` (PR).
- **The owner's decisions are implemented:** Windows Mesa (pinned and SHA-256-verified, no third-party action);
  step budgets (de-duplication, then per-platform budgets from repeated CI measurements); and #360 option A (total
  time is informational, and broken bundles are errors).

**Tracked separately, as the owner directed:**

- **Release-only: [#359](https://github.com/septimus82/Mesh/issues/359).** The `ship` job's 13 replay goldens are
  stale, so that job stays red until each digest change is checked against intended gameplay.
- **Still open:** #356, #357, the #345 packaging gaps, and replacing the three unverified sprites with original,
  redistributable art.

#358 stays a draft for owner review. Stage 5B should start only after that review.

This checkpoint covered five things:

- **Stage 5A:** hardened and integrated.
- **The full CI test suite:** red for a long time; reproduced, diagnosed and fixed, apart from what is listed under
  "remaining".
- **The 2D lighting GPU lifetime defect** that Stage 5A found: confirmed and fixed.
- **Studio's editing latency:** profiled, with one measured improvement.
- **Packaging and provenance:** audited, with a recommended integration plan.

No Stage 5B, Stage 6 or weather work was done. #344 is still a draft, and `main` is untouched.

## Stage 5A integration (Phase 0)

| Item | Result |
|---|---|
| Hardening (on #355, commit `a231858`) | **One path rule**, `engine.hd2d.settings.asset_path`, for a structure's model and the ground texture: project-relative, with no absolute or drive path and no `..`. It runs in `parse_hd2d`, so scene loading, `project_ops` and AI changes all meet it. **Containment** (the real file must lie inside the project, symlinks followed) is checked where the project's files are known: `model_problem`, used by Mesh Studio and authoring; and the runtime resolver, where a scene's assets must lie under its content roots (`engine.paths.is_path_under_content_roots`). **Non-finite numbers** (NaN, ±infinity) are refused by the settings and by the structure ops. |
| Human vs AI | Both go through the same `project_ops` operations and the same `model_problem`. A test checks that they produce the same error text for the same bad input. |
| Tests | `tests/test_hd2d_asset_paths.py` has 30 fast tests. They cover: path shapes; a link out of the project (a symlink, or a junction on Windows, where symlinks need a privilege), both through `model_problem` and through the runtime; NaN and ±infinity everywhere; and matching wording. |
| Checks before merging | Fast tier 4,467 passed, 0 failed. Type gate and ruff gate ok. HD-2D GPU suites 25/25. The full CI suite failed with the **identical** 19-test failure set as before (Linux). |
| Merge | **#355 merged as `35b7c03`**. The merged tree is identical to the PR head. It contained only the Stage 5A files and the validation fix. |

## Audit findings (Phase 1)

Severity: **High** means it blocks or corrupts something users rely on; **Medium** is a real defect with limited
reach; **Low** is minor or hygiene.

| # | Severity | Finding | Evidence | Status |
|---|---|---|---|---|
| 1 | High | **The full CI `tests` job never passed, so `verify-all`'s later gates (type gate on Linux, ruff, exception budgets…) and Windows CI hadn't really run for a long time.** The jobs use `fail-fast: true`, so every Linux failure cancelled Windows. The "Windows failure" on PRs was a cancellation. | CI runs on #347, #349, #350, #353, #355: the Windows job was `cancelled` whenever Linux failed | Fixed (Phase 2); see CI results |
| 2 | High | **Committed content stored Windows paths:** 142 `path` / `scene_path` values in `worlds/*.json`, `plans/*.json` and `plan.json` used `\`. On Linux a backslash is part of a file name, so tools and tests reading those files found nothing. The engine's own loader normalises separators, so games ran. | 15 of the 26 CI failures named `packs\core_regions\scenes\…` as missing; all 9 named scene files are tracked | Fixed (data normalised; the plan executor writes `/`) |
| 3 | Medium | **The 2D lighting layer was never released** on a room load. Its lights point back at it, so its textures, framebuffers and programs waited for Python's cycle collector. | Phase 3: +49 of each over 4 reloads plus 4 Play/Stop; all freed only by `gc.collect()` | Fixed |
| 4 | Medium | **2D rooms leak about 5 GL buffers per room load,** never freed (not even by `gc.collect()`). | Phase 3: buffer counts 87 → 142 over 12 reloads, +5 each; HD-2D rooms +0 | **Open: [#356](https://github.com/septimus82/Mesh/issues/356)** |
| 5 | Medium | **User-facing commands import the unpackaged `tooling/` folder** (`mesh export`, the web-demo export, the asset manifest, campaign replay), so they fail in a pip install. | 20 `from tooling…` imports in `engine/` and `mesh_cli/` | **Open: [#357](https://github.com/septimus82/Mesh/issues/357)** |
| 6 | Medium | **Test isolation:** a full test run rewrote the tracked `user_settings.json` (the player settings) and left `tests/fixtures/background_layer_red.png` behind. This explains a modified `user_settings.json` in a checkout after running tests. | A full run in a clean worktree modified exactly those two files | Fixed (the session uses a temp settings path; the guard covers `user_settings.json`; the test draws in `tmp_path`) |
| 7 | Medium | **An unknown prefab, asked for with no catalogue path, fails differently by OS** (`ai_ops.add_entity_from_prefab` read the project folder as the catalogue) | Linux: "is a directory"; Windows: passes | Fixed |
| 8 | Low | **Studio's icon loading leaves files open** on Linux (pyglet's decoder): a `ResourceWarning` that fails under `-W error` | 2 Linux failures | Fixed |
| 9 | Low | **Fixture defects** that only show on some platforms or Python versions: the audit-trend test used a relative temp path (Python 3.11 vs 3.12+); the background-layer GPU test lacked `_foreground_layers` (#351). | CI on 3.11; #351 | Fixed |
| 10 | Low | **The packaging hygiene gates flagged CI's own build products** (`.egg-info`, `__pycache__`, the mypy cache), all of which are gitignored | 3 failures on every CI run | Fixed: they now fail when git would take a cache in (tracked, or not ignored) |
| 11 | Low | **The Linux type gate:** Windows-only GUI tooling (`gui_driver`, two acceptance scripts) was 12 Linux-only mypy errors. It hadn't been seen, because the gate never ran (#1). | `mypy --platform linux` | Fixed |
| 12 | Low | **GPU-gated tests never run in CI** (`MESH_GL_SMOKE` isn't set). #351 rotted unnoticed. | — | Recommendation: run the GPU tier locally before each merge, as these stages did, or add a scheduled GL lane |
| 13 | Low | **Studio's per-frame UI layout:** arcade 3's `UIManager.draw()` lays every widget out every frame, about 4.4 ms of a 10 ms Studio frame (profiled), in 2D and HD-2D alike. | cProfile (Phase 4) | Noted; proportional to widget count, not a defect |
| 15 | Medium | **`verify-all`'s step-time budget is out of date and has never been enforced.** The fast tier takes 87–129 s against a 43 s budget set in June, when it had 62% fewer tests. Now that CI reaches `verify-all`, this is the last red check on both OSes. | CI run `40187015582`; local timing; test counts at `c25c2b2` and now | **Fixed:** de-duplicated, then per-platform budgets from 6 CI samples each; enforced and passing on both OSes (see CI results) |
| 16 | Medium | **CI's "Diff against baseline" gate can't pass reliably.** Total `verify-all` time is compared with a fixed 50 ms threshold against one local run from February (36.5 s then, 115 s now, with more than 10% spread between identical runs). It had never been reached. | CI runs `40193191718`, `40193196720` | **Fixed (option A):** total time is informational; broken bundles are errors; the report is built after the summary. Passing in CI. [#360](https://github.com/septimus82/Mesh/issues/360) has to be closed by hand when #358 merges (its base is not the default branch, so GitHub won't close it) |
| 17 | Low | **All 13 release replay goldens are stale.** They're used only by the `ship` job (dispatch and `release/` branches); the base branch gives identical digests. | CI run `40190965398`; local runs on the base and the branch | **Open: [#359](https://github.com/septimus82/Mesh/issues/359)** |
| 14 | Low | **Repeated selections grow Python memory slowly**: a one-off ~3.8 MB warm-up (pyglet vertex domains, glyph caches), then about 4 KB per selection inside pyglet and arcade-gui. GL objects stay flat and nothing goes stale. | `tracemalloc` over 120 selections plus 20 edit/undo cycles | Noted |

**Checked and found healthy:**

- **The HD-2D vs 2D boundary.** 2D games never import the HD-2D renderer or GLB reader (a test checks this); only the
  light `engine.hd2d.world` is imported.
- **The HD-2D renderer's GPU ownership.** All 36 objects are released on Edit/Play/Stop, and a reload adds +0.
- **Scene load and unload.** The renderer is released before the next is built.
- **Save/load integrity.** The HD-2D floors, elevation and structure tests, plus the `projects.json` /
  `user_settings.json` guard.
- **Generated docs.** `mesh docs --verify` passed.
- **Dependencies.** Every third-party import is declared, or is a transitive dependency of one (`pyglet` via arcade,
  `referencing` via jsonschema). NumPy is not imported by the engine.

**Not changed, deliberately:**

- **The module-instance forwarding shims** in `engine/editor_controller.py` (e.g. `load_prefab_palette`): their
  non-use isn't proven, so they stay.
- **The legacy editor:** kept off the normal path since #347.
- **The `engine/editor/hd2d*` and `engine/hd2d_debug_model.py` modules:** the legacy editor's own "HD-2D" depth
  tools. They are unrelated to `engine/hd2d` and only confusingly named; no removal without a usage audit.

## Known failures (Phase 2)

All of these were reproduced against the integrated branch, from CI logs on Linux and from local runs on Windows.

| Failure(s) | Count | Class | Fix |
|---|---|---|---|
| golden slice ×7 variants and the boss UX contract, golden-slice content invariants ×7, lighting showcase intent, lighting demo uses variant e, prefab variant consistency, world vertical slice | 15 + subtests | **Content defect (platform):** backslash paths in committed worlds and plans | Normalised the data to `/`; the plan executor normalises what it writes; new test |
| `test_no_egg_info_directories`, `test_no_forbidden_directories_in_workspace`, `test_no_pycache_dirs_in_source_tree` | 3 | **Test-environment problem:** the gates ran after CI's own install, compile and cache steps | They fail on what git would take in; they still fail when git can't tell |
| `test_audit_trend_command` | 1 | **Fixture defect (Python 3.11):** a relative temp path reused after `chdir` | Resolve it |
| `test_add_entity_unknown_prefab_is_structured_not_raised` | 1 | **Real engine defect (platform):** an empty catalogue path read the project folder | Use the default catalogue when no path is given |
| `test_the_window_gets_the_mesh_studio_icon…`, `test_launch_editor_pins_project_without_using_last_root` | 2 | **Real defect (Linux):** icon files left open | Open and close them ourselves |
| `test_doctor_assets_prefab_paths` | 1 | **No separate fix needed.** It passed on Linux once the fixes above landed. Its assertion now prints the report if it ever fails again. | — |
| #351, `test_scene_controller_draw_composites_background_layer` (GPU-gated) | 1 | **Fixture defect:** the hand-built controller lacked `_foreground_layers` | Fixture; it also draws into `tmp_path` now |

- **No artwork was restored or added for any test.** None of the failures depended on missing third-party assets.
- **No test was disabled.** No assertion was removed, and no baseline was accepted silently. The exception-envelope
  ratchet's line baseline moved by one line for an unchanged handler, following its own documented practice.

## CI results

Final: PR [#358](https://github.com/septimus82/Mesh/pull/358) head `b697b6f`. Push run `40195573992` and PR run
`40195576678` gave the same result. Every step was read from the job logs, not inferred from a green check.

| Check | Linux (ubuntu-latest, py3.11) | Windows (windows-latest, py3.11) |
|---|---|---|
| `arcade3-canary` (required) | **pass** | — |
| `web-smoke` (required) | **pass** | — |
| Full pytest suite | **pass**: 9,609 passed, 0 failed, 87 skipped, 53 subtests | **pass**: 9,609 passed, 0 failed, 87 skipped, 53 subtests |
| `verify-all`: all 32 steps | **pass** | **pass** |
| Step-time budgets, enforced (finding 15) | **pass**: `pytest-fast` 64.6 s and 56.0 s (threshold 79.0 s) | **pass**: `pytest-fast` 60.2 s and 103.1 s (threshold 121.8 s) |
| Artifact bundle validation | **pass** | **pass** |
| "Diff against baseline" (finding 16) | **pass**: 0 regressions, 0 changed, 1 informational (`timing.total_ms` 36,470 → 113,499 and 94,622 ms) | **pass**: 0 regressions, 0 changed, 1 informational (36,470 → 96,249 and 172,873 ms) |
| Release bundle build (seeded) | **pass**: `release_bundle.zip`, 5,854 files, 25.7 MB | **pass**: 5,854 files, 25.8 MB |
| Release bundle strict verify | **pass**: 5,856/5,856 verifiable files, sealed manifest verified, 0 extras, missing or mismatches | **pass**: the same |

- **The reports are accurate now.** In all four jobs, `verify_report.json` read `verify_all_summary.json` and
  records `verify_summary.ok: true`, with no failing steps. The diff's former `verify_summary.ok: true -> null`
  "change" is gone.
- **Total time is still visible.** It appears in the diff's text, Markdown and JSON output, and in the PR comment:
  "No regressions. Improvements: 0, Changed: 0, Informational: 1", then `timing.total_ms`: `36470` -> `94622`. The
  spread across these four runs (94.6–172.9 s) is why a fixed 50 ms total-time gate couldn't work.

### The baseline gate fix (#360, owner decision: option A)

**`mesh_cli/artifacts_diff.py`:**

- **Total time is informational.**
  - A `timing.total_ms` difference beyond the 50 ms threshold is a new `informational` category, listed last. It
    appears in text ("INFORMATIONAL (does not fail):"), Markdown ("## Informational (does not fail)") and JSON
    (`informational` plus `counts.informational`), with the base and current values.
  - It never counts as a regression, and `ok` in the JSON still means "no regressions".
  - The baseline's 36,470 ms and the zero-sentinel rule are kept. The field isn't suppressed and the baseline isn't
    zeroed.
- **Everything else still fails `--fail-on-regression`:** `verify_summary.ok`, the exception, step and
  authoring-trace budget `ok` flips, swallowed-exception total, distinct and `ok`, unchanged.
- **Broken bundles are errors.** A `verify_report.json` that is missing (also behind an `index.json` pointing to
  nowhere), corrupt, not a JSON object, or without a boolean `verify_summary.ok` raises `ArtifactsDiffError`, in
  either the base or the current bundle.
  - The command exits 2 whether or not `--fail-on-regression` is set. It prints the reason to stderr and writes it to
    `--out`.
  - Before this, it printed an error and exited 0.

**`mesh_cli/verify.py`** (the ordering defect):

- **The outcome is settled first.** The required-metric-artifacts check now runs before the reports.
- **Then the summary.** `verify_all_summary.json` is written next, followed by the reports derived from it:
  `verify_report.json`, the release notes (which read it too and had the same staleness), `verify_summary` and
  `index.json`.
- **Rewritten at the end,** as before, so it also lists those reports. They read only the summary and never each
  other, so there is no circular dependency.

**Also changed:**

- **`.github/workflows/ci.yml`:** the step summary and PR comment count and list informational items.
- **`docs/generated/cli_snapshot.json`:** regenerated for the new `--fail-on-regression` help text. It also lacked
  the `author` command. `docs/generated/commands.md` is stale too, but its generator (`engine/tooling/docs_command.py`)
  is referenced nowhere and CI doesn't check it, so it was left alone and noted here.

**Tests:**

- **`tests/test_artifacts_diff.py`:** 76 passing.
  - The 3 tests that pinned the old behaviour now pin the new one.
  - New cases:
    - the committed baseline passes a slow but healthy run (36,470 → 115,419 ms, exit 0, reported);
    - Markdown and JSON keep the total time;
    - a verify failure, step budget, exception budget, swallowed total or swallowed distinct regression still exits 2,
      even when total time also changed;
    - five kinds of broken current bundle exit 2, with and without the flag, and a broken baseline does too.
- **`tests/test_verify_report_reflects_completed_run.py`:** new, 4 tests, driving the real
  `_build_verify_all_payload` with stubbed steps.
  - A successful run reports `ok: true` from the summary (in the report, the release notes and the index), and the
    index lists the report and the summary. The run passes the real CI baseline diff.
  - A failed step reports `ok: false` and names the step; the diff exits 2.
  - A violated, enforced step budget makes the run fail, and the report says so; the diff exits 2.
  - The report, index, summary and release notes are byte-identical across runs.
  - With the old `verify.py`, three of the four fail. The determinism test passes either way.
- **Locally on Windows:** 188 related verify and diff tests pass, and the fast tier passes (4,499). The type gate,
  `mypy --platform linux` on the changed files, the ruff gate and the CI workflow contract tests pass.

### History

| Point | Linux | Windows |
|---|---|---|
| Before this checkpoint | 26 pytest failures; `verify-all` never ran | always cancelled (`fail-fast`); when run, 13 OpenGL failures |
| `09f3841` (run `40187015582`) | pytest and 32 steps pass; step budget fails | same |
| `c877698` (runs `40193191718`, `40193196720`) | everything up to the baseline diff passes; the diff fails (#360) | same |
| `b697b6f` (runs `40195573992`, `40195576678`) | **every step passes, including the release bundle** | **same** |

**Another long-hidden failure, found by a manual dispatch: the release replay suite ([#359](https://github.com/septimus82/Mesh/issues/359)).**

- The `ship (release branches)` job runs only on `workflow_dispatch` and on `release/` branches. Its golden replay
  ratchet reports a mismatch on all 13 cases.
- The base branch `35b7c03` produces byte-identical digests, as do Linux and Windows, so #358 didn't cause it. The
  goldens date from February.
- They were not re-recorded. Push and PR runs never run this job.

### Windows Mesa (decision 1)

- **The action is gone.** `ssciwr/setup-mesa-dist-win@v2` was a moving tag. Audited at `6657792`: it downloads
  the archive without any integrity check and runs the archive's `systemwidedeploy.cmd`, which copies into System32
  and registers an OpenGL driver.
- **Source and version.** The job downloads `mesa3d-26.0.3-release-msvc.7z` (68,883,699 bytes) from
  [pal1000/mesa-dist-win](https://github.com/pal1000/mesa-dist-win/releases/tag/26.0.3) release `26.0.3`, published
  2026-03-20 by the maintainer `pal1000`.
- **Integrity.**
  - It checks the archive's SHA-256, `de1ec45c906164de2c046288a8969e83cf2d51d031dc8dfd1f9371bb31cd6755`, before
    extracting anything. That digest is the one GitHub recorded when the asset was uploaded (the API's `digest`
    field), not one computed from a download. The asset's upload time is earlier than the release's publication, so
    it hasn't been replaced since.
  - A mismatch fails the job.
- **Installation.**
  - Only `opengl32.dll` and `libgallium_wgl.dll` (plus `libglapi.dll`, if a release has one) are copied beside the
    job's `python.exe`. Windows loads them before System32's. `GALLIUM_DRIVER=llvmpipe` is set.
  - No script from the archive runs; nothing is written to System32 or the registry. Everything lives on the
    disposable runner.
  - The step then opens a hidden pyglet window. CI logs:
    `OpenGL 4.5 (Compatibility Profile) Mesa 26.0.3 | llvmpipe (LLVM 22.1.1, 256 bits)`.
- **Updating.** The procedure is in the step's comment in `.github/workflows/ci.yml`:
  1. Choose a release.
  2. Read its digest with
     `gh api repos/pal1000/mesa-dist-win/releases/tags/<version> --jq '.assets[] | select(.name | endswith("-release-msvc.7z")) | .digest'`.
  3. Change `MESA_VERSION` and `MESA_SHA256` together.
- **Not changed.** The `tests` job keeps `pull-requests: write`, which the baseline-diff PR comment uses. The Mesa
  step doesn't need it.

### Step-time budgets (decision 2)

**De-duplication first.** No assertion or boundary was removed.

- **Exception-policy scan.**
  - The scanner now walks statements only, since handlers and `raise` can't occur in expressions. Its output on
    `engine`, `mesh_cli`, `tooling` and `tests` is byte-identical, in the same order, and it is 27% faster.
  - The schema, baseline and missing-reason tests share one session scan, and the determinism test still compares
    two independent scans. That is 5 scans per fast run down to 2: 15.5 s → 6.4 s locally.
  - A new test pins the statement walk to `ast.walk`'s handlers.
- **Creator-mode import boundaries.**
  - 20 checks each started a fresh Python, about 1 s each, because `engine.editor` imports arcade. They now share one
    long-lived interpreter, or one with arcade unimportable from the start.
  - A check whose watched modules are already loaded falls back to a fresh interpreter, so the answers are a fresh
    interpreter's. The snippets and assertions are unchanged.
  - **Proof:** with a planted violation (a bridge import and an `arcade` import), the original and the converted tests
    failed on exactly the same 18 cases.
  - The helper has its own test (`tests/test_shared_python_helper.py`).
- **Result.** The fast tier went from 129 s to 99 s on the owner's PC.

**Before and after on CI (ms).** "Before" is run `40187015582`. "After" is 6 samples per platform: runs
`40189903113` ×2, `40189903845` ×3 and `40190965398`.

| Step | Linux before | Linux after: median (range) | Windows before | Windows after: median (range) |
|---|---|---|---|---|
| `pytest-fast` | 86,551 | **63,237** (53,118–64,097) | 123,391 | **93,708** (65,511–109,785) |
| `exception-policy-scan` | 3,682 | **2,845** (2,441–3,018) | 4,061 | **2,989** (2,494–3,075) |
| `verify-demo` | 10,313 | 10,217 (6,589–10,513) | 17,115 | 18,171 (10,766–23,269) |
| `web-smoke` | 3,693 | 3,657 (3,074–3,844) | 5,231 | 5,218 (3,306–5,468) |
| `player-package-gate` | 1,101 | 1,095 (874–1,114) | 1,762 | 1,770 (1,195–1,941) |

**New budgets** (`tooling/metrics/verify_step_budget.json`, `platforms.linux` / `platforms.windows`):

- **The rule.**
  - The budget is the median of the 6 CI samples.
  - The allowance stays the existing 25% (ratio 1.25). It is widened only where a step's observed spread
    (slowest ÷ median) plus 10 points exceeds that, rounded up to 0.05.
  - The threshold is `max(budget + 50 ms, budget × ratio)`, plus the guard's existing near-miss margins.

| Step | Linux budget / ratio → threshold | Windows budget / ratio → threshold |
|---|---|---|
| `pytest-fast` | 63,237 / 1.25 → 79,046 | 93,708 / **1.30** → 121,820 |
| `exception-policy-scan` | 2,845 / 1.25 → 3,556 | 2,989 / 1.25 → 3,736 |
| `verify-demo` | 10,217 / 1.25 → 13,021 | 18,171 / **1.40** → 25,689 |
| `web-smoke` | 3,657 / 1.25 → 5,171 | 5,218 / 1.25 → 7,122 |
| `player-package-gate` | 1,095 / 1.25 → 2,068 | 1,770 / 1.25 → 2,912 |

- **They still catch regressions.**
  - Fed through the real guard, all 12 "after" samples pass. Both pre-optimisation runs fail: Linux `pytest-fast`
    86.6 s > 79.0 s, Windows 123.4 s > 121.8 s, and `exception-policy-scan` 3.68 s > 3.56 s and 4.06 s > 3.74 s. So
    undoing the de-duplication would be caught on both platforms.
  - Several budgets are now much tighter than June's single values. For example, Linux `verify-demo` went from 21.8 s
    to 10.2 s, and `web-smoke` from 10.1 s to 3.7 s.
- **The mechanism.** `platforms.<name>` overrides the top-level budgets and ratios on that platform only. Other
  platforms, and every other budget (mypy, exception, authoring-trace, the pytest duration guard), are unchanged.
  - The failure message names the platform.
  - The baseline writer that the message suggests now replaces only the current platform's section.
  - Tests cover the override, the fallback and the writer, and the baseline schema test covers the new section.
- **Final runs** (`c877698`), with every step under its threshold:
  - Linux `pytest-fast` 65.4 s and 51.5 s;
  - Windows `pytest-fast` 75.5 s and 65.6 s.

**Historical data, kept:**

- The June budget (`c25c2b2`, 2026-06-11): `pytest-fast` 43,203 ms, `exception-policy-scan` 2,268 ms, `verify-demo`
  21,789 ms, `web-smoke` 10,071 ms, `player-package-gate` 2,512 ms. These stay as the top-level fallback.
- Then, the fast tier had about 2,510 tests in 351 files. It has 4,066 tests in 505 files at `c877698`.
- Fast tier on the owner's PC: 129 s before this work, 99 s after.

## GPU lifetime (Phase 3)

`tooling/gpu_lifetime_probe.py` builds three throwaway projects in a temp folder, in hidden windows. For each, it
runs 4 Studio reloads and 4 Edit → Play → Stop cycles, and counts live GL objects (created minus freed, after
arcade's `ctx.gc()`). It counts once with Python's cycle collector off, which shows what explicit ownership frees,
and once after `gc.collect()`.

| Room | Before: growth, cycle GC off | Before: after `gc.collect()` | After the fix: cycle GC off | After the fix: after `gc.collect()` |
|---|---|---|---|---|
| 2D, no lights | tex/fb/prog +1, buffers +61 | +1, buffers +61 | +1, buffers +56 | +1, buffers +56 |
| 2D, two lights | **tex/fb/prog +49**, buffers +133 | +1, buffers +61 | **+1**, buffers +56 | +1, buffers +56 |
| HD-2D, lit | **tex/fb/prog +49**, buffers +73 | +1, buffers +1 | **+1**, buffers +1 | +1, buffers +1 |

- **The +1** is a one-time object created on the first Play, the same in every room.
- **The light-layer defect.** `LightManager` made a new arcade `LightLayer` on every room load and dropped the old
  one. Each `Light` keeps `_light_layer` pointing back at its layer, so the old layer, with its 2 framebuffers,
  textures, 2 programs and buffers, was freed only when Python's cycle collector happened to run. That is a few
  full-screen textures per room change.
- **The fix.** `engine.lighting._release_light_layer` runs when a layer is replaced. It breaks the cycle and deletes
  exactly the GL objects that layer created itself: its framebuffers, their attachments, its instance buffer and its
  two programs. Nothing it deletes is shared, and nothing is still drawing with it: the layer is replaced during a
  room load, not mid-frame.
- **The test.** `tests/test_lighting_layer_release_gpu.py` reloads a lit room 5 times with the cycle collector off
  and requires flat counts. With the fix disabled, it fails with (5, 3, 18) → (25, 23, 38).
- **The remaining 2D buffer growth** (+5 per 2D room load, never freed) is a separate leak, tracked in **#356**. Its
  holder wasn't found within this checkpoint's time box.
- **Window shutdown** closes the GL context, so everything is gone. The HD-2D renderer releases explicitly before
  that (Stage 2).

## Editor performance (Phase 4)

**Where the time goes** (cProfile, Mesh Studio on the lit HD-2D crossing, hidden 1280×720):

| Action | Cost (profiled) | Of which |
|---|---|---|
| Studio frame | ~10 ms | arcade lays out every widget every frame: ~4.4 ms, in 2D too; 3D canvas: ~2.3 ms; UI draw |
| Selecting a structure | ~150 ms | Studio's full UI rebuild (inspector and panels; pyglet text layout dominates). The 3D pick is 0.5 ms. |
| Committing an edit | ~290–440 ms | UI rebuild 54%; room reload 44%. Within the reload: Animator sprite sheets decoded and sliced every time (~75 ms), tilemap ~58 ms, scene loader ~52 ms, **HD-2D renderer ~40 ms** (GLB read, batching, lighting) |

**One change, measured.** Sprite-sheet frames are now cached per (sheet, frame size, frames) and cleared with the
texture cache, which is what hot reload clears. Timings are medians of 8, unprofiled, two runs each:

| | Before | After |
|---|---|---|
| Room reload | 139–146 ms | **96–97 ms** |
| Edit commit (button → op → reload → rebuild → draw) | 411–445 ms | **365–380 ms** |
| Structure selection | 159–166 ms | 146–147 ms |
| Studio frame | 9.5–9.8 ms | 9.1–9.6 ms |

**Checks after the change:**

- Undo/redo, saves and AI authoring are unchanged: the same ops and the same reload path; the Studio and HD-2D GPU
  suites pass.
- In repeated selections and edits (120 selections, 20 edit/undo cycles), GL objects are flat and the renderer
  matches the document.

**Not done.** Making selection cheaper means rebuilding only the inspector, not the whole UI. That is a real but
non-trivial change, and the evidence (about 150 ms, interactive) doesn't yet justify it. Partial room reloads were
also left alone: at ~40 ms, HD-2D is not the bottleneck.

## Packaging and provenance (Phase 5)

**#345** (draft, targets `main`, head `add7d28`):

- It merges **without conflicts** into current `redesign/visual-editor` (checked with `git merge-tree`).
- Its approach is sound: an explicit allow-list installed under `share/mesh-engine`, with one lookup for it. It
  correctly leaves out the three unconfirmed sprites, which follows the recorded owner decision.

It predates redesign's content, so it is now incomplete:

| Gap | Effect in a pip install | Recommendation |
|---|---|---|
| The starter art every new project copies (`starter_hero`, `starter_villager`, `starter_sign`, `door`, the starter tileset) isn't in the allow-list | New projects have no characters, tiles or doors | Add them. They're Mesh's own: generated by `tooling/make_starter_art.py` and `tooling/make_starter_tileset.py`. `door.png` was made with the Studio commit `156068c`, with no generator script; adding a generator or a provenance note is advisable. |
| Mesh Studio's branding and icons resolve from `engine/../assets/` | A pip-installed Studio has no logo or icons | Bundle `assets/branding` (© MeshMind Studios; the owner's to ship, NOTICE kept) and `assets/icons` (Lucide, ISC; `lucide/LICENSE` kept), and look them up through `bundled_file()` |
| `animated_player.png` is still in `_STARTER_FILES`, copied into **every** new project. `sproutling` and `shelltide` are copied by the monster template. | An unconfirmed sprite lands in every new source-checkout project | **The recorded decision (replace them with original, generated art) isn't done yet.** Generate replacements in the `make_starter_art.py` style, and switch the scaffold to them. Don't replace the owner's art automatically; this is the owner's call. |
| User-facing commands import `tooling/` (#357) | `mesh export` and the web-demo export fail | Move those modules into the package |

**Other assets audited:**

- **HD-2D technical assets** (`tooling/hd2d_assets/stone_crossing.glb`, `tooling/hd2d_lab/assets/*`): generated by
  Mesh's own scripts (`build_crossing.py`, `blender_build.py`, `textures.py`), so they're original. They're demo and
  test only and don't need packaging.
- **The older sprites from the initial import** (`goblin`, `guard`, `merchant`, `quest_giver`, `boss_*`): origin not
  recorded. They're used only by the golden-slice demo packs, not by new projects or the wheel. Record their
  provenance before anything ships them.

**Safest integration plan:**

1. Retarget #345 to `redesign/visual-editor`.
2. Extend its allow-list with the starter art, branding (with NOTICE) and icons (with LICENSE).
3. Switch Studio's branding and icon lookups to `bundled_file()`.
4. Separately, and only with the owner's go-ahead, generate original replacements for the three unconfirmed sprites
   and point the scaffold at them.
5. Fix #357.
6. Then run #345's clean-venv wheel test. It already checks that a pip-installed project matches a source-checkout
   one.

## Issues

| Status | Items |
|---|---|
| Resolved here | #351, the #352 failure set (all 26), the light-layer lifetime, test isolation (`user_settings.json`, the fixtures PNG), the Linux type gate, sprite-sheet re-slicing |
| Fixed in | [#358](https://github.com/septimus82/Mesh/pull/358) (draft): all of the above, plus Windows CI OpenGL (pinned, verified Mesa), `fail-fast`, the fast-tier de-duplication, per-platform step budgets, and the #360 baseline-diff and report-ordering fixes |
| Remaining, tracked | **#356** (2D GL buffer leak), **#357** (pip install and `tooling/`), **#345** gaps (above), the three unconfirmed sprites (to be replaced with original, redistributable art), **#359** (release replay goldens: not re-recorded; each digest change must be checked against intended gameplay), GPU tests not in CI (recommendation) |

## Risks and next actions

**Risks:**

- **CI was blind for a long time.** That is fixed: every step of the normal CI job has now run and passed on both
  OSes. The release-only `ship` job is still red (#359). Window tests on Windows CI use Mesa's software renderer, which
  is closer to Linux CI than to a player's GPU driver.
- **Total time no longer fails CI on its own.** A slowdown has to show up in one of the 5 budgeted steps, or in a
  functional gate, to fail. The total stays visible in every diff and PR comment.
- **Step budgets are tighter than before.** Windows `pytest-fast` and `verify-demo` have only 10–11% headroom over
  the slowest run seen in 6 samples. If runner variance grows, the remedy is more samples and a recomputed allowance
  using the same rule, not a blanket increase.
- **The Mesa pin needs a deliberate update.** A new version means a new digest, read from GitHub's release record.
- **#356** grows slowly in long Studio sessions with 2D rooms.
- **Packaging** isn't usable for creators until the #345 gaps and #357 are closed.

**Next actions:**

1. Owner review of #358, then merge it and close #360 by hand.
2. Release only: go through the 13 replay goldens (#359), case by case.
3. Replace the three unverified sprites with original, redistributable art.
4. Update #345 per the plan above.
5. #356 and #357.
6. Then Stage 5B.
