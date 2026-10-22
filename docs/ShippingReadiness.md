# Shipping Readiness (Versioned)

**Doc version:** SR-1  
**Applies to:** Mesh Engine runtime-only + player package shipping pipeline  
**Last updated:** 2026-06-03

This document defines the minimum gates and artifacts required to consider the engine "shippable" as a **runtime-only player build**, without editor dependencies.

## Definition of "shippable"

A build is considered shippable when all required gates pass and the expected deterministic artifacts are produced, with **no forbidden editor imports** in runtime-only paths and **no editor code included** in the player package.

## Required gates (must pass)

### 1) Full verification bundle

Run:

```bash
python -m mesh_cli verify-all --artifacts artifacts --ci-bundle
```

Must complete with `ok=true`.
The verify summary must include the shipping gates:

- `runtime-player-smoke`
- `player-package-gate`
- `web-smoke`
- `perf-baseline-compare`

### 2) Player package gate

The verify pipeline must include and pass:

- `player-package-gate`

This gate must produce:

- `artifacts/player_pkg/manifest.json`
- `artifacts/player_pkg/package_check.json`
- `artifacts/player_pkg/runtime_smoke.json`

And `package_check.json` must report:

- forbidden hits list is empty

### 3) Runtime-only smoke gate

Runtime-only smoke must be runnable and must not import editor modules.

Expected artifact schema includes:

- `ok`
- `scene_loaded`
- `ticks`
- `forbidden_imports_found` (must be empty)
- `diagnostics` (deterministic list)

### 4) Web build + web smoke gate

The verify pipeline must build the web target, run `web-smoke`, and produce:

- `artifacts/web_smoke.json`

This must report:

- `ok=true`
- `outputs_present` reports required outputs
- deterministic `files_sample` ordering

### 5) Perf baseline compare gate

The verify pipeline must include and pass:

- `perf-baseline-compare`

Artifacts:

- `artifacts/perf_run.json`
- `artifacts/perf_compare.json`

Rule:

- counters must not regress beyond allowed tolerance (currently exact, `increase_allowed=0`)

## Required artifacts (expected outputs)

After a successful `verify-all --ci-bundle`, the `artifacts/` directory should include at minimum:

- `artifacts/player_pkg/manifest.json`
- `artifacts/player_pkg/package_check.json`
- `artifacts/player_pkg/runtime_smoke.json`
- `artifacts/runtime_smoke.json` (or similar runtime smoke artifact from pipeline)
- `artifacts/web_smoke.json`
- `artifacts/perf_run.json`
- `artifacts/perf_compare.json`

## Diagnostic expectations

- Any gate failure should emit structured diagnostics.
- Diagnostics ordering must be deterministic and match the engine diagnostics ordering rules.
- The editor "Problems" panel must show the same ordered diagnostics set when running editor workflows.

## Known non-goals

- This document does not define gameplay/content completeness.
- It defines shipping readiness for the engine runtime distribution path.

## Change log

- SR-1: initial definition of shipping readiness and required gates/artifacts.

## Contract anchors (exact lines)

```text
python -m mesh_cli verify-all --artifacts artifacts --ci-bundle
artifacts/player_pkg/manifest.json
artifacts/web_smoke.json
artifacts/perf_compare.json
player-package-gate
perf-baseline-compare
```
