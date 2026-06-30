from __future__ import annotations

import importlib
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from engine.monster.companion_mind import (
    ATTACK,
    BEHAVIOR_REGISTRY,
    DEFEND,
    FLEE,
    HESITATE,
    BehaviorDefinition,
    CompanionMind,
    DecisionContext,
    LearnedWeights,
    Temperament,
    companion_mind_from_dict,
    companion_mind_to_dict,
    decide,
    praise,
    scold,
    score_behaviors,
    wait,
)

pytestmark = pytest.mark.fast


def _mind(
    *,
    aggression: float = 50.0,
    fear: float = 10.0,
    learn_attack: float = 0.0,
    learn_defend: float = 0.0,
    learn_hesitate: float = 0.0,
    trust: float = 50.0,
    bond: float = 0.0,
    last_behavior: str | None = None,
) -> CompanionMind:
    return CompanionMind(
        temperament=Temperament(aggression=aggression, fear=fear),
        learned=LearnedWeights(
            ATTACK=learn_attack,
            DEFEND=learn_defend,
            HESITATE=learn_hesitate,
        ),
        trust=trust,
        bond=bond,
        last_behavior=last_behavior,
    )


def test_module_is_pure_without_runtime_imports() -> None:
    module = importlib.import_module("engine.monster.companion_mind")
    assert module.__name__ == "engine.monster.companion_mind"
    assert not hasattr(module, "GameWindow")
    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden = (
        "optional_arcade",
        "GameWindow",
        "battle_controller",
        "battle_mode",
        "import random",
        "from random import",
    )
    for token in forbidden:
        assert token not in source


def test_decide_is_deterministic_under_fixed_seed() -> None:
    mind = _mind()
    ctx = DecisionContext()

    _, first = decide(mind, ctx, random.Random(12345))
    _, second = decide(mind, ctx, random.Random(12345))

    assert first.behavior_id == second.behavior_id
    assert dict(first.scores) == dict(second.scores)


def test_decide_records_last_behavior_on_returned_mind() -> None:
    mind = _mind()
    ctx = DecisionContext()

    updated, result = decide(mind, ctx, random.Random(7))

    assert updated.last_behavior == result.behavior_id
    assert mind.last_behavior is None


def test_decide_returns_scores_for_every_available_behavior() -> None:
    mind = _mind(aggression=40.0, fear=15.0, learn_attack=3.0, learn_defend=2.0, learn_hesitate=1.0, trust=50.0)
    ctx = DecisionContext()

    _, result = decide(mind, ctx, random.Random(0))

    assert set(result.scores.keys()) == {ATTACK, DEFEND, HESITATE}
    assert result.scores[ATTACK] == pytest.approx(40.0 * 0.7 + 3.0)
    assert result.scores[DEFEND] == pytest.approx(15.0 * 0.4 + 20.0 + 2.0)
    assert result.scores[HESITATE] == pytest.approx(15.0 * 0.5 + (100.0 - 50.0) * 0.4 + 1.0)


def test_higher_aggression_shifts_distribution_toward_attack() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=10.0, fear=10.0), ctx, random.Random(seed))[1].behavior_id for seed in range(500)
    )
    aggressive = Counter(
        decide(_mind(aggression=100.0, fear=10.0), ctx, random.Random(seed))[1].behavior_id for seed in range(500)
    )

    baseline_attack_rate = baseline[ATTACK] / sum(baseline.values())
    aggressive_attack_rate = aggressive[ATTACK] / sum(aggressive.values())
    assert aggressive_attack_rate > baseline_attack_rate + 0.15


def test_higher_learned_defend_shifts_distribution_toward_defend() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=50.0, fear=10.0), ctx, random.Random(seed))[1].behavior_id for seed in range(500)
    )
    defensive = Counter(
        decide(_mind(aggression=50.0, fear=10.0, learn_defend=80.0), ctx, random.Random(seed))[1].behavior_id
        for seed in range(500)
    )

    baseline_defend_rate = baseline[DEFEND] / sum(baseline.values())
    defensive_defend_rate = defensive[DEFEND] / sum(defensive.values())
    assert defensive_defend_rate > baseline_defend_rate + 0.15


def test_selection_is_weighted_random_not_argmax() -> None:
    mind = _mind(aggression=30.0, fear=10.0)
    ctx = DecisionContext()
    scores = score_behaviors(mind, ctx)
    top = max(scores, key=scores.get)
    choices = {decide(mind, ctx, random.Random(seed))[1].behavior_id for seed in range(200)}

    assert len(choices) >= 2
    assert top in choices
    assert any(choice != top for choice in choices)


def test_only_available_behaviors_can_be_chosen() -> None:
    blocked = BehaviorDefinition("HEAL", lambda _mind, _ctx: False, lambda _mind, _ctx: 999.0)
    registry = (*BEHAVIOR_REGISTRY, blocked)
    mind = _mind()
    ctx = DecisionContext()

    for seed in range(100):
        _, result = decide(mind, ctx, random.Random(seed), registry=registry)
        assert result.behavior_id != "HEAL"
        assert "HEAL" not in result.scores
        assert set(result.scores.keys()) == {ATTACK, DEFEND, HESITATE}


def test_praise_after_attack_raises_learned_attack_and_attack_likelihood() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=20.0, fear=10.0, trust=50.0), ctx, random.Random(seed))[1].behavior_id
        for seed in range(400)
    )
    mind, _ = decide(_mind(aggression=20.0, fear=10.0, trust=50.0), ctx, random.Random(0))
    mind = replace(mind, last_behavior=ATTACK)
    praised = praise(mind)
    assert praised.learned.ATTACK > 0.0

    reinforced = Counter(decide(praised, ctx, random.Random(seed))[1].behavior_id for seed in range(400))
    assert reinforced[ATTACK] / sum(reinforced.values()) > baseline[ATTACK] / sum(baseline.values()) + 0.05


def test_scold_after_attack_lowers_learned_attack_trust_and_raises_fear() -> None:
    mind = _mind(trust=60.0, fear=10.0, last_behavior=ATTACK, learn_attack=10.0)

    scolded = scold(mind)

    assert scolded.learned.ATTACK < mind.learned.ATTACK
    assert scolded.trust < mind.trust
    assert scolded.temperament.fear > mind.temperament.fear


def test_low_trust_raises_hesitate_score_and_share() -> None:
    ctx = DecisionContext()
    high_trust = _mind(trust=90.0, aggression=10.0, fear=10.0)
    low_trust = _mind(trust=10.0, aggression=10.0, fear=10.0)

    assert score_behaviors(low_trust, ctx)[HESITATE] > score_behaviors(high_trust, ctx)[HESITATE]

    high_counts = Counter(decide(high_trust, ctx, random.Random(seed))[1].behavior_id for seed in range(400))
    low_counts = Counter(decide(low_trust, ctx, random.Random(seed))[1].behavior_id for seed in range(400))
    assert low_counts[HESITATE] / sum(low_counts.values()) > high_counts[HESITATE] / sum(high_counts.values()) + 0.05


def test_praise_trust_gain_is_slower_than_scold_trust_loss() -> None:
    ctx = DecisionContext()
    mind, _ = decide(_mind(trust=50.0), ctx, random.Random(1))
    praised = praise(mind)
    praise_gain = praised.trust - 50.0

    mind2, _ = decide(_mind(trust=50.0), ctx, random.Random(1))
    scolded = scold(mind2)
    scold_loss = 50.0 - scolded.trust

    assert praise_gain > 0.0
    assert scold_loss > praise_gain


def test_equal_praise_and_scold_counts_leave_net_negative_trust() -> None:
    ctx = DecisionContext()
    mind = _mind(trust=50.0)
    for seed in range(10):
        mind, _ = decide(mind, ctx, random.Random(seed))
        mind = praise(mind)
    for seed in range(100, 110):
        mind, _ = decide(mind, ctx, random.Random(seed))
        mind = scold(mind)

    assert mind.trust < 50.0


def test_bond_rises_slowly_under_repeated_praise() -> None:
    ctx = DecisionContext()
    mind = _mind(bond=0.0, trust=50.0)
    for seed in range(20):
        mind, _ = decide(mind, ctx, random.Random(seed))
        mind = praise(mind)

    assert mind.bond > 0.0
    assert mind.bond <= 20.0


def test_companion_mind_serialize_round_trip_matches_exactly() -> None:
    mind = _mind(
        aggression=61.0,
        fear=22.5,
        learn_attack=3.5,
        learn_defend=-1.0,
        learn_hesitate=2.0,
        trust=63.0,
        bond=9.5,
        last_behavior=HESITATE,
    )

    restored = companion_mind_from_dict(companion_mind_to_dict(mind))

    assert restored == mind


def test_flee_excluded_from_pool_when_trust_and_bond_are_high_at_low_hp() -> None:
    mind = _mind(trust=95.0, bond=90.0, fear=80.0)
    ctx = DecisionContext(hp_fraction=0.1)

    scores = score_behaviors(mind, ctx)

    assert FLEE not in scores
    assert set(scores.keys()) == {ATTACK, DEFEND, HESITATE}


def test_flee_included_for_neglected_companion_at_low_hp() -> None:
    mind = _mind(trust=8.0, bond=4.0, fear=75.0)
    ctx = DecisionContext(hp_fraction=0.1)

    scores = score_behaviors(mind, ctx)

    assert FLEE in scores


def test_reinforcement_clamps_trust_bond_and_fear() -> None:
    mind = _mind(trust=98.0, bond=98.0, fear=98.0, last_behavior=ATTACK)
    for _ in range(20):
        mind = praise(mind)
    assert mind.trust == 100.0
    assert mind.bond == 100.0

    for _ in range(20):
        mind = scold(mind)
    assert mind.trust == 0.0
    assert mind.temperament.fear == 100.0

    mind = wait(mind)
    assert mind.bond == 100.0
