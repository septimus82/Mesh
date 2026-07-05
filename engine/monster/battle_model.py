"""Pure turn-based monster battle math.

No GameWindow, scene, save, event-bus, or Arcade dependencies belong here.
The functions in this module are deterministic for the same inputs and seeded
RNG object.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class BattleStats:
    hp: int
    atk: int
    defense: int
    spd: int
    sp_attack: int | None = None
    sp_defense: int | None = None

    def __post_init__(self) -> None:
        if self.sp_attack is None:
            object.__setattr__(self, "sp_attack", int(self.atk))
        if self.sp_defense is None:
            object.__setattr__(self, "sp_defense", int(self.defense))


@dataclass(frozen=True, slots=True)
class BattleSpriteClip:
    frames: tuple[int, ...]
    fps: float = 6.0
    loop: bool = True
    sheet: str | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    columns: int | None = None


@dataclass(frozen=True, slots=True)
class BattleSprite:
    sheet: str
    columns: int
    rows: int
    frame_width: int
    frame_height: int
    clips: dict[str, BattleSpriteClip]

    @property
    def idle_frames(self) -> tuple[int, ...]:
        return self.clips["idle"].frames

    @property
    def fps(self) -> float:
        return self.clips["idle"].fps


@dataclass(frozen=True, slots=True)
class Species:
    id: str
    base_stats: BattleStats
    types: tuple[str, ...]
    learnset: tuple[str, ...] = ()
    capture_rate: int = 150
    battle_sprite: BattleSprite | None = None


@dataclass(frozen=True, slots=True)
class MoveStatusInflict:
    condition: str
    chance: float


@dataclass(frozen=True, slots=True)
class Move:
    id: str
    type: str
    power: int
    accuracy: int
    pp: int
    status_inflict: MoveStatusInflict | None = None
    category: str = "physical"


@dataclass(frozen=True, slots=True)
class MonsterInstance:
    species: Species
    level: int
    current_hp: int | None = None
    known_moves: tuple[str, ...] = ()
    stats: BattleStats | None = None
    experience: int = 0
    status_condition: str | None = None
    status_turns: int = 0

    def __post_init__(self) -> None:
        level = max(1, int(self.level))
        stats = self.stats or derive_stats(self.species.base_stats, level)
        hp = stats.hp if self.current_hp is None else max(0, min(int(self.current_hp), stats.hp))
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "stats", stats)
        object.__setattr__(self, "current_hp", hp)
        object.__setattr__(self, "experience", max(0, int(self.experience)))
        object.__setattr__(self, "status_turns", max(0, int(self.status_turns)))

    @property
    def fainted(self) -> bool:
        return int(self.current_hp or 0) <= 0

    def with_current_hp(self, hp: int) -> "MonsterInstance":
        return replace(self, current_hp=max(0, min(int(hp), self.stats.hp if self.stats else int(hp))))


@dataclass(frozen=True, slots=True)
class MoveResolution:
    move_id: str
    damage: int
    type_multiplier: float
    hit: bool
    fainted: bool
    defender: MonsterInstance


class RandomLike(Protocol):
    def random(self) -> float:
        ...


TypeChart = Mapping[str, Mapping[str, float]]

DEFAULT_TYPE_CHART: dict[str, dict[str, float]] = {
    "fire": {"grass": 2.0, "water": 0.5},
    "grass": {"water": 2.0, "fire": 0.5},
    "water": {"fire": 2.0, "grass": 0.5},
}


def derive_stats(base: BattleStats, level: int) -> BattleStats:
    """Derive simple battle stats from base stats and level.

    Phase 0 keeps this intentionally small: HP grows by level and combat stats
    grow by half level. The formula is pure and can be replaced later without
    changing the battle-mode integration boundary.
    """

    level = max(1, int(level))
    half_level = level // 2
    return BattleStats(
        hp=max(1, int(base.hp) + level),
        atk=max(1, int(base.atk) + half_level),
        defense=max(1, int(base.defense) + half_level),
        spd=max(1, int(base.spd) + half_level),
        sp_attack=max(1, int(base.sp_attack) + half_level),
        sp_defense=max(1, int(base.sp_defense) + half_level),
    )


def type_multiplier(move_type: str, defender_types: Sequence[str], type_chart: TypeChart | None = None) -> float:
    """Return the combined type multiplier, defaulting missing entries to 1.0."""

    chart = type_chart or DEFAULT_TYPE_CHART
    attack_row = chart.get(str(move_type), {})
    multiplier = 1.0
    for defender_type in defender_types:
        multiplier *= float(attack_row.get(str(defender_type), 1.0))
    return multiplier


def compute_damage(
    *,
    level: int,
    attacker_atk: int,
    defender_def: int,
    move_power: int,
    type_mult: float,
    rng: RandomLike | None = None,
) -> int:
    """Compute deterministic turn damage.

    Formula:
        base = (((2 * level / 5 + 2) * power * atk / defense) / 50) + 2
        damage = floor(base * type_multiplier * variance)

    Variance is 1.0 when no RNG is supplied. When an RNG is supplied, variance
    is sampled from [0.85, 1.0] using only that injected RNG.
    """

    level = max(1, int(level))
    attack = max(1, int(attacker_atk))
    defense = max(1, int(defender_def))
    power = max(0, int(move_power))
    if power <= 0 or type_mult <= 0.0:
        return 0
    variance = 1.0
    if rng is not None:
        variance = 0.85 + (max(0.0, min(1.0, float(rng.random()))) * 0.15)
    base = ((((2 * level / 5 + 2) * power * attack / defense) / 50) + 2)
    return max(1, int(floor(base * float(type_mult) * variance)))


def resolve_move(
    attacker: MonsterInstance,
    defender: MonsterInstance,
    move: Move,
    type_chart: TypeChart | None = None,
    rng: RandomLike | None = None,
) -> MoveResolution:
    """Resolve one move and return a new defender state.

    The attacker is not mutated. The defender is not mutated either; callers get
    a returned copy whose HP is reduced and clamped to zero.
    """

    hit = _accuracy_hits(move.accuracy, rng)
    mult = type_multiplier(move.type, defender.species.types, type_chart)
    if not hit:
        updated = defender.with_current_hp(int(defender.current_hp or 0))
        return MoveResolution(move.id, 0, mult, False, updated.fainted, updated)

    damage = compute_damage(
        level=attacker.level,
        attacker_atk=_attacker_offense_stat(attacker, move),
        defender_def=_defender_defense_stat(defender, move),
        move_power=move.power,
        type_mult=mult,
        rng=rng,
    )
    updated = defender.with_current_hp(int(defender.current_hp or 0) - damage)
    return MoveResolution(move.id, damage, mult, True, updated.fainted, updated)


def _attacker_offense_stat(attacker: MonsterInstance, move: Move) -> int:
    stats = attacker.stats
    if stats is None:
        return 1
    if move.category == "special":
        return int(stats.sp_attack)
    return int(stats.atk)


def _defender_defense_stat(defender: MonsterInstance, move: Move) -> int:
    stats = defender.stats
    if stats is None:
        return 1
    if move.category == "special":
        return int(stats.sp_defense)
    return int(stats.defense)


def _accuracy_hits(accuracy: int, rng: RandomLike | None) -> bool:
    accuracy = max(0, min(100, int(accuracy)))
    if accuracy >= 100:
        return True
    if accuracy <= 0:
        return False
    if rng is None:
        return True
    return float(rng.random()) < (accuracy / 100.0)
