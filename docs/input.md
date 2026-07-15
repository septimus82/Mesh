# Input Bindings

Runtime bindings are configured via `config.json` -> `input_bindings`.

For the canonical, player-facing keybind contract, see `docs/INPUT_BINDS.md`.

Engine fallback defaults are bound via `InputManager.bind_default_actions(arcade)` when config bindings are absent.

| Action | Default Key Name |
| --- | --- |
| `attack` | `SPACE` |
| `interact` | `E` |
| `move_down` | `S, DOWN` |
| `move_left` | `A, LEFT` |
| `move_right` | `D, MOTION_RIGHT` |
| `move_up` | `W, MOTION_UP` |
| `pause_menu` | `ESCAPE` |
| `quick_load` | `F9` |
| `quick_save` | `F5` |
| `quickload_last_save` | `F10` |
| `save_game` | `Ctrl+F5` |
| `show_character` | `C` |
| `show_inventory` | `TAB` |
| `show_quests` | `J, Q` |
| `toggle_editor` | `F4` |
| `toggle_help` | `H` |
| `toggle_inspector` | `I` |

Note: debug/authoring hotkeys (for example `F3` debug, `F4` editor, `F5/F6` quick save/load) are handled directly in `engine/input_runtime/capture_runtime.py` and are not part of the action bindings table above.

---

## Input Architecture

### Keyboard Input

Keyboard events flow through `capture_runtime.py` -> `capture_key_router.py` which resolves keys to action IDs based on the current focus scope, then dispatches to handler modules.

### Mouse Input

Mouse events are handled by the **capture mouse router** (`engine/input_runtime/capture_mouse_router.py`).

**Architecture:**
- **Router** (`capture_mouse_router.py`): Glue-only module that builds/caches the route table, resolves events to action IDs, and dispatches via prefix registry. Contains no handler logic.
- **Model** (`capture_mouse_router_model.py`): Route table schema (`MouseRouteSpec`), builder (`build_mouse_routes()`), validation (`validate_route_table()`), and audit functions.
- **Per-scope handlers** (`capture_mouse_router_handlers_<scope>.py`): Each scope (tile_paint, entity_select, confirm_modal, etc.) has its own handler module with a `dispatch_*_mouse()` function.

**Key files:**
| File | Purpose |
| --- | --- |
| `capture_mouse_router.py` | Main router (glue + prefix dispatch) |
| `capture_mouse_router_model.py` | Route specs, builder, validation |
| `capture_mouse_router_handlers_*.py` | Per-scope handler modules |
| `capture_mouse_router_handlers_*_base.py` | Shared helper utilities (no routes) |

**Adding new mouse handlers:**
1. Create `capture_mouse_router_handlers_<scope>.py` with a `dispatch_<scope>_mouse()` function
2. Add routes in `build_mouse_routes()` in the model
3. Register prefix in `MOUSE_PREFIX_DISPATCH` in the router

**Deprecated shims:**
The old monolithic handlers (`capture_mouse_router_handlers_paint.py`, `capture_mouse_router_handlers_select.py`) are frozen and deprecated. They exist only for backward compatibility and emit `DeprecationWarning` on import. Policy tests prevent new shims.

See module docstrings in `capture_mouse_router.py` for detailed developer notes.
