# Episode Replay Check

`mesh_cli episode replay-check` runs a deterministic playtest harness for episode scenes.

## Usage

```bash
python -m mesh_cli episode replay-check \
  --scene episode_01_intro.json \
  --script replays/ep01.json \
  --out-dir artifacts/replays/ep01 \
  --seed 123
```

## Replay Script Format

```json
{
  "dt_schedule": [0.2, 0.2, 0.2],
  "actions": [
    {"t": 0, "type": "emit", "event": "ep02_entered"},
    {"t": 2, "type": "dialogue_choose", "choice": 1},
    {"t": 3, "type": "interact", "entity": "episode_02_ep02_signal_terminal"},
    {"t": 4, "type": "save"},
    {"t": 5, "type": "restore"},
    {"t": 6, "type": "assert_flag", "flag": "ep02.exit_unlocked", "value": true}
  ]
}
```

Supported action types:
- `emit`
- `interact`
- `dialogue_choose`
- `save`
- `restore`
- `assert_flag`

## Artifacts

The command writes deterministic artifacts under `--out-dir`:
- `replay_report.json`
- `replay_report.txt`
- `events.ndjson`
- `digests.json`
- `final_state_bundle.json`

`replay_report.json` includes run-to-run determinism checks for:
- event sequence equality
- digest sequence equality
- final state bundle equality
