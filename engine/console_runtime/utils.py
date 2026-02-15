"""Shared stateless helpers for console command handlers."""

from __future__ import annotations

import difflib
import json
from typing import Any, Sequence


def parse_float(controller: Any, value: Any, label: str) -> float | None:
    """Parse a float from *value*, logging an error via *controller* on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        controller.log(f"Invalid {label}: {value}")
        return None


def parse_int(controller: Any, value: Any, label: str) -> int | None:
    """Parse an int (via float) from *value*, logging an error on failure."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        controller.log(f"Invalid {label}: {value}")
        return None


def format_scalar(value: Any, *, precision: int = 2) -> str:
    """Format a numeric *value* to a fixed-precision string."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    fmt = f"{{:.{precision}f}}"
    return fmt.format(number)


def normalize_tag_value(value: str) -> str | None:
    """Return *value* stripped, or ``None`` for sentinel strings."""
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "null", "nil"}:
        return None
    return cleaned


def format_param_value(value: Any) -> str:
    """Format a behaviour-parameter value for console display."""
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def param_kind_from_def(raw_type: Any) -> str:
    """Map a behaviour-parameter type annotation to a short kind label."""
    if raw_type in {int, "int"}:
        return "int"
    if raw_type in {float, "float"}:
        return "float"
    if raw_type in {bool, "bool"}:
        return "bool"
    if raw_type in {list, tuple, "array"}:
        return "array"
    if raw_type in {dict, "object"}:
        return "object"
    return "string"


def parse_value_for_kind(kind: str, raw_value: str) -> Any:
    """Coerce a raw console string into the appropriate Python value."""
    text = (raw_value or "").strip()
    if kind == "float":
        try:
            return float(text)
        except ValueError:
            return 0.0
    if kind == "int":
        try:
            return int(float(text))
        except ValueError:
            return 0
    if kind == "bool":
        lowered = text.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return bool(text)
    if kind == "array":
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        if "," in text:
            return [chunk.strip() for chunk in text.split(",") if chunk.strip()]
        return [text] if text else []
    if kind == "object":
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {"value": text} if text else {}
    return text


def suggest_param_name(target: str, candidates: Sequence[str]) -> str | None:
    """Return a close match for *target* among *candidates*, or ``None``."""
    pool = [name for name in candidates if isinstance(name, str) and name.strip()]
    if not target or not pool:
        return None
    lookup = {name.lower(): name for name in pool}
    matches = difflib.get_close_matches(target.lower(), lookup.keys(), n=1, cutoff=0.7)
    if matches:
        return lookup[matches[0]]
    return None


def entity_health_summary(behaviours: list[Any]) -> str | None:
    """Return a ``'cur/max'`` HP string from the first health-bearing behaviour."""
    for behaviour in behaviours:
        max_hp = getattr(behaviour, "max_health", None)
        current_hp = getattr(behaviour, "health", None)
        if max_hp is None and current_hp is None:
            continue
        safe_current = current_hp if current_hp is not None else max_hp
        if safe_current is None:
            continue
        try:
            cur = float(safe_current)
        except (TypeError, ValueError):
            cur = 0.0
        try:
            maximum = float(max_hp) if max_hp is not None else cur
        except (TypeError, ValueError):
            maximum = cur
        return f"{cur:.1f}/{maximum:.1f}"
    return None
