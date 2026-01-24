from __future__ import annotations

from typing import Any, Mapping

ELITE_COST_MULT = 2.0
MINI_BOSS_COST_MULT = 3.0
BOSS_COST_MULT = 4.0


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _iter_tags(payload: Mapping[str, Any]) -> list[str]:
    tags = payload.get("tags")
    if isinstance(tags, (list, tuple, set)):
        out: list[str] = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip():
                out.append(tag.strip())
        return out
    return []


def is_boss_payload(payload: Mapping[str, Any] | None) -> bool:
    payload = _as_mapping(payload)
    if payload is None:
        return False
    if bool(payload.get("is_boss")):
        return True
    for tag in _iter_tags(payload):
        if tag.lower() == "boss":
            return True
    inner = _as_mapping(payload.get("entity"))
    return is_boss_payload(inner) if inner is not None else False


def is_elite_payload(payload: Mapping[str, Any] | None) -> bool:
    payload = _as_mapping(payload)
    if payload is None:
        return False
    if bool(payload.get("is_elite")):
        return True
    for tag in _iter_tags(payload):
        if tag.lower() == "elite":
            return True
    inner = _as_mapping(payload.get("entity"))
    return is_elite_payload(inner) if inner is not None else False


def is_mini_boss_payload(payload: Mapping[str, Any] | None) -> bool:
    payload = _as_mapping(payload)
    if payload is None:
        return False
    if bool(payload.get("is_mini_boss")):
        return True
    for tag in _iter_tags(payload):
        if tag.lower() == "mini_boss":
            return True
    inner = _as_mapping(payload.get("entity"))
    return is_mini_boss_payload(inner) if inner is not None else False


def get_base_encounter_cost(payload: Mapping[str, Any] | None, default: float | None = 1.0) -> float | None:
    payload = _as_mapping(payload)
    if payload is None:
        return float(default) if default is not None else None

    raw = payload.get("encounter_cost")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default) if default is not None else None

    inner = _as_mapping(payload.get("entity"))
    if inner is not None:
        return get_base_encounter_cost(inner, default=default)

    return float(default) if default is not None else None


def get_effective_encounter_cost(payload: Mapping[str, Any] | None, default: float = 1.0) -> float:
    base = get_base_encounter_cost(payload, default=default)
    if base is None:
        base = float(default)
    if is_boss_payload(payload):
        return base * BOSS_COST_MULT
    if is_mini_boss_payload(payload):
        return base * MINI_BOSS_COST_MULT
    if is_elite_payload(payload):
        return base * ELITE_COST_MULT
    return base
