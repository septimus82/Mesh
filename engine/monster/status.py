"""Pure battle-scoped status effect logic."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .battle_model import MonsterInstance, RandomLike

StatusKind = Literal["poison", "sleep"]
StatusEventKind = Literal["poisoned", "poison_damage", "fell_asleep", "woke_up", "asleep_skip"]

POISON = "poison"
SLEEP = "sleep"
KNOWN_STATUS_CONDITIONS = frozenset({POISON, SLEEP})
SLEEP_DURATION = 3
POISON_DAMAGE_DIVISOR = 8


@dataclass(frozen=True, slots=True)
class StatusCondition:
    condition: StatusKind
    turns_remaining: int = 0


@dataclass(frozen=True, slots=True)
class StatusEvent:
    kind: StatusEventKind
    damage: int = 0


def apply_status(instance: MonsterInstance, condition: str) -> MonsterInstance:
    """Apply a battle-scoped status condition to an instance."""

    if condition == POISON:
        return replace(instance, status_condition=POISON, status_turns=0)
    if condition == SLEEP:
        if instance.status_condition == SLEEP and instance.status_turns > 0:
            return instance
        return replace(instance, status_condition=SLEEP, status_turns=SLEEP_DURATION)
    raise ValueError(f"Unknown status condition '{condition}'")


def can_act(instance: MonsterInstance, rng: RandomLike | None = None) -> tuple[bool, tuple[StatusEvent, ...], MonsterInstance]:
    """Return whether the instance may act, wake/skip events, and the updated instance."""

    if instance.status_condition != SLEEP or instance.status_turns <= 0:
        return True, (), instance

    if rng is not None and instance.status_turns == 1 and float(rng.random()) < 0.5:
        updated = replace(instance, status_condition=None, status_turns=0)
        return True, (StatusEvent("woke_up"),), updated

    return False, (StatusEvent("asleep_skip"),), instance


def tick_end_of_turn(instance: MonsterInstance) -> tuple[MonsterInstance, tuple[StatusEvent, ...]]:
    """Apply end-of-turn status ticks such as poison damage and sleep countdown."""

    events: list[StatusEvent] = []
    updated = instance

    if updated.status_condition == POISON:
        max_hp = int(updated.stats.hp if updated.stats is not None else updated.current_hp or 1)
        damage = max(1, max_hp // POISON_DAMAGE_DIVISOR)
        updated = updated.with_current_hp(int(updated.current_hp or 0) - damage)
        events.append(StatusEvent("poison_damage", damage))

    if updated.status_condition == SLEEP and updated.status_turns > 0:
        remaining = int(updated.status_turns) - 1
        if remaining <= 0:
            updated = replace(updated, status_condition=None, status_turns=0)
            events.append(StatusEvent("woke_up"))
        else:
            updated = replace(updated, status_turns=remaining)

    return updated, tuple(events)


def inflict_event_for(condition: str) -> StatusEventKind:
    if condition == POISON:
        return "poisoned"
    if condition == SLEEP:
        return "fell_asleep"
    raise ValueError(f"Unknown status condition '{condition}'")
