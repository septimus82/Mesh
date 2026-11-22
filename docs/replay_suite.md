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

### Quest scoping (golden schema 2)

Digested quest state holds only the quests a replay is about: those it declares (campaign `quests` list, the episode's own
quest) plus any quest that is not pristine in that snapshot. Untouched, undeclared catalogue quests are excluded, so adding
unrelated quests to `assets/data/quests.json` does not invalidate goldens (`mesh_cli.replay_digest_projection.scope_quest_state`).

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

## Pooled tick timing (T-07)

Episode cases are short (8 to 18 ticks), and nearest-rank p95 of fewer than 20 samples is just the slowest tick, so one
scheduler stall used to fail `max_tick_ms_p95`. The budget values are unchanged; the measurement is not:

- `replay-check` already runs the episode twice (`run_1`, `run_2`). When a suite case has fewer than
  `MIN_TICK_SAMPLES` (40) tick samples in those, it runs further fresh, timing-only executions in the same process
  until it has 40, at most `MAX_TIMING_EXECUTIONS` (10) executions in all. 40 samples is the smallest pool whose p95 (the
  38th smallest) ignores the two slowest ticks: an isolated stall passes, a sustained slowdown (over 5% of ticks)
  still fails.
- `tick_ms_p95` is computed over the pooled samples. `total_ms` and `tick_ms_max` stay the canonical `run_1` values,
  so `max_total_ms` is still one replay's total and `max_tick_ms_max` is no looser or stricter than before.
- Digests, events, final state and goldens come from `run_1` only. Every repeat builds a fresh context and must
  reproduce `run_1`'s digests, events and final state exactly, otherwise the case fails (nondeterminism).
- No warm-up is excluded: the runner has no such notion, setup happens before the first tick, and pooling dilutes any
  one-off cost.
- `performance.json` / `timings.json` carry a `pooled` object: `min_samples`, `min_samples_met`, `executions`,
  `repeats` (beyond `run_1` and `run_2`), `samples_per_execution`, `total_ms_per_execution`, `pooled_count`,
  `tick_ms_p50`, `tick_ms_p95`, `tick_ms_max`. `tick_ms_count` / `tick_ms_list` remain the canonical execution's.
- Campaign cases record placeholder zero timings, so their budgets are not a timing measurement.

## CI Budget Notes

CI enforces replay budgets on Linux only:

```powershell
python -m mesh_cli replays run --suite replays/suite.json --out-dir artifacts/replay_suite --seed 123 --budgets-only-on linux --quiet
```

This avoids Windows timing noise while still keeping a deterministic perf gate.

The suite runs on every pull request and push as the required `replays (ubuntu-latest, py3.11)` job (R-2), and again in the release `ship` job.

CI policy: CI only runs `mesh_cli replays run` and never updates goldens automatically.
