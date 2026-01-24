from __future__ import annotations

from typing import Any


def normalize_event_name(name: str) -> str:
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ValueError("event name must be a non-empty string")
    return cleaned


def normalize_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise TypeError(f"payload must be a dict, got {type(payload).__name__}")
    return dict(payload)

