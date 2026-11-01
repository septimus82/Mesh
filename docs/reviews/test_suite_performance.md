# Test-suite performance: findings and tiers (post-M20, Part D)

**Measured** on the owner's PC: Windows, Python 3.13, CPU otherwise idle, at `8613110` unless stated. This PC runs at about 1.7–1.9× a median CI runner (the advisory's speed factor).

**Changes on this branch:** three, with no test removed or weakened. Each one is shown to still fail when the behaviour it guards breaks.

## Where the time goes

| Run | Wall time | Notes |
|---|---|---|
| Fast tier (`-m fast`) | **131 s** (4,819 tests) | at `0fd517a` (2026-10-25 calibration): 120 s (4,559 tests) |
| Fast tier, 4 workers (`pytest-xdist`, scratch venv only) | **71 s** | 4,817 passed, 9 skipped, no failure (the serial run in the same venv: 133 s) |
| Default suite (`not slow and not e2e`) | **388 s** (9,925 tests) | what CI's "Run pytest" runs |
| GPU tier (`test_*_gpu.py`, hidden windows) | **1,133 s** (167 tests) | **→ about 510 s with this branch** |
| CI's whole Windows sequence (pytest → verify-all → release bundle) | about 28 min | release bundle alone 12 min |

**The fast tier's growth since calibration (+10.9 s here, #373's +14–16 % on CI) is new tests, not slower old ones:**

- New milestone test files (terrain, scatter, terrain materials, water, the speed advisory): +6.6 s.
- The export-bundle file (+1.5 s): #389's real export test.
- The legacy-event-bus policy scan (+1.3 s): the repository it walks grew.
- No existing test got slower.

**The default suite's 284 s of listed test time, by what the tests spend it on:**

| Kind | Tests | Seconds | Biggest |
|---|---|---|---|
| Subprocess CLI runs (a fresh interpreter each: ~2–2.5 s before any work) | 37 | 100.7 | `--help` checks 27 s; `perf run` thresholds 12 s; `doctor-assets` 12 s |
| Packaging, export and release builds | 48 | 54.7 | release-bundle CLI 18 s, self-verify 13 s |
| Repository scans (policy and contract tests that walk the tree) | 26 | 41.6 | logging policy 7 s, legacy event bus 7 s, docs freshness 6 s |
| Disposable projects | 30 | 18.8 | |
| Other | 95 | 68.5 | |

- Setup and teardown are small in the default suite: 5 s in total. One fixture is already shared: `exception_policy_scan`, a session scan.
- The GPU tier's setups are large:
  - the Blender-asset import: 55 s;
  - opening the HD-2D starter in Studio: 40 s;
  - the HD-2D Studio room: 28 s.

## Changes on this branch (before → after, and the mutation each still catches)

| Change | Before | After | Mutation | Caught by |
|---|---|---|---|---|
| **Walk tests run without filming.** The terrain and scatter walk tests called the studies' evidence path: a frame read back every other step, and a 120-frame WebP encoded at `method=6`. No assertion reads them. `walking()`/`walks()` take `film=False`; the studies still film by default. | 331.7 s + 311.0 s | 7.0 s + 9.2 s | `STEP = 3.0` (cliffs climbable) | both tests: `into_the_cliff` reached |
| **`--help` checks in process** (`test_cli_migration_pass7.py`: 12 interpreter starts). A fresh interpreter's `mesh_cli --help` is still checked in `test_cli_commands_scaffold_guard.py`. | 27.3 s | 1.4 s | `new-npc`'s parser renamed | `test_authoring_commands_help` |
| **One provenance per bundle.** A release bundle ran `get_provenance()` (three git subprocesses) and `git rev-parse HEAD` for every manifest pass, up to 9 times. Now once per manifest build, so the passes agree by construction. A product speed-up, not only a test one. | the 5 release/help files: 92.2 s | 33.0 s | a timestamped provenance fed to the manifest | `test_handle_same_seed_is_byte_deterministic_by_default`, `test_seeded_bundle_is_byte_identical` |

**Totals:**

- The GPU tier goes from about 19 min to about 8.5 min.
- The default suite drops by about 85 s locally: the five files, 59 s, of which the `--help` file's 26 s is in the default run.
- The fast tier is unchanged. The release-bundle tests that sped up are in the default suite, not the fast tier.

## Proposed tiers

| Tier | When | What | Time here | Fails on |
|---|---|---|---|---|
| **Quick** | every edit, every agent iteration | `-m fast`, plus `ruff` on changed files; what `tooling/test_tiers.py tier0` runs | 131 s; **71 s with 4 workers** | logic, contracts, policies |
| **Focused** | before a PR, for the area changed | Quick, plus the changed area's test files and their GPU tests (`MESH_GL_SMOKE=1`, hidden windows): e.g. a terrain change runs `test_terrain*.py`, `test_scatter*.py`, `test_water*.py` | about 3–6 min | the area's behaviour in a real game window |
| **Acceptance** | before a merge, and CI | default suite, plus slow/e2e (163 tests), the GPU tier, the release bundle, the clean-install check; `tooling/runtime_gate.py` only on request (real windows) | about 25 min in CI per OS; GPU tier 8.5 min here | integration seams, packaging, determinism |

## Next steps, measured, not done here

1. **`pytest-xdist` for Quick:** −46 % here, with no failures. It is a new dev dependency, so it needs the owner's decision.
   - Before turning it on in CI, run the default suite under it. Tests that write shared state (#334's class) are the risk.
   - One skip differed between the runs (9 against 10).
2. **Subprocess CLI tests:** 100 s of the default suite.
   - Run argument-only checks in process, as done here.
   - Keep one fresh-interpreter check per entry point.
   - The `*_help_regressions` files are already `slow`; the same change applies.
3. **Release-bundle tests:** each test still builds a bundle (about 1 s). The read-only ones (`TestSelfVerifySuccess`, six tests) can share one class-scoped bundle: about 6 s.
4. **Repository scans:** 26 tests walk the tree separately (42 s). A session-scoped file index, as `exception_policy_scan` already does for one scan, could save about half.
5. **GPU setups:** the Blender import (55 s) and Studio opens (40 s, 28 s) are module fixtures. They could share one opened project per module where tests only read.
6. **CI's in-job duplication** (proposal #400): the fast tier runs three times per job and `verify-all` twice.

```
py -3.13 -m pytest -q -p no:cacheprovider -m fast --durations=0 --durations-min=0.05        # Quick, profiled
MESH_GL_SMOKE=1 py -3.13 -m pytest -q -o addopts= tests/test_*_gpu.py --durations=0       # GPU tier, profiled
```
