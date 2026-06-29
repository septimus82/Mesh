"""Pure monster XP, level, and learnset progression."""

from __future__ import annotations

from dataclasses import dataclass

from .battle_model import MonsterInstance, derive_stats


@dataclass(frozen=True, slots=True)
class ExperienceResult:
    instance: MonsterInstance
    xp_gained: int
    previous_level: int
    levels_gained: int
    moves_learned: tuple[str, ...] = ()


def xp_required_for_level(level: int) -> int:
    """Return total XP required to be at ``level``."""

    level = max(1, int(level))
    return 10 * (level - 1) * level


def level_for_experience(experience: int) -> int:
    total = max(0, int(experience))
    level = 1
    while xp_required_for_level(level + 1) <= total:
        level += 1
    return level


def award_xp_for_victory(opponent: MonsterInstance) -> int:
    """Phase-0 deterministic victory XP from opponent level and species."""

    capture_rate = max(1, int(getattr(opponent.species, "capture_rate", 150)))
    return max(1, (max(1, int(opponent.level)) * 20) + (capture_rate // 10))


def apply_experience(instance: MonsterInstance, xp: int) -> ExperienceResult:
    """Apply XP and return a new instance with level, stats, HP, and moves updated."""

    gained = max(0, int(xp))
    previous_level = max(1, int(instance.level))
    base_experience = max(int(instance.experience), xp_required_for_level(previous_level))
    total_experience = base_experience + gained
    new_level = max(previous_level, level_for_experience(total_experience))
    levels_gained = max(0, new_level - previous_level)
    known_moves = list(instance.known_moves)
    learned: list[str] = []
    for _ in range(levels_gained):
        for move_id in instance.species.learnset:
            if move_id not in known_moves:
                known_moves.append(move_id)
                learned.append(move_id)
                break

    old_hp = int(instance.current_hp or 0)
    old_max_hp = int(instance.stats.hp if instance.stats is not None else old_hp)
    new_stats = derive_stats(instance.species.base_stats, new_level)
    hp_gain = max(0, new_stats.hp - old_max_hp)
    updated = MonsterInstance(
        instance.species,
        level=new_level,
        current_hp=min(new_stats.hp, old_hp + hp_gain),
        known_moves=tuple(known_moves),
        experience=total_experience,
    )
    return ExperienceResult(
        instance=updated,
        xp_gained=gained,
        previous_level=previous_level,
        levels_gained=levels_gained,
        moves_learned=tuple(learned),
    )
