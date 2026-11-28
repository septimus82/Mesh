# CI Workflow

## What Runs

The GitHub Actions workflow at `.github/workflows/ci.yml` runs on every push and pull request with this matrix:

- `ubuntu-latest`, Python `3.11`
- `windows-latest`, Python `3.11`

Each matrix run executes:

1. `python -m compileall -q engine mesh_cli tooling tests`
2. `python -m pytest -q` (Windows uses `-p no:cacheprovider`; Linux runs it as two shards and Windows as three, whose records each OS's fan-in checks the same way and holds to the suite's floor: see below)
3. `python -m mesh_cli verify-all --artifacts artifacts --ci-bundle --release-notes-artifact --reuse-evidence` (step budgets enforced)
4. `python -m mesh_cli release bundle --out artifacts/release_bundle.zip --seed 123 --reuse-verify-all artifacts`: its release check reuses step 3's verify-all only when that run's evidence proves it passed on this exact clean commit with unchanged reports, and otherwise runs verify-all itself (F13-B, `docs/release_bundle.md`)
5. `python -m mesh_cli bundle verify --zip artifacts/release_bundle.zip --strict`

The workflow uploads artifacts per OS/Python run:

- `artifacts/release_bundle.zip`
- `artifacts/bundle_verify_report.json`
- `artifacts/verify_all/**`

Artifact names follow this pattern:

- `mesh_release_bundle_<os>_py<python>`

Retention is 7 days.

## Test Shards (F13-C; Linux since S1 5.9; Windows in three since its follow-up)

Each OS's full default suite (`not slow and not e2e`) runs as shard jobs, `pytest (<os>, py3.11, shard K/N)`: Linux's
as two (`1/2`, `2/2`, plan `default`; since S1 5.9, when its single job had become CI's critical path) and Windows' as
three (`1/3` to `3/3`, plan `default-windows`; since S1 5.9's follow-up, when its two shards had become CI's slowest
jobs). Each OS's plan has its own pins and count (`tooling/ci_shards.py` `PLANS`, `PLAN_SHARDS`), and each OS is checked
the same way by its own `tests` fan-in, with that plan and count.

- **Whole modules.** A shard runs whole test modules, so a module's fixtures and test order are as in a full run.
  `tooling/ci_shards.py` decides which: the heaviest modules (the plan's pins, by measured duration) are pinned to
  balance the shards; every other module, present or new, goes to `sha256(path) % N + 1`, fixed whatever else changes.
- **Separate processes.** Each shard is its own job (its own runner, checkout and Python): no `pytest-xdist`, nothing
  shared between them.
- **Evidence.** Each shard collects the whole suite and keeps its own modules (`-p tooling.ci_shards_plugin
  --mesh-shard K/N`, with `--mesh-shard-plan default-windows` on Windows), and writes a record (`artifacts/shards/shard-K.json`): the commit, the collected test ids and
  their digest, the scheme's digest, the selected ids, every test's outcome and seconds, its subtests' outcome counts, the modules skipped at
  collection and pytest's exit status, with `complete: true` only once the session finished. Its JUnit report sits
  beside it. Both go up as `pytest-shard-K-<os>-py3.11`, whatever the job's result.
- **The fan-in.** `tests (<os>, py3.11)` requires every one of its OS's shard jobs (`tooling/ci_require_jobs.py`),
  downloads their records and runs `python3 tooling/ci_shards.py check shard-records --plan <plan> --shards <N>
  --min-selected <floor> --commit <sha>`. It refuses a missing,
  duplicate, incomplete or failed shard; a record of another commit, collection, shard count or scheme, or one whose
  ids don't match its own digest; a test selected twice, run in both shards, run in neither or without an outcome; a
  test that didn't pass; and a JUnit report that is missing or disagrees with its record. Test ids that embed the
  checkout's path are written `<repo>`; a module skipped at collection is reported by both shards and counted once.
- **The suite's MCP test (#649).** Both Linux shards install `.[mcp]` and set `MESH_REQUIRE_MCP=1`, so the real
  FastMCP server build fails, never skips, in whichever shard holds it.
- **Lane floors (#648).** Both OSes' checks pass `--min-selected` with the default suite's floor
  (`tooling/ci_shards.py` `DEFAULT_MIN_SELECTED`), and refuse a suite that collects fewer tests: a conftest, marker or
  collection change that drops most of the suite turns CI red instead of green. Extended's gpu fan-ins do the same
  with the gpu lane's floor, and every lane run by `tooling/test_tiers.py` checks its own `min_selected`. Each floor sits
  just under what its lane collects; `tests/test_test_lanes_contract.py` keeps it within 5% of that (a whole-suite run
  counts every lane). **The rule:** a legitimate test removal lowers the floor on purpose, in the same PR; growth past
  5% raises it there too. The lane-floor test needs the whole suite's collection; every shard collects the whole suite
before keeping its own modules, so it runs in its shard on each OS, and under `CI=true` it fails rather than skips if
the collection was ever narrowed.

Run one Windows shard locally the way CI does (the check needs all three records to pass):

```powershell
python -m pytest -q -p no:cacheprovider -p tooling.ci_shards_plugin --mesh-shard 1/3 --mesh-shard-plan default-windows --mesh-shard-record artifacts/shards/shard-1.json --junitxml=artifacts/shards/junit-1.xml
python tooling/ci_shards.py check artifacts/shards --plan default-windows --shards 3
```

## Replay Suite (every PR and push)

The golden replay suite (~8 s) runs as the `replays (ubuntu-latest, py3.11)` job on every pull request and push, and is
required: both `tests (<os>, py3.11)` fan-ins list it (`needs:` and `tooling/ci_require_jobs.py`), so a mismatch, or a
replays job that is missing, skipped or cancelled, turns the required checks red. One OS is enough: digests are
platform-independent; only the time budgets are Linux-only. The job only compares and uploads `replay-suite-*`
(`artifacts/replay_suite/**`); it never updates goldens. A failure is a regression, or an intentional change that needs a
reviewed refresh: `python -m mesh_cli replays update-golden --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --reason "..."`
(see `docs/replay_suite.md`), committed in the PR. The ship job below still runs it too.

## Baseline Growth (every PR and push)

Each ratchet lets through what its committed baseline lists, so a change could add to the baseline and pass in the same
pull request (#624). The `baseline-growth (ubuntu-latest, py3.11)` job, required through both `tests` fan-ins like the
replays job, runs `python -m tooling.baseline_growth --base <base>`: it compares each baseline in
`tooling/baseline_growth.py` (`BASELINES`: the ruff and mypy baselines, `exception_policy_baseline.json`, the exception
budget count, the unmarked-test, never-runs, quarantine and fast-marking lists, the public API export list, the tech-debt marker
cap in `tests/test_todo_audit_ratchet_contract.py` (its last assignment), and the timing and perf budgets
`verify_step_budget.json`, `authoring_trace_budget.json` and `perf_baselines/baselines.json`) with the same file at
`git merge-base HEAD <base>`. The base is the pull request's base branch, or on a push what the branch held before it.

Any growth (a new entry, any number in a JSON baseline going up or removed, a new key under `report_only_ceiling_ratios` in `verify_step_budget.json`, which makes a hard ceiling report-only, a deleted file) fails, unless a commit between the merge base
and `HEAD` has a line, at the start of a line in its message:

```text
baseline-growth: tooling/ruff_baseline.txt: ruff 0.16 reports UP038 on code that predates it
```

naming the file exactly as listed and a reason. It goes in a commit message, not the pull request body: it is reviewed
with the change, can't be edited after CI has run, and works the same locally and on push runs. Shrinking always passes.
Run it locally with `python -m tooling.baseline_growth --base origin/redesign/visual-editor` (uncommitted growth fails
until it is committed with its line). verify-all's `mypy-baseline-guard` runs the same check on the mypy baseline when
`MESH_BASELINE_BASE` names the base; CI's verify jobs are shallow clones, so there it is an allow-listed skip and this
job is the check. Entries for tests that no longer exist fail `tests/test_tier_marker_ratchet.py`.

## Flake Quarantine (D10)

A flaky test is never loosened, skipped or retried automatically: no `pytest-rerunfailures`, no retry loops
(`tests/test_flake_quarantine_contract.py` fails on them). Re-running a failed attempt is a person's decision, recorded
in the PR or issue. The required lanes keep `-W error`. What a flaky test may get is a dated, issue-linked quarantine
with an expiry, in `tests/baselines/quarantine.txt`, one test per line:

```text
tests/test_example.py::test_races 649 2026-11-26 2026-12-26
```

That's the node id, the issue number, the date it was added and the expiry date (`YYYY-MM-DD`).

- **Effect.** `tests/conftest.py` deselects a listed test from every run: CI's pytest jobs, the fast tier and
  verify-all, and every `tooling/test_tiers.py` lane. Only `pytest --mesh-quarantined` runs it, and that runs nothing
  else (`python -m tooling.test_tiers quarantine`). Extended's `quarantine (<os>, py3.11, report-only)` job runs it on
  both OSes after every merge, nightly and on dispatch. It lists each entry and the outcome in its job summary, and
  raises a warning annotation for each failure. It passes whatever the tests do: it reports, it doesn't gate.
- **Floors.** Each lane's floor counts only the tests the lane runs, not quarantined ones. `ci_shards.py check
  --min-selected` and `test_tiers` `min_selected` see the suite after the quarantine is deselected, and so does
  `test_every_lane_floor_is_within_5_percent_of_what_the_lane_collects`. So a quarantine that takes a lane under its
  floor fails the PR that adds it. Never lower a floor to make room for a quarantine; fix the test instead.
- **The contract** (`tests/test_flake_quarantine_contract.py`, fast tier) fails on an entry with no issue number, a
  malformed date, an `added` date in the future, an expiry in the past (UTC), an expiry more than 30 days after
  `added`, or a node id whose test doesn't exist. It can't check offline that the issue is still open: the reviewer
  does.

**To quarantine** (when the same test fails a second time within 30 days, on attempt 1, for reasons unrelated to the
change):
1. Open an issue with the evidence: the run ids and a log excerpt.
2. Add the line, with today's date as `added` and an expiry no more than 30 days later.
3. Commit it with a `baseline-growth: tests/baselines/quarantine.txt: <reason, issue>` line. A new or changed entry is
   baseline growth.

**To unquarantine:** fix the cause and delete the line in the same PR. The test is back in its required lane, and
removing an entry is never growth. An entry that expires before the fix makes the contract test fail CI for everyone.
Then fix the test, or renew the entry: a new `added` date and expiry, with fresh evidence on the issue and a
`baseline-growth:` line.

## Release Branch Ship Job

On `release/**` branches (or `workflow_dispatch`), CI also runs:

1. `python -m mesh_cli release ship --out-dir artifacts/ship --seed 123 --quiet`
2. `python -m mesh_cli replays run --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --budgets-only-on linux --quiet`
3. `python -m mesh_cli bundle verify --zip artifacts/ship/release_final.zip --strict`

Ship artifacts are uploaded from:

- `artifacts/ship/**`
- `artifacts/replay_suite/**`

## Determinism and Headless Safety

CI sets deterministic runtime variables:

- `MESH_CI_SEED=123`
- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`

Headless safety is handled per OS:

- Linux installs `xvfb` and runs `pytest`, `verify-all`, and `release bundle` under `xvfb-run -a`.
- Windows runs the same commands directly without requiring an Arcade window/GPU.

## Reproduce Locally

Run from repository root:

```powershell
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m compileall -q engine mesh_cli tooling tests
python -m pytest -q -p no:cacheprovider
python -m mesh_cli verify-all --artifacts artifacts/verify_all
python -m mesh_cli release bundle --out artifacts/release_bundle.zip --seed 123
python -m mesh_cli bundle verify --zip artifacts/release_bundle.zip --strict
```

On Linux, prefix the `pytest`, `verify-all`, and `release bundle` commands with `xvfb-run -a` to mirror CI headless execution.

Optional: write the JSON verify report like CI:

```powershell
python -m mesh_cli bundle verify --zip artifacts/release_bundle.zip --strict --json > artifacts/bundle_verify_report.json
```
