"""Pure monster capture math."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .battle_model import MonsterInstance


class RandomLike(Protocol):
    def random(self) -> float:
        ...


@dataclass(frozen=True, slots=True)
class CaptureResult:
    caught: bool
    roll: float
    chance: float
    capture_rate: int
    hp_fraction: float
    ball_bonus: float
    status_bonus: float = 1.0


def resolve_capture(
    wild: MonsterInstance,
    ball_bonus: float,
    rng: RandomLike,
    *,
    status_bonus: float = 1.0,
) -> CaptureResult:
    """Resolve one capture attempt from species rate, HP fraction, ball, and RNG."""

    capture_rate = max(1, min(255, int(getattr(wild.species, "capture_rate", 150))))
    max_hp = max(1, int(wild.stats.hp if wild.stats is not None else wild.current_hp or 1))
    current_hp = max(0, min(max_hp, int(wild.current_hp or 0)))
    hp_fraction = current_hp / max_hp
    hp_bonus = 1.0 + ((1.0 - hp_fraction) * 1.5)
    chance = (capture_rate / 255.0) * max(0.0, float(ball_bonus)) * max(0.0, float(status_bonus)) * hp_bonus
    chance = max(0.0, min(0.95, chance))
    roll = max(0.0, min(0.999999, float(rng.random())))
    return CaptureResult(
        caught=roll < chance,
        roll=roll,
        chance=chance,
        capture_rate=capture_rate,
        hp_fraction=hp_fraction,
        ball_bonus=float(ball_bonus),
        status_bonus=float(status_bonus),
    )
