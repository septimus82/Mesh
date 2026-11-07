# Retiring `.github/workflows/build.yml` (issue #368)

**Proposal:** delete `build.yml`. It has never run a single job. Its useful intentions are listed below, with a
recommended way to restore the gaps that matter, as separate reviewed changes. This change removes nothing that
currently runs, and doesn't weaken CI: `ci.yml` is untouched.

## Why it never ran

`build.yml` has been invalid YAML since it was added in the initial import (`5600701`, 2026-01-24). Since then, every
push to any branch has created a failed run with no jobs: **828 runs** by 2026-10-25, all marked "This run likely
failed because of a workflow file issue". GitHub registers it under its file path because it has never read its
`name:`.

Checked with a YAML parser; the five other workflows parse:

1. **Line 209:** unquoted step names containing `": "`, such as `- name: Canary: minipack shippable` ("mapping values
   are not allowed here"). It was line 205 in the first version.
2. **Line 273:** the `integrity` job's PowerShell here-string has Python lines at column 0, which end the `run: |`
   block.
3. **Even if it parsed,** its nine `actions/upload-artifact@v3` steps use a version GitHub retired in January 2025, so
   those jobs would fail.

It was also built for an older layout. It only triggered on `main` (Windows, Python 3.11/3.12/3.13), so it never
covered the redesign branch.

## What it was meant to check, and what covers it today

| `build.yml` job: check | Covered today? | Where |
|---|---|---|
| fast-headless: `compileall` | **yes** | `ci.yml` tests and arcade3-canary: `python -m compileall -q engine mesh_cli tooling tests` |
| fast-headless: `pytest -W error --strict-markers -m fast` | **yes** | `ci.yml` tests runs the whole default suite (fast + integration). `pytest.ini`'s `addopts` already has `-W error --strict-markers` |
| integration-gl: `tooling.test_tiers tier1` with enforced budgets | **yes** | `ci.yml` tests: full pytest, then `verify-all` with `MESH_VERIFY_BUDGET_ENFORCE=1`, Linux (Xvfb) and Windows (Mesa) |
| full-suite: `tooling.pytest_full` | **mostly** | `ci.yml` runs every test except `slow` and `e2e` (163 deselected). No workflow runs those (the weekly `weekly_health.yml` runs the default suite too); they run locally |
| check: headless-imports test, `verify-all` | **yes** | `ci.yml` tests (`verify-all --ci-bundle`, artifact validation, baseline diff) |
| check: `verify-demo`, `verify-replays`, `verify-strict` | **yes** | steps of `verify-all` (`mesh_cli/verify_steps`) |
| check: `perf-run` coarse gate (p95 ≤ 5000 ms) | **partly** | `verify-all`'s `perf-baseline-compare` step |
| check: `release-contract` (asset audit) | **no** | not run in CI. It passes today: `mesh release-contract`, exit 0, 174 files |
| check: `content-contract --with-prefabs --with-behaviours` | **no** | not run in CI (verify-all runs the lighter `content-audit`). It passes today: exit 0, 174 files |
| canary: minipack fixture shippable | **yes** | `tests/test_minipack_fixture_is_shippable.py` is in the default suite |
| canary: replay-hash determinism | **yes** | `ci.yml` arcade3-canary: replay-hash, plus an installed-wheel replay smoke |
| integrity: build a wheel, install it in a clean venv, `verify-all` | **partly** | arcade3-canary installs the wheel and runs a replay. The full clean-install check (`tests/test_wheel_bundles_engine_data.py`, slow) and `tooling/hd2d_install_acceptance.py` are local only |
| release (`main` and tags): `mesh dist`, `replay-goldens --strict`, upload | **partly** | `ci.yml`'s `ship (release branches)` job runs `release ship` and the replay suite on release branches; release goldens are issue #359 |
| Python 3.12 and 3.13 | **no in CI** | `ci.yml` is 3.11 only. Development runs 3.13 locally (the whole fast and GPU tiers pass on 3.13.3); 3.12 is untested |

## Recommended restorations (separate, reviewed changes)

None of these is part of this change. Each is small, and none duplicates `ci.yml`:

1. **Newer Pythons, fast tier only.** A Linux job on Python 3.12 and 3.13 running `compileall` and
   `pytest -q -m fast`, without Xvfb and Mesa. That's about 2-3 minutes each; a full matrix would duplicate the slow
   jobs.
2. **The contracts.** Add `mesh release-contract --repo-root . --artifacts artifacts` and
   `mesh content-contract --with-prefabs --with-behaviours` as steps in `ci.yml`'s Linux tests job, after
   `verify-all`. Both pass today and take seconds.
3. **The clean-install check.** Run `tests/test_wheel_bundles_engine_data.py` (about 50 s; builds and installs the
   wheel) on Linux in `ci.yml`, or in `weekly_health.yml` if PR time matters (it would be the first slow test any workflow runs). The full launcher and GPU acceptance
   (`tooling/hd2d_install_acceptance.py`) stays a manual pre-release check: it downloads dependencies and drives
   windows.
4. **Not restored:**
   - the coarse perf gate (`perf-baseline-compare` covers it);
   - the `release` job (`ship` covers release branches; goldens are #359);
   - the Windows 3 × 6-job matrix (it would triple CI time for checks `ci.yml` already runs).

## After merging

- The failed `.github/workflows/build.yml` runs stop.
- The existing 828 runs can be left as they are; they cost nothing. They can also be deleted from the Actions page,
  but that is irreversible, so it's the owner's choice.
