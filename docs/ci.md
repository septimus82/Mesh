# CI Workflow

## What Runs

The GitHub Actions workflow at `.github/workflows/ci.yml` runs on every push and pull request with this matrix:

- `ubuntu-latest`, Python `3.11`
- `windows-latest`, Python `3.11`

Each matrix run executes:

1. `python -m compileall -q engine mesh_cli tooling tests`
2. `python -m pytest -q` (Windows uses `-p no:cacheprovider`)
3. `python -m mesh_cli verify-all --artifacts artifacts/verify_all`
4. `python -m mesh_cli release bundle --out artifacts/release_bundle.zip --seed 123`
5. `python -m mesh_cli bundle verify --zip artifacts/release_bundle.zip --strict`

The workflow uploads artifacts per OS/Python run:

- `artifacts/release_bundle.zip`
- `artifacts/bundle_verify_report.json`
- `artifacts/verify_all/**`

Artifact names follow this pattern:

- `mesh_release_bundle_<os>_py<python>`

Retention is 7 days.

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
