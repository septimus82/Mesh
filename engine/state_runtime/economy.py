from __future__ import annotations

from typing import Any


def _normalize_key(name: str) -> str:
    return str(name or "").strip()


def set_counter(state: Any, name: str, value: float = 0.0) -> float:
    key = _normalize_key(name)
    if not key:
        return 0.0
    counters = getattr(state, "counters", None)
    if not isinstance(counters, dict):
        return 0.0
    coerced = float(value)
    counters[key] = coerced
    return coerced


def add_counter(state: Any, name: str, delta: float = 1.0, *, perk_manager: Any = None) -> float:
    key = _normalize_key(name)
    if not key:
        return 0.0
    counters = getattr(state, "counters", None)
    if not isinstance(counters, dict):
        return 0.0

    # Apply perk gold bonus
    final_delta = float(delta)
    if key == "gold" and final_delta > 0:
        bonus_pct = 0.0
        perks = getattr(state, "perks", None)
        if isinstance(perks, list) and perk_manager is not None:
            get_perk = getattr(perk_manager, "get_perk", None)
            if callable(get_perk):
                for perk_id in perks:
                    perk = get_perk(perk_id)
                    if perk:
                        bonus_pct += perk.effects.get("gold_bonus_pct", 0.0)
        final_delta *= (1.0 + bonus_pct)

    current = float(counters.get(key, 0.0) or 0.0)
    current += final_delta
    counters[key] = current
    return current


def get_counter(state: Any, name: str, default: float = 0.0) -> float:
    key = _normalize_key(name)
    if not key:
        return float(default)
    counters = getattr(state, "counters", None)
    if not isinstance(counters, dict):
        return float(default)
    value = counters.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def add_gold(state: Any, amount: float, *, perk_manager: Any = None) -> float:
    return add_counter(state, "gold", amount, perk_manager=perk_manager)


def get_gold(state: Any, default: float = 0.0) -> float:
    return get_counter(state, "gold", default)

