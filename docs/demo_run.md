# Demo Pipeline — One Command Pipeline

Run the complete demo pipeline end-to-end with a single command.
Deterministic, fail-fast, headless-safe.

## Quick Start

```bash
python -m mesh_cli demo pipeline --out-dir artifacts/demo --seed 123
```

## Pipeline

The command executes these steps in fixed order, stopping at the first
failure:

| # | Step                    | Outputs under `out-dir/`                  |
|---|-------------------------|-------------------------------------------|
| 1 | release check           | `release/` (verify-all, asset audit, …)   |
| 2 | new-game                | `new_game.json`                           |
| 3 | campaign replay-check   | `replay/` (digest traces, checkpoints)    |
| 4 | debug export            | `debug/debug_bundle.json`                 |
| 5 | export build            | `bundle/` (shippable bundle + manifest)   |
| 6 | demo report             | `demo_report.json`, `demo_report.txt`     |

## Options

| Flag              | Default             | Description                                |
|-------------------|---------------------|--------------------------------------------|
| `--out-dir <dir>` | *(required)*        | Root directory for all output artifacts    |
| `--seed <int>`    | `42`                | RNG seed for new-game payload              |
| `--campaign <id>` | `mini_campaign_01`  | Campaign identifier                        |
| `--quiet`         | off                 | Suppress stdout (report files still written) |
| `--json`          | off                 | Print `demo_report.json` to stdout         |
| `--no-fail`       | off                 | Exit 0 even if a step fails                |

## Exit Codes

| Code | Meaning                        |
|------|--------------------------------|
| 0    | All steps passed               |
| 1    | A step failed (see report)     |
| 2    | Usage / argument error         |

## Report Format

`demo_report.json`:

```json
{
  "schema_version": 1,
  "seed": 123,
  "campaign": "mini_campaign_01",
  "out_dir": "D:/Games/Mesh/artifacts/demo",
  "steps": [
    {"name": "release-check", "ok": true, "exit_code": 0, "outputs": {...}},
    {"name": "new-game", "ok": true, "exit_code": 0, "outputs": {...}},
    ...
  ],
  "file_sizes": {
    "new_game.json": 1234,
    "debug/debug_bundle.json": 5678,
    "demo_report.json": 890
  },
  "ok": true,
  "failed_step": null
}
```

`demo_report.txt`:

```
Mesh Demo Run
Campaign: mini_campaign_01
Seed: 123
Output: D:/Games/Mesh/artifacts/demo

Steps:
  release-check: OK (exit=0)
  new-game: OK (exit=0)
  campaign-replay-check: OK (exit=0)
  debug-export: OK (exit=0)
  export-build: OK (exit=0)

Result: OK
```

## Workflow

```bash
# 1. Run the full demo
python -m mesh_cli demo pipeline --out-dir artifacts/demo --seed 123

# 2. Inspect the report
cat artifacts/demo/demo_report.txt

# 3. Load the new-game save
# (in-engine or via tests)

# 4. Compare two runs for determinism
python -m mesh_cli demo pipeline --out-dir artifacts/demo_a --seed 123
python -m mesh_cli demo pipeline --out-dir artifacts/demo_b --seed 123
# Compare demo_report.json files — should be identical except out_dir paths
```

## CI Integration

```yaml
- name: Demo Pipeline
  run: |
    python -m mesh_cli demo pipeline \
      --out-dir artifacts/demo \
      --seed 42 \
      --quiet \
      --json
```

## Architecture

The orchestrator (`mesh_cli/demo.py`) reuses existing commands:

- `mesh_cli.release._handle_check()` — release check pipeline
- `mesh_cli.new_game.build_new_game_payload()` — deterministic save
- `mesh_cli.campaign._handle_replay_check()` — replay determinism
- `mesh_cli.debug._handle_export()` — debug bundle snapshot
- `mesh_cli.export._handle_export_build()` — shippable bundle

Each step is an independently mockable function, making the pipeline
fully testable without requiring a graphics context.
