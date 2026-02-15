"""Deterministic, pure combat damage resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.combat_constants import (
    EVENT_COMBAT_DAMAGE,
    EVENT_COMBAT_DEATH,
    EVENT_COMBAT_HIT,
    EVENT_COMBAT_MISS,
)

ROUND_DIGITS = 6
CRIT_MULTIPLIER = 2.0


@dataclass(frozen=True, slots=True)
class AttackSpec:
    source_id: str
    target_id: str
    base_damage: float
    crit_chance: float
    rng_stream: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TargetState:
    hp: float
    max_hp: float
    dead: bool = False
    invulnerable: bool = False


@dataclass(frozen=True, slots=True)
class DamageResult:
    applied_damage: float
    was_crit: bool
    target_dead: bool
    events_emitted: tuple[str, ...]


def resolve_attack(
    spec: AttackSpec,
    target_state: TargetState,
    rng: Any | None = None,
) -> tuple[TargetState, DamageResult]:
    """Resolve one attack into deterministic HP and event outcomes."""
    hp = _round(max(0.0, min(float(target_state.hp), float(target_state.max_hp))))
    max_hp = _round(max(0.0, float(target_state.max_hp)))
    dead = bool(target_state.dead or hp <= 0.0)
    invulnerable = bool(target_state.invulnerable)

    if dead or invulnerable:
        result = DamageResult(
            applied_damage=0.0,
            was_crit=False,
            target_dead=dead,
            events_emitted=(EVENT_COMBAT_MISS,),
        )
        return TargetState(hp=hp, max_hp=max_hp, dead=dead, invulnerable=invulnerable), result

    raw_damage = _round(max(0.0, float(spec.base_damage)))
    was_crit = raw_damage > 0.0 and _roll_crit(spec, rng)
    adjusted_damage = _round(raw_damage * (CRIT_MULTIPLIER if was_crit else 1.0))
    applied_damage = _round(min(hp, adjusted_damage))
    remaining_hp = _round(max(0.0, hp - applied_damage))
    target_dead = remaining_hp <= 0.0

    events: list[str] = []
    if applied_damage > 0.0:
        events.append(EVENT_COMBAT_HIT)
        events.append(EVENT_COMBAT_DAMAGE)
        if target_dead:
            events.append(EVENT_COMBAT_DEATH)
    else:
        events.append(EVENT_COMBAT_MISS)

    result = DamageResult(
        applied_damage=applied_damage,
        was_crit=was_crit,
        target_dead=target_dead,
        events_emitted=tuple(events),
    )
    new_state = TargetState(
        hp=remaining_hp,
        max_hp=max_hp,
        dead=target_dead,
        invulnerable=invulnerable,
    )
    return new_state, result


def _roll_crit(spec: AttackSpec, rng: Any | None) -> bool:
    chance = min(1.0, max(0.0, float(spec.crit_chance)))
    if chance <= 0.0:
        return False
    if chance >= 1.0:
        return True
    if rng is None:
        return False

    value: float
    random_fn = getattr(rng, "random", None)
    if not callable(random_fn):
        return False
    try:
        value = float(random_fn(spec.rng_stream))
    except TypeError:
        try:
            value = float(random_fn())
        except Exception:
            return False
    except Exception:
        return False
    return value < chance


def _round(value: float) -> float:
    return round(float(value), ROUND_DIGITS)

