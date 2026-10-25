# Post-M16 Stage 5A: repository health checkpoint

**Verdict: CONDITIONAL PASS.** Stage 5A is hardened and integrated (#355). The full test suite now passes on Linux
and Windows CI for the first time. All 32 `verify-all` steps pass on both. The fixes are in draft PR
[#358](https://github.com/septimus82/Mesh/pull/358). The conditions are:

1. The owner's OK for the Windows CI Mesa action.
2. A decision on the out-of-date step-time budget, the one check still red (finding 15).
3. #356 and #357 stay open, along with the packaging gaps and the three unconfirmed sprites.

None of these blocks Stage 5B technically. Stage 5B should start only after the owner's review.

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
| 15 | Medium | **`verify-all`'s step-time budget is out of date and has never been enforced.** The fast tier takes 87–129 s against a 43 s budget set in June, when it had 62% fewer tests. Now that CI reaches `verify-all`, this is the last red check on both OSes. | CI run `40187015582`; local timing; test counts at `c25c2b2` and now | **Open: owner decision** (see CI results) |
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

PR [#358](https://github.com/septimus82/Mesh/pull/358), commit `09f3841`, CI run `40187015582`. The PR's own run
(`40187033537`) gave the same result.

| Check | Linux (ubuntu-latest, py3.11) | Windows (windows-latest, py3.11) |
|---|---|---|
| `arcade3-canary` (required) | **pass** | — |
| `web-smoke` (required) | **pass** | — |
| Full pytest suite | **pass**: 9,579 passed, 0 failed, 87 skipped, 53 subtests (4 min 24 s) | **pass**: 9,579 passed, 0 failed, 87 skipped, 53 subtests (6 min 34 s) |
| `verify-all`: all 32 steps (type gate, mypy baseline and island, ruff, exception budget, swallow scan, exception policy, fast tier, runtime and player-package smokes, web smoke, perf compare, content audits, doctor-assets, …) | **pass** | **pass** |
| `verify-all`: step-time budget (`MESH_VERIFY_BUDGET_ENFORCE=1`, CI only) | **fail** | **fail** |

- **Before this checkpoint:**
  - Linux: 26 failures, and `verify-all` never ran.
  - Windows: always cancelled. When it did run, it had 13 OpenGL failures (no GL driver on the runner) and 0 other
    failures.
- **How Windows was fixed.** The runner had only Microsoft's OpenGL 1.1. It now installs Mesa's software OpenGL, the
  Windows counterpart of Linux's Xvfb + Mesa, so those 13 window tests really run and pass. Nothing was skipped.
  This adds a third-party action, `ssciwr/setup-mesa-dist-win@v2`, which **needs the owner's OK** (see the PR).
- **`fail-fast` is now off**, so a failure on one OS no longer hides the other's result.

**What remains red, and why: the step-time budget (finding 15).**

- **The numbers.** `pytest-fast` has a 43.2 s budget (threshold 54 s). It took 87 s on Linux CI, 123 s on Windows
  CI and 129 s on the owner's PC. `exception-policy-scan`: 2.3 s budget, 3.7 s and 4.1 s.
- **Why the budget is out of date:**
  - It was written on 2026-06-11 (`c25c2b2`), when the fast tier had about 2,510 tests in 351 files. It now has 4,066
    tests in 505 files.
  - The policy scan has grown with the code it scans.
  - The budget was never enforced: CI stopped at pytest before `verify-all` could run, and the check is off outside
    CI.
- **Not a single regression.** No one test explains it. The slowest 25 take about 52 s together: four repository
  scans for the exception policy (about 15 s), and about 15 Creator-mode "doesn't import X" checks, each in its own
  subprocess (about 1.15 s each).
- **Deliberately not re-baselined.** Lowering the bar on a ratchet is the owner's call.
- **Options, which can be combined:**
  - (a) Speed up the fast tier. Share one scan across the policy-scan tests; check all the Creator-mode import
    boundaries in one subprocess. Together that saves about 30 s.
  - (b) An explicit, reviewed re-baseline, with budgets measured on CI runners. One budget can't fit machines that
    take 87, 123 and 129 s for the same tests.

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
| Fixed in | [#358](https://github.com/septimus82/Mesh/pull/358) (draft): all of the above, plus Windows CI OpenGL and `fail-fast` |
| Remaining, tracked | **#356** (2D GL buffer leak), **#357** (pip install and `tooling/`), **#345** gaps (above), the three unconfirmed sprites (owner decision pending), the step-time budget (finding 15, owner decision), GPU tests not in CI (recommendation) |

## Risks and next actions

**Risks:**

- **CI was blind for a long time.** That is now fixed: every gate has run on both OSes. Window tests on Windows CI
  use Mesa's software OpenGL, which is closer to Linux CI than to a player's GPU driver.
- **#356** grows slowly in long Studio sessions with 2D rooms.
- **Packaging** isn't usable for creators until the #345 gaps and #357 are closed.

**Next actions:**

1. Merge #358 once reviewed, including the owner's OK for the Mesa action.
2. Owner decisions: the step-time budget (speed-up, re-baseline, or both) and the three sprites.
3. Update #345 per the plan above.
4. #356 and #357.
5. Then Stage 5B.
