# Golden Slice Demo (Runbook)

Run the Golden Slice demo pack and use the in-game picker to swap between variants without editing config.

## Run (recommended)

From the repo root:

```bash
python mesh_cli.py run-preset golden_slice_showcase
```

Notes:
- The showcase preset runs a quick validation pass, then launches the game window.
- Close the game window to continue to the next variant in the showcase sequence.

## Controls

- `V`: Open **Golden Slice Variant Picker**
  - `Up/Down`: Select
  - `Enter`: Load selected variant
  - `Esc`: Close
- `H`: Help overlay (if available)

## What you'll see in-game

- **Top-left Golden Slice demo HUD strip** (Golden Slice contexts only):
  - Variant, active quest id, gold delta / new flags since scene load, and hint keys.

## What's included

Variants included in the showcase (see `config.json` preset descriptions):
- **G (linear)**: Beacon objective: quest + reward toast
- **H (linear)**: Relay objective: quest + reward toast (content-only)
- **I (linear)**: Signal cache objective: quest + reward toast (content-only)
- **J (branching choice)**: Signal fork: branching choice (content-only)
- **K (puzzle-lite)**: Puzzle-lite switch gate: unlock event gates goal quest (content-only)

## Quality gates (determinism / no flakes)

- Run tests with warnings-as-errors:
  ```bash
 python -m pytest -q -W error
  ```
- Determinism expectations:
  - Stable ordering and outputs (tests and tooling)
  - No time/random dependencies in tests

## Troubleshooting

- **Picker says "No variants available"**
  - Ensure `config.json` contains `presets.golden_slice_showcase` and it lists the `golden_slice_variant_*` presets.
- **Picker shows "(missing)" entries**
  - A preset name is referenced by the showcase but not present in `config.json`.
- **Picker says recursion detected**
  - `golden_slice_showcase` (or a referenced preset) contains `run-preset` steps that create a cycle.
- **Demo HUD strip not visible**
  - It only renders when you're in a Golden Slice context (e.g. `MESH_ACTIVE_PRESET=golden_slice_variant_*` or a `golden_slice_*` world).
  - Launch via the showcase preset (recommended) to ensure the preset context is set.

## Authoring / adding variants

For the standardized rules and templates for adding new Golden Slice variants, see:
- `docs/GOLDEN_SLICE_VARIANTS.md`

