# Replay Suite

`mesh_cli replays run` makes episode replays a first-class deterministic regression gate with golden digests.

## Command

```powershell
python -m mesh_cli replays run --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123
```

Options:

- `--budgets-only-on all|linux|windows|none`: enforce case budgets only on selected platform kind.
- `--json`: print `suite_report.json` payload to stdout.
- `--quiet`: suppress normal text output.

`replays run --update-golden` is intentionally blocked; use `replays update-golden --reason "..."` so golden changes are explicit and reviewable.

## Safe Golden Update Command

Use `mesh_cli replays update-golden` when a behavior change is intentional and reviewed:

```powershell
python -m mesh_cli replays update-golden --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --reason "Intentional replay behavior change"
```

Options:

- `--case <id>`: update one suite case only.
- `--reason "<text>"`: required when golden files would change.
- `--allow-no-reason`: bypass reason requirement for exceptional cases.
- `--max-changed <N>`: fail before writing if more than `N` cases would change.
- `--dry-run`: compute and report changes without modifying golden files.
- `--json`: print `update_golden_report.json` payload to stdout.
- `--quiet`: suppress normal text output.

Safety behavior:

- `--out-dir` must already exist.
- Unknown suite modes are rejected unless `--allow-unknown-mode` is provided.
- If changes are detected and `--reason` is missing, command fails unless `--allow-no-reason` is set.
- Per-case deterministic diffs are written to `<out-dir>/<id>/golden_diff.txt`.

## Suite Format

`replays/suite.json` is a JSON array:

```json
[
  {
    "id": "ep01",
    "scene": "scenes/episode_01_intro.json",
    "script": "replays/ep01.json",
    "golden": "replays/golden/ep01_golden.json",
    "budgets": {
      "max_total_ms": 1200,
      "max_tick_ms_p95": 10,
      "max_tick_ms_max": 25
    }
  }
]
```

Each case runs `mesh_cli episode replay-check` in-process and writes artifacts to:

- `<out-dir>/<id>/replay_report.json`
- `<out-dir>/<id>/events.ndjson`
- `<out-dir>/<id>/digests.json`
- `<out-dir>/<id>/final_state_bundle.json`
- `<out-dir>/<id>/performance.json`

Campaign-mode cases currently ignore replay seed by design and report `seed_ignored: true` in case artifacts/suite reports.

`performance.json` includes deterministic timing metrics:

- `total_ms`
- `tick_ms_list` (rounded to 3 decimals)
- `tick_ms_p50`
- `tick_ms_p95`
- `tick_ms_max`
- budget evaluation (`ok/skipped/violations`)

## Golden Contract

Each golden file stores:

- `expected_event_digest`
- `expected_world_digest`
- `expected_final_state_digest`
- counts and first/last previews for readability

Default behavior compares run output to golden and fails on mismatch.  
Mismatch details are written to `<out-dir>/suite_report.json` and `<out-dir>/suite_report.txt`.

### Digest Projection Stability

Replay artifacts intentionally remain rich for debugging (`replay_report.json`, timings, provenance-like metadata).
Golden digests are computed from projected payloads so report-only metadata does not churn goldens.

Excluded report-only keys include:

- `seed_ignored`
- `timing` and any key prefixed with `timing*`
- `host`
- `env` / `environment`
- `provenance`
- `platform`
- `python_version`
- `generated_at`
- `tool_version`

These are excluded because they describe runtime/report context, not gameplay state transitions.
Gameplay-relevant changes (event types/payloads, digest sequence, final state content) still change digests.

### Digest Projection Policy

Digest projection is policy-gated by a stable config constant:

- `mesh_cli.replays.DIGEST_PROJECTION_POLICY`

If you intentionally change projection behavior:

1. Edit `DIGEST_PROJECTION_POLICY` (keys/prefixes) intentionally.
2. Update the ratchet expectation in `tests/test_replay_digest_projection_policy.py`.
3. Re-run replay suite tests to confirm gameplay-vs-report separation still holds.

This keeps digest-relevant fields reviewable and prevents silent drift where reporting metadata starts influencing goldens.

## Updating Goldens

Recommended workflow:

```powershell
python -m mesh_cli replays run --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123
python -m mesh_cli replays update-golden --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --case ep02 --dry-run
python -m mesh_cli replays update-golden --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --case ep02 --reason "Adjusted ep02 scripted interactions"
```

Then review:

- `<out-dir>/update_golden_report.json`
- `<out-dir>/update_golden_report.txt`
- `<out-dir>/<id>/golden_diff.txt` for changed cases

Finally re-run `replays run` to confirm the ratchet passes before committing.

## CI Budget Notes

CI enforces replay budgets on Linux only:

```powershell
python -m mesh_cli replays run --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --budgets-only-on linux --quiet
```

This avoids Windows timing noise while still keeping a deterministic perf gate for release branches.

CI policy: CI only runs `mesh_cli replays run` and never updates goldens automatically.
