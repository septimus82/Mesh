# Campaign Replay Check

Determinism verification toolchain for stitched campaign flows.

## Quick Start

```bash
# Run the default mini_campaign_01 replay check
python -m mesh_cli campaign replay-check

# Custom output directory
python -m mesh_cli campaign replay-check --campaign mini_campaign_01 --out-dir artifacts/my_check

# JSON diff output
python -m mesh_cli campaign replay-check --json
```

## What It Does

1. Loads a scripted playthrough definition from `tests/fixtures/campaign_scripts/<campaign>.json`
2. Runs **two** identical headless playthroughs using the same dt schedule and actions
3. Records a **digest trace** at every drain/milestone tick
4. Exports **checkpoint debug bundles** after each scene (town, puzzle, combat)
5. Diffs the two digest traces to detect nondeterminism
6. Exits **0** if identical, **1** if divergent

## Output Files

| File | Description |
|------|-------------|
| `run_1_digest_trace.json` | Digest + milestone log from run 1 |
| `run_2_digest_trace.json` | Digest + milestone log from run 2 |
| `digest_diff.txt` | Human-readable diff summary |
| `digest_diff.json` | Machine-readable diff (with `--json`) |
| `debug_bundle_checkpoint_after_town.json` | State snapshot after town scene |
| `debug_bundle_checkpoint_after_puzzle.json` | State snapshot after puzzle scene |
| `debug_bundle_checkpoint_after_combat.json` | State snapshot after combat scene |

Default output directory: `artifacts/campaign_replay/<campaign_id>/`

## Script Format

Campaign scripts live in `tests/fixtures/campaign_scripts/` and define:

```json
{
  "campaign_id": "mini_campaign_01",
  "quests": ["mini_campaign_01", "town_schedule_01", ...],
  "initial_flags": ["campaign.started"],
  "scenes": [
    {
      "scene_id": "town",
      "scene_path": "scenes/town_schedule_01.json",
      "start_hour": 8.0,
      "steps": [
        {"action": "set_hour", "hour": 8.0},
        {"action": "step_trigger", "trigger": "town_entry_trigger", "player_x": 128.0, "player_y": 256.0},
        {"action": "drain"},
        {"action": "emit", "event_type": "vendor_interact_attempt", "payload": {"interactor": "player"}},
        {"action": "process_quests"},
        {"action": "checkpoint", "label": "after_town"}
      ]
    }
  ]
}
```

### Available Actions

| Action | Parameters | Description |
|--------|-----------|-------------|
| `set_hour` | `hour` | Set day/night cycle hour |
| `update_schedule` | `dt` | Tick NPC schedule + time gate |
| `step_trigger` | `trigger`, `player_x`, `player_y` | Walk player onto a trigger volume |
| `drain` | — | Drain event bus and route to ActionListRunners |
| `emit` | `event_type`, `payload` | Emit a gameplay event |
| `damage_enemy` | `amount` | Deal damage to enemy (combat scene) |
| `process_quests` | — | Full quest event routing cycle |
| `checkpoint` | `label` | Snapshot state and record checkpoint bundle |

## Architecture

```
mesh_cli campaign replay-check
  └─ mesh_cli/campaign.py
       └─ tooling/campaign_replay.py
            ├─ Reuses DigestTracker from engine/save_runtime/digest.py
            ├─ Same mock infrastructure as tests/test_mini_campaign_01_integration.py
            └─ Zero Arcade dependency (fully headless)
```

## CI Integration

Add to your CI pipeline:

```bash
python -m mesh_cli campaign replay-check --out-dir artifacts/campaign_replay/mini_campaign_01
```

Exit code 0 = deterministic, exit code 1 = nondeterminism detected.
