# Act 1

## How to run

Run Act 1 Chapter 1:

- `python mesh_cli.py run-preset act1_chapter1`

Run Act 1 Chapter 2 (slice):

- `python mesh_cli.py run-preset act1_chapter2`

Run Act 1 Chapter 3 (stub):

- `python mesh_cli.py run-preset act1_chapter3`

Run Act 1 Chapter 5 (finale stub):

- `python mesh_cli.py run-preset act1_chapter5`

Run Act 1 Chapter 4 (stub):

- `python mesh_cli.py run-preset act1_chapter4`

Optional: run the prologue then Chapter 1:

- `python mesh_cli.py run-preset act1_demo`

Optional: run the prologue, Chapter 1, then Chapter 2:

- `python mesh_cli.py run-preset act1_demo_extended`

## Demo path

- Run: `python mesh_cli.py run-preset act1_full_demo`

This is the canonical Act 1 chain. Shorter compatibility presets exist (`act1_demo`, `act1_demo_extended`),
but `act1_full_demo` is the recommended default.

What to do (expected path):

- Prologue: walk to the end marker to complete the prologue.
- Chapter 1: flip the Gate Path switch, go to Clearing, then continue to Overlook.
- Chapter 2: enter the Chapter 2 start + checkpoint zones to begin Chapter 2.
- Chapter 2 (Ruined Gate): take `ToRuinedGate`, enter the start zone, flip the switch, then reach the goal zone.
- Chapter 2: pick Path A or B, then reach `Ch2DepartZone` to complete Chapter 2.
- Chapter 3: take `ToChapter3`, then enter start + checkpoint zones.
- Chapter 3: find the note, then reach the exit zone to complete Chapter 3.
- Chapter 4: take `ToChapter4`, then enter start + checkpoint zones.
- Chapter 5: take `ToChapter5`, then enter start + checkpoint zones.

By the end, these flags should be set:

- `act1_prologue_complete`
- `act1_chapter1_complete`
- `act1_chapter2_started`
- `act1_ch2_ruin_unlocked`
- `act1_ch2_ruin_complete`
- `act1_chapter2_complete`
- `act1_chapter3_started`
- `act1_ch3_note_found`
- `act1_chapter3_complete`
- `act1_chapter4_started`
- `act1_chapter4_complete`
- `act1_chapter5_started`

## World entrypoints

- `worlds/act1_prologue.json`
- `worlds/act1_chapter1.json`
- Back-compat stub world: `worlds/act1_chapter1_stub.json`

## Tests

- Install dev/test deps: `python -m pip install -e ".[dev]"`
- Run suite (warnings as errors): `python -m pytest -q -W error`
