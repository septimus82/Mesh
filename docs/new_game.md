# New Game Bootstrap

Create a deterministic starting save for a fresh campaign playthrough —
no GUI required, CI-friendly, identical output on every run.

## Quick Start

```bash
# Create a new-game save (default: mini_campaign_01, seed 42)
python -m mesh_cli new-game --out saves/fresh.json

# With explicit seed
python -m mesh_cli new-game --out saves/fresh.json --seed 12345 --force

# Print payload to stdout as well
python -m mesh_cli new-game --out saves/fresh.json --json --force
```

## Options

| Flag              | Default               | Description                                  |
|-------------------|-----------------------|----------------------------------------------|
| `--out <file>`    | *(required)*          | Path for the output save JSON                |
| `--campaign <id>` | `mini_campaign_01`    | Campaign identifier                          |
| `--scene <id>`    | campaign default      | Override starting scene path                 |
| `--seed <int>`    | `42`                  | RNG seed stored in the save                  |
| `--force`         | off                   | Allow overwriting an existing file            |
| `--json`          | off                   | Also print the payload to stdout              |

## What It Produces

A single JSON file that:

- Passes `validate_save()` (schema v2).
- Contains `save_format_version`, `save_schema_version`, scene ids,
  game state with `campaign.started` flag, empty quest/entity blocks,
  RNG seed + initial RNG state, and metadata.
- Is **byte-identical** across runs with the same arguments.
- Can be loaded by the normal `SaveManager.load_game()` path.

## Payload Structure (abridged)

```json
{
  "save_format_version": 1,
  "save_schema_version": 2,
  "scene_id": "scenes/town_schedule_01.json",
  "scene_path": "scenes/town_schedule_01.json",
  "gold": 0,
  "flags": ["campaign.started"],
  "game_state": {
    "flags": {"campaign.started": true},
    "counters": {},
    "chapter": 1,
    "level": 1,
    "xp": 0,
    "equipment": {"weapon": null, "armor": null, "accessory": null},
    "perks": [],
    "quests": {}
  },
  "saved_entities": {"schema_version": 1, "entities": []},
  "saved_quests": {"schema_version": 1, "quests": {}},
  "campaign": "mini_campaign_01",
  "rng_seed": 42,
  "rng_state": { "global_seed": 42, "..." : "..." },
  "meta": {
    "slot": "new_game",
    "scene_path": "scenes/town_schedule_01.json",
    "timestamp": "1970-01-01T00:00:00",
    "version": 2
  }
}
```

## Workflow: New Game → Replay Check → Release

```bash
# 1. Bootstrap a fresh save
python -m mesh_cli new-game --out artifacts/new_game.json

# 2. Run the campaign replay-check for determinism verification
python -m mesh_cli campaign replay-check \
  --campaign mini_campaign_01 \
  --out-dir artifacts/campaign_replay/new_game_seeded

# 3. Full verification pipeline
python -m mesh_cli verify-all --artifacts artifacts
python -m mesh_cli release check --artifacts artifacts
```

## CI Integration

```yaml
- name: New Game Bootstrap + Replay
  run: |
    python -m mesh_cli new-game --out artifacts/new_game.json
    python -m mesh_cli campaign replay-check \
      --campaign mini_campaign_01 \
      --out-dir artifacts/campaign_replay/ci
    python -m mesh_cli verify-all --artifacts artifacts
    python -m mesh_cli release check --artifacts artifacts
```

## Architecture

The command reuses:

- `engine.game_state_controller.GameState` — default player state
- `engine.rng_service.RNGService` — isolated seed → state snapshot
- `engine.save_runtime.schema.validate_save` — structural validation
- `engine.persistence_io.write_json_atomic` — atomic, deterministic write
