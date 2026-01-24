"""Input hint helpers for UI surfaces."""

from __future__ import annotations

from typing import Iterable

_GAMEPAD_HINTS: dict[str, str] = {
    "interact": "A",
    "toggle_help": "B",
    "attack": "X",
    "show_inventory": "Y",
    "pause_menu": "Start",
}

_DEFAULT_KEYBOARD_HINTS: dict[str, str] = {
    "interact": "E",
    "attack": "Space",
    "pause_menu": "Esc",
    "toggle_help": "H",
    "show_inventory": "Tab",
}

_KEYBOARD_HINTS: dict[str, str] = {}


def _format_key_label(label: str) -> str:
    text = str(label or "").strip()
    if not text:
        return ""
    if text.isupper():
        return text.title()
    return text


def set_keyboard_hints(bindings: dict[str, Iterable[str]] | None) -> None:
    """Update keyboard hints from a bindings snapshot."""
    if not isinstance(bindings, dict):
        return
    for action, keys in bindings.items():
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, Iterable):
            continue
        for key in keys:
            label = _format_key_label(str(key))
            if label:
                _KEYBOARD_HINTS[str(action)] = label
                break


def get_action_hint(action: str, input_source: str) -> str:
    """Return a short hint label for the given action/source."""
    action = str(action or "")
    source = str(input_source or "").strip().lower()
    if source == "gamepad":
        return _GAMEPAD_HINTS.get(action, "")
    hint = _KEYBOARD_HINTS.get(action)
    if hint:
        return hint
    return _DEFAULT_KEYBOARD_HINTS.get(action, "")
