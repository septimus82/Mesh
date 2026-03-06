# Debug Diagnostics & Health Tooling

Quick reference for the diagnostics pipeline: **verify-all** artifacts,
**debug-report** / **health-report** CLIs, editor debug overlay, and
baseline update commands.

---

## 1. Overview

| Layer | What it does |
|---|---|
| `verify-all` | Runs the full validation pipeline and writes deterministic JSON artifacts. |
| `debug-report` | Reads artifacts and prints a human-readable diagnostics summary (+ optional JSON). |
| `health-report` | Reads artifacts + baselines and writes `health_report.json` with signal summaries. |
| Editor debug overlay | In-editor panel (debug-gated) showing swallowed exceptions, shadow backend, and verify health snapshot. |

---

## 2. Artifacts emitted by `verify-all`

Run:

```
python -m mesh_cli verify-all --artifacts artifacts
```

Key artifacts written to the `--artifacts` directory:

| Filename | Schema ver | Purpose |
|---|---|---|
| `verify_all_summary.json` | — | Top-level pass/fail summary for all steps. |
| `exception_budget.json` | 1 | Current vs baseline exception-site count + ok flag. |
| `verify_step_durations.json` | 1 | Per-step wall-clock timings (`total_ms`, `steps[]`). |
| `verify_step_budget_check.json` | 2 | Per-step budget regression check; lists offenders. |
| `shadow_backend.json` | 1 | Selected shadow backend, reason, fallback chain. |
| `swallowed_exceptions.json` | 1 | Snapshot of swallowed exception counts by call-site. |
| `scenes_index.json` | — | Scene manifest for the project. |
| `worlds_index.json` | — | World manifest for the project. |

Additional artifacts (content audit, encounter audit, stamp/brush/macro/room
audits, replays summary, doctor assets) are also written — see
`artifacts_written` keys in `mesh_cli/verify.py` for the full list.

---

## 3. CLI commands

### verify-all

```
python -m mesh_cli verify-all --artifacts artifacts
```

Runs every validation step and writes all artifacts above. Exit code 0 on
success, non-zero on failure.

### debug-report

```
python -m mesh_cli debug-report --artifacts artifacts
```

Reads the artifacts directory and prints three sections:

1. **Verify Health Snapshot** — exception budget, total verify ms, step
   budget ok/offenders.
2. **Shadow Backend** — selected backend, reason, fallback list.
3. **Swallowed Exceptions** — total, distinct sites, per-site counts.

Optional: `--json-out path/to/report.json` writes the full payload as
deterministic JSON (schema version 1).

### health-report

```
python -m mesh_cli health-report --artifacts artifacts
```

Reads artifacts + baseline files and writes `artifacts/health_report.json`
(schema version 1) containing signals:

- `exception_budget` — current count vs baseline from
  `tooling/metrics/exception_budget_count.txt`.
- `verify_step_durations` — total ms from last verify run.
- `mypy_baseline` — error count from `tooling/mypy_baseline.txt`.
- `hotspots` — top 10 largest `.py` files by line count.

---

## 4. Baseline update commands

When a verify step fails because the baseline is stale, the failure message
prints the exact update command. Below are the patterns for reference.

### Exception budget baseline

Baseline file: `tooling/metrics/exception_budget_count.txt`

The update command is printed on failure by `verify-all`. It calls internal
helpers to recount exception-budget sites and overwrite the baseline file.
Look for the `update baseline with:` line in the failure output and run it
verbatim.

### Verify step budget baseline

Baseline file: `tooling/metrics/verify_step_budget.json`

Same pattern — the failure output includes a `python -c "..."` one-liner
that reads the latest `verify_step_durations.json` from the artifacts
directory and rewrites the baseline. Run it after a legitimate performance
change.

### Unmarked-test ratchet baseline

Baseline file: `tests/baselines/unmarked_test_nodeids.txt`

```
python -c "import os, subprocess, sys; import tests.test_tier_marker_ratchet as t; os.environ['MESH_UPDATE_UNMARKED_BASELINE']='1'; raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q', t.__file__]))"
```

This re-collects all unmarked test node IDs and overwrites the baseline.
Only run it after intentionally adding tests without a tier marker.

---

## 5. Editor debug overlay

### Enabling debug mode

1. Press **F3** in-game, or set `"debug_on_start": true` in `config.json`.
2. The debug overlay appears with engine state, tool mode, and diagnostics
   panels.
3. Optional dev-only asset watcher: set `MESH_HOT_RELOAD=1` to enable
   debounced asset cache reloads on file changes (`assets/` + `packs/`).

### Diagnostics sections

| Section | Content |
|---|---|
| **Swallowed Exceptions** | `total_swallowed_count`, `distinct_sites`, per-site breakdown. |
| **Shadow Backend** | `selected` backend, `reason`, `fallbacks` list. |
| **Verify Health Snapshot** | Exception budget (current/baseline, ok), total verify ms, step budget ok + worst offender. Requires `set_verify_artifacts_dir()` to be called. |

### Overlay controls

- **Toggle overlay**: swallowed-exceptions overlay is toggled via
  `toggle_swallowed_exceptions_overlay` (debug-gated — no-op when debug is
  off).
- **Copy to clipboard**: copies all sections as formatted text.
- **Reset swallowed exceptions**: clears counters and cache immediately
  (debug-gated).

### Throttling

All overlay data refreshes are throttled to **0.5 s** intervals:

- Shadow backend diagnostics are fetched at most once per 0.5 s window.
- Verify snapshot files are re-read only when their mtime changes *and* the
  throttle window has elapsed.
- Swallowed exception summary refresh is time-gated via
  `_swallowed_exceptions_overlay_next_refresh_ts`.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `?` or `?/?` in overlay/report | Artifact files missing or not yet generated. | Run `python -m mesh_cli verify-all --artifacts artifacts` first. |
| `(unavailable)` for shadow backend | `get_shadow_backend_diagnostics()` failed (no GL context or import error). | Expected in headless/CLI — informational only. |
| Verify Health Snapshot blank | Artifacts directory not configured in the overlay controller. | Call `overlay.set_verify_artifacts_dir(path)` or run the CLI report instead. |
| Stale data in overlay | Throttle window hasn't elapsed yet. | Wait 0.5 s or trigger a force-refresh. |
| Corrupt JSON → `?` | An artifact file contains invalid JSON. | Re-run `verify-all` to regenerate. |
| Debug sections missing | Debug mode not enabled. | Press **F3** or set `debug_on_start: true`. |
