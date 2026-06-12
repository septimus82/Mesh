"""Helpers for translating human-readable key names to Arcade key codes."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, Set

import engine.optional_arcade as optional_arcade
from engine.input import InputManager

ACTION_SHOW_CHARACTER = "show_character"

# Default actions the engine expects to exist.
DEFAULT_ACTIONS: tuple[str, ...] = (
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "interact",
    "attack",
    "show_quests",
    "show_inventory",
    ACTION_SHOW_CHARACTER,
    "toggle_editor",
    "toggle_help",
    "toggle_inspector",
    "pause_menu",
    "editor_dialogue",
    "editor_animation",
    "editor_tile",
    "editor_lights",
)

_KEY_NAME_TO_CODE: Dict[str, int] | None = None
_CODE_TO_NAME: Dict[int, str] | None = None


def _ensure_key_maps(arcade_module=optional_arcade.arcade) -> tuple[Dict[str, int], Dict[int, str]]:
    """Build and cache key name <-> code lookups from optional_arcade.arcade.key."""
    global _KEY_NAME_TO_CODE, _CODE_TO_NAME
    if _KEY_NAME_TO_CODE is not None and _CODE_TO_NAME is not None:
        return _KEY_NAME_TO_CODE, _CODE_TO_NAME

    name_to_code: Dict[str, int] = {}
    code_to_name: Dict[int, str] = {}
    for name, value in arcade_module.key.__dict__.items():
        if not name.isupper():
            continue
        if not isinstance(value, int):
            continue
        code = int(value)
        name_to_code[name] = code
        previous = code_to_name.get(code)
        if previous is None or previous.startswith("MOD_"):
            code_to_name[code] = name

    _KEY_NAME_TO_CODE = name_to_code
    _CODE_TO_NAME = code_to_name
    return name_to_code, code_to_name


def key_name_to_code(
    key_name: str,
    *,
    warn: Callable[[str], None] | None = None,
    arcade_module=optional_arcade.arcade,
) -> int | None:
    """Convert a string name like 'SPACE' to an optional_arcade.arcade key code."""
    name_to_code, _ = _ensure_key_maps(arcade_module)
    cleaned = str(key_name or "").strip().upper()
    if not cleaned:
        return None
    code = name_to_code.get(cleaned)
    if code is None and warn is not None:
        warn(f"Unknown key name '{key_name}'")
    return code


def key_code_to_name(key_code: int, *, arcade_module=optional_arcade.arcade) -> str:
    """Convert a raw key code back into its canonical name."""
    _, code_to_name = _ensure_key_maps(arcade_module)
    return code_to_name.get(int(key_code), str(key_code))


def parse_bindings_config(
    bindings: dict[str, Iterable[str]] | None,
    *,
    warn: Callable[[str], None] | None = None,
    arcade_module=optional_arcade.arcade,
) -> dict[str, list[int]]:
    """
    Parse a config input_bindings map into InputManager-friendly codes.

    Unknown key names are ignored with an optional warning callback.
    """
    if not isinstance(bindings, dict):
        return {}

    parsed: dict[str, list[int]] = {}
    for action, names in bindings.items():
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, Iterable):
            continue
        codes: list[int] = []
        for name in names:
            code = key_name_to_code(name, warn=warn, arcade_module=arcade_module)
            if code is not None:
                codes.append(code)
        if codes:
            parsed[str(action)] = codes
    return parsed


def apply_config_bindings(
    manager: InputManager,
    bindings: dict[str, Iterable[str]] | None,
    *,
    warn: Callable[[str], None] | None = None,
    arcade_module=optional_arcade.arcade,
) -> bool:
    """Apply parsed bindings to the manager; return True if any applied."""
    parsed = parse_bindings_config(bindings, warn=warn, arcade_module=arcade_module)
    if not parsed:
        return False
    parsed_iter: dict[str, Iterable[int]] = {action: codes for action, codes in parsed.items()}
    manager.set_bindings(parsed_iter)
    return True


def snapshot_bindings(
    manager: InputManager,
    *,
    arcade_module=optional_arcade.arcade,
) -> dict[str, list[str]]:
    """Capture the current bindings as key names for persistence."""
    _, code_to_name = _ensure_key_maps(arcade_module)
    snapshot: dict[str, list[str]] = {}
    for action, codes in manager.get_bindings().items():
        snapshot[action] = [code_to_name.get(code, str(code)) for code in sorted(codes)]
    return snapshot


def known_actions(
    manager: InputManager | None,
    config_bindings: dict[str, Iterable[str]] | None,
    *,
    extra: Iterable[str] | None = None,
) -> Set[str]:
    """Return a superset of actions from defaults, config, runtime, and extras."""
    actions: Set[str] = set(DEFAULT_ACTIONS)
    if config_bindings:
        actions.update(config_bindings.keys())
    if manager is not None:
        actions.update(manager.get_bindings().keys())
    if extra:
        actions.update(extra)
    return actions
