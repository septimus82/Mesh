# Content Scaffold

`mesh_cli content episode new` generates a deterministic episode skeleton that follows the Episode 1 wiring style.

## Command

```bash
python -m mesh_cli content episode new --id ep02 --title "Signal in the Dust" --out-dir . --seed 123
```

Options:
- `--id`: episode identifier (`ep02` style; must include digits).
- `--title`: display title.
- `--out-dir`: target repository root to patch.
- `--seed`: deterministic metadata seed (default `123`).
- `--dry-run`: validate and print planned edits without writing.

## Generated Outputs

- `scenes/episode_02_ep02.json`
- `docs/episode_02_ep02.md`
- `tests/test_episode_02_ep02_integration.py`

And deterministic registry updates:
- `assets/data/events.json`
- `assets/data/quests.json`
- `cutscenes.json`
- `assets/data/dialogues.json` (created if missing)
- `assets/prefabs.json`

## Safety Rules

- Refuses to overwrite generated target files.
- Refuses duplicate ids/names in registries (events, quests, cutscenes, dialogues, prefabs).
- Parses JSON first and rewrites through canonical stable formatting.

## Customizing the Scaffold

After generation, update:
- Dialogue text in the generated dialogue script/prefab.
- Scene layout positions in the generated scene.
- Quest stage text and completion events.
- Controller action lists for your branch logic.

The generated integration test verifies registry wiring and deterministic quest progression; extend it with full gameplay path assertions for the chapter you are shipping.
