# CI Workflow

## What Runs

The GitHub Actions workflow at `.github/workflows/ci.yml` runs on every push and pull request with this matrix:

- `ubuntu-latest`, Python `3.11`
- `windows-latest`, Python `3.11`

Each matrix run executes:

1. `python -m compileall -q engine mesh_cli tooling tests`
2. `python -m pytest -q` (Windows uses `-p no:cacheprovider`, and runs it as two shards: see below)
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

## Windows Test Shards (F13-C)

Windows' full default suite (`not slow and not e2e`) was the longest job of every run, so it runs as two jobs,
`pytest (windows-latest, py3.11, shard 1/2)` and `shard 2/2`. Linux runs the whole suite in one job, as before.

- **Whole modules.** A shard runs whole test modules, so a module's fixtures and test order are as in a full run.
  `tooling/ci_shards.py` decides which: the heaviest modules (`PINNED`, by measured duration) are pinned to balance the
  two; every other module, present or new, goes to `sha256(path) % 2 + 1`, fixed whatever else changes.
- **Separate processes.** Each shard is its own job (its own runner, checkout and Python): no `pytest-xdist`, nothing
  shared between them.
- **Evidence.** Each shard collects the whole suite and keeps its own modules (`-p tooling.ci_shards_plugin
  --mesh-shard K/2`), and writes a record (`artifacts/shards/shard-K.json`): the commit, the collected test ids and
  their digest, the scheme's digest, the selected ids, every test's outcome and seconds, its subtests' outcome counts, the modules skipped at
  collection and pytest's exit status, with `complete: true` only once the session finished. Its JUnit report sits
  beside it. Both go up as `pytest-shard-K-windows-latest-py3.11`, whatever the job's result.
- **The fan-in.** `tests (windows-latest, py3.11)` requires both shard jobs (`tooling/ci_require_jobs.py`), downloads
  their records and runs `python3 tooling/ci_shards.py check shard-records --commit <sha>`. It refuses a missing,
  duplicate, incomplete or failed shard; a record of another commit, collection, shard count or scheme, or one whose
  ids don't match its own digest; a test selected twice, run in both shards, run in neither or without an outcome; a
  test that didn't pass; and a JUnit report that is missing or disagrees with its record. Test ids that embed the
  checkout's path are written `<repo>`; a module skipped at collection is reported by both shards and counted once.

Run one shard locally the way CI does:

```powershell
python -m pytest -q -p no:cacheprovider -p tooling.ci_shards_plugin --mesh-shard 1/2 --mesh-shard-record artifacts/shards/shard-1.json --junitxml=artifacts/shards/junit-1.xml
python tooling/ci_shards.py check artifacts/shards
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
budget count, the unmarked-test, never-runs and fast-marking lists, the public API export list, the tech-debt marker
cap in `tests/test_todo_audit_ratchet_contract.py` (its last assignment), and the timing and perf budgets
`verify_step_budget.json`, `authoring_trace_budget.json` and `perf_baselines/baselines.json`) with the same file at
`git merge-base HEAD <base>`. The base is the pull request's base branch, or on a push what the branch held before it.

Any growth (a new entry, any number in a JSON baseline going up or removed, a deleted file) fails, unless a commit between the merge base
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
