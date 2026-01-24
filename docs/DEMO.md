# Master Demo

Single runbook for the full playable demo: Golden Slice + Act 1.

## One command

From the repo root:

```bash
python mesh_cli.py run-preset demo_master
```

Notes:
- The preset runs the Golden Slice demo pack first, then runs Act 1 (prologue -> chapter 5 stub).
- Close the game window to advance to the next step in the preset sequence.

## One in-game flow (no config edits)

### Open the picker

- Press `V` to open the **Variant Picker**.

Keys:
- `Left/Right`: switch tabs
- `Up/Down`: select
- `Enter`: load selection
- `Esc`: close

### Tabs

- **Ridge Outpost** (Golden Slice location 1)
- **Hollowmere Outskirts** (Golden Slice location 2)
- **Act 1** (via `act1_index` -> `act1_full_demo`)

## What's included

### Golden Slice

Two locations:
- Ridge Outpost
- Hollowmere Outskirts

Use the picker to swap between variants without editing config.

### Act 1

- Prologue world (`worlds/act1_prologue.json`)
- Chapter 1 world (`worlds/act1_chapter1.json`)
- Chapter 2 world (`worlds/act1_chapter2_stub.json`)
- Chapter 3 world (`worlds/act1_chapter3_stub.json`)
- Chapter 4 world (`worlds/act1_chapter4_stub.json`)
- Chapter 5 world (`worlds/act1_chapter5_stub.json`)

When running Act 1 contexts, the top-left demo HUD shows:
- `Act 1: <world> | quest:<id> | +gold:<delta> +flags:<count> | V picker`

## Quality gate

Run tests with warnings-as-errors:

```bash
python -m pytest -q -W error
```

## Troubleshooting

- **Picker says "No variants available"**
  - Ensure `config.json` includes the required presets (Golden Slice indices + `act1_*`).
- **Picker shows missing entries**
  - A listed preset is referenced but not present in `config.json`.
- **Recursion detected**
  - A `run-preset` chain forms a cycle.
