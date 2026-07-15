# Mesh Engine -- Canonical Input Bindings

This document locks the **canonical** (player-facing) keybind contract for Mesh Engine.

Source of truth:
- Runtime bindings are configured via `config.json` -> `input_bindings`.
- Tests enforce that the core controls below do not conflict (no duplicate keys).

## Core controls

### Movement
- `move_up`: `W`
- `move_down`: `S`
- `move_left`: `A`
- `move_right`: `D`

### Interact / Attack
- `interact`: `E`
- `attack`: `SPACE`

### UI overlays
- `toggle_help`: `H`
- `toggle_variant_picker`: `V`
- `toggle_inspector`: `I`
- `show_quests`: `Q`
- `show_inventory`: `TAB`
- `show_character`: `C`

### Save / Load
Snapshot (tooling-style quick actions):
- `quick_save`: `F5`
- `quick_load`: `F9`

SaveManager (in-game save slots / last-save convenience):
- `save_game`: `Ctrl+F5`
- `quickload_last_save`: `F10`

## Notes
- Editor-specific actions (e.g. `editor_dialogue`, `editor_tile`) are intentionally excluded from the "core controls conflict" test because they may reuse keys already used by gameplay.
- `save_game` is owned by the capture route table because it uses a modifier chord. It is intentionally not represented as a configurable bare-key binding in `config.json`.
