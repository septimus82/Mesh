from __future__ import annotations

from typing import Any


def _normalize_key(name: str) -> str:
    return str(name or "").strip()


def set_var(state: Any, name: str, value: Any) -> None:
    key = _normalize_key(name)
    if not key:
        return
    variables = getattr(state, "variables", None)
    if not isinstance(variables, dict):
        return
    variables[key] = value


def get_var(state: Any, name: str, default: Any = None) -> Any:
    key = _normalize_key(name)
    if not key:
        return default
    variables = getattr(state, "variables", None)
    if not isinstance(variables, dict):
        return default
    return variables.get(key, default)

