# Input Bindings

Runtime bindings are configured via `config.json` -> `input_bindings`.

For the canonical, player-facing keybind contract, see `docs/INPUT_BINDS.md`.

Engine fallback defaults are bound via `InputManager.bind_default_actions(arcade)` when config bindings are absent.

| Action | Default Key Name |
| --- | --- |
| `move_up` | `W` |
| `move_down` | `S` |
| `move_left` | `A` |
| `move_right` | `D` |
| `interact` | `E` |
| `attack` | `SPACE` |
| `show_quests` | `Q` |
| `show_inventory` | `TAB` |
| `show_character` | `C` |
| `toggle_editor` | `F4` |
| `toggle_help` | `H` |
| `toggle_inspector` | `I` |

Note: debug/authoring hotkeys (for example `F3` debug, `F4` editor, `F5/F6` quick save/load) are handled directly in `engine/input_runtime/capture_runtime.py` and are not part of the action bindings table above.
