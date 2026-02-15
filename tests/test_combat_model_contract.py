from __future__ import annotations

from engine.combat_constants import (
    EVENT_COMBAT_DAMAGE,
    EVENT_COMBAT_DEATH,
    EVENT_COMBAT_HIT,
    EVENT_COMBAT_MISS,
)
from engine.combat_model import AttackSpec, TargetState, resolve_attack


class _FixedRng:
    def __init__(self, value: float) -> None:
        self._value = float(value)

    def random(self, _stream: str = "") -> float:
        return self._value


def _attack_spec(*, damage: float, crit_chance: float = 0.0) -> AttackSpec:
    return AttackSpec(
        source_id="enemy_archer",
        target_id="player",
        base_damage=damage,
        crit_chance=crit_chance,
        rng_stream="combat.tests",
        tags=("ranged",),
    )


def test_resolve_attack_is_deterministic_for_fixed_inputs() -> None:
    state = TargetState(hp=12.0, max_hp=12.0)
    spec = _attack_spec(damage=3.5, crit_chance=0.25)

    run_a = resolve_attack(spec, state, rng=_FixedRng(0.8))
    run_b = resolve_attack(spec, state, rng=_FixedRng(0.8))
    assert run_a == run_b
    assert run_a[0].hp == 8.5
    assert run_a[1].events_emitted == (EVENT_COMBAT_HIT, EVENT_COMBAT_DAMAGE)


def test_crit_boundaries_and_damage_rounding() -> None:
    state = TargetState(hp=10.0, max_hp=10.0)

    no_crit_state, no_crit_result = resolve_attack(
        _attack_spec(damage=2.0, crit_chance=0.0),
        state,
        rng=_FixedRng(0.0),
    )
    assert no_crit_result.was_crit is False
    assert no_crit_result.applied_damage == 2.0
    assert no_crit_state.hp == 8.0

    crit_state, crit_result = resolve_attack(
        _attack_spec(damage=2.0, crit_chance=1.0),
        state,
        rng=_FixedRng(0.99),
    )
    assert crit_result.was_crit is True
    assert crit_result.applied_damage == 4.0
    assert crit_state.hp == 6.0


def test_clamping_and_death_transition() -> None:
    start = TargetState(hp=3.0, max_hp=5.0, dead=False, invulnerable=False)
    next_state, result = resolve_attack(_attack_spec(damage=10.0), start, rng=None)

    assert next_state.hp == 0.0
    assert next_state.dead is True
    assert result.applied_damage == 3.0
    assert result.target_dead is True
    assert result.events_emitted == (EVENT_COMBAT_HIT, EVENT_COMBAT_DAMAGE, EVENT_COMBAT_DEATH)


def test_invulnerable_target_resolves_to_miss_without_hp_change() -> None:
    start = TargetState(hp=4.0, max_hp=5.0, dead=False, invulnerable=True)
    next_state, result = resolve_attack(_attack_spec(damage=2.0), start, rng=_FixedRng(0.0))

    assert next_state == start
    assert result.applied_damage == 0.0
    assert result.was_crit is False
    assert result.events_emitted == (EVENT_COMBAT_MISS,)

