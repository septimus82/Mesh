from __future__ import annotations

from typing import Any


def _normalize_key(name: str) -> str:
    return str(name or "").strip()


def set_flag(state: Any, name: str, value: bool = True) -> None:
    key = _normalize_key(name)
    if not key:
        return
    flags = getattr(state, "flags", None)
    if not isinstance(flags, dict):
        return
    flags[key] = bool(value)


def get_flag(state: Any, name: str, default: bool = False) -> bool:
    key = _normalize_key(name)
    if not key:
        return bool(default)
    flags = getattr(state, "flags", None)
    if not isinstance(flags, dict):
        return bool(default)
    return bool(flags.get(key, default))


def toggle_flag(state: Any, name: str) -> bool:
    key = _normalize_key(name)
    if not key:
        return False
    flags = getattr(state, "flags", None)
    if not isinstance(flags, dict):
        return False
    new_value = not bool(flags.get(key, False))
    flags[key] = new_value
    return new_value

