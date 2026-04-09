# Release Checklist (Runtime-only Engine Ship)

Use this checklist to cut a "player build" release artifact. This does not require the editor.

## Pre-flight

- [ ] Working tree clean (no uncommitted changes)
- [ ] On the intended ref/branch/tag

## Gates (must pass)

- [ ] Run compileall:
  ```bash
  python -m compileall -q engine mesh_cli tooling tests
  ```
- [ ] Run full test suite:
  ```bash
  python -m pytest -q -W error
  ```
- [ ] Run verify-all CI bundle:
  ```bash
  python -m mesh_cli verify-all --artifacts artifacts --ci-bundle
  ```
- [ ] Confirm in output:
  - `ok=true`
  - `player-package-gate: ok`
  - `runtime-player-smoke: ok` (or equivalent runtime smoke step)
  - `web-smoke: ok`
  - `perf-baseline-compare: ok`

## Build the distributable package

- [ ] Build package:
  ```bash
  python -m mesh_cli package-player --out artifacts/player_pkg
  ```
- [ ] Run packaged smoke:
  ```bash
  python -m mesh_cli package-player --out artifacts/player_pkg --smoke
  ```

## Artifact verification (must exist)

Player package:

- [ ] `artifacts/player_pkg/manifest.json`
- [ ] `artifacts/player_pkg/package_check.json` (forbidden hits empty)
- [ ] `artifacts/player_pkg/runtime_smoke.json` (`ok=true`, no forbidden imports)

Web smoke:

- [ ] `artifacts/web_smoke.json` (`ok=true`)

Perf:

- [ ] `artifacts/perf_run.json`
- [ ] `artifacts/perf_compare.json` (no regressions)

Optional but useful:

- [ ] `artifacts/verify_step_budget_check.json` (`pytest-fast` budget)
- [ ] `artifacts/verify_step_durations.json`

## Release bundle preparation

- [ ] Copy `artifacts/player_pkg/` to your release staging location
- [ ] Include a small `RELEASE_NOTES` snippet:
  - commit hash
  - date
  - key gates passed (player package, runtime smoke, web smoke, perf compare)

## Post-release sanity

- [ ] On a clean environment (optional), run:
  ```bash
  python -m mesh_cli play-runtime --headless-smoke --smoke-artifact artifacts/post_release_smoke.json
  ```
- [ ] Confirm `ok=true`.

## Contract anchors (exact lines)

```text
python -m compileall -q engine mesh_cli tooling tests
python -m pytest -q -W error
python -m mesh_cli verify-all --artifacts artifacts --ci-bundle
python -m mesh_cli package-player --out artifacts/player_pkg --smoke
```
