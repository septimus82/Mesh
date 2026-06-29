from __future__ import annotations

import importlib
import random
from collections import Counter
from pathlib import Path

import pytest

from engine.monster.companion_mind import (
    ATTACK,
    BEHAVIOR_REGISTRY,
    DEFEND,
    HESITATE,
    BehaviorDefinition,
    CompanionMind,
    DecisionContext,
    LearnedWeights,
    Temperament,
    decide,
    score_behaviors,
)

pytestmark = pytest.mark.fast


def _mind(
    *,
    aggression: float = 50.0,
    fear: float = 10.0,
    learn_attack: float = 0.0,
    learn_defend: float = 0.0,
    learn_hesitate: float = 0.0,
) -> CompanionMind:
    return CompanionMind(
        temperament=Temperament(aggression=aggression, fear=fear),
        learned=LearnedWeights(
            ATTACK=learn_attack,
            DEFEND=learn_defend,
            HESITATE=learn_hesitate,
        ),
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

    first = decide(mind, ctx, random.Random(12345))
    second = decide(mind, ctx, random.Random(12345))

    assert first.behavior_id == second.behavior_id
    assert dict(first.scores) == dict(second.scores)


def test_decide_returns_scores_for_every_available_behavior() -> None:
    mind = _mind(aggression=40.0, fear=15.0, learn_attack=3.0, learn_defend=2.0, learn_hesitate=1.0)
    ctx = DecisionContext()

    result = decide(mind, ctx, random.Random(0))

    assert set(result.scores.keys()) == {ATTACK, DEFEND, HESITATE}
    assert result.scores[ATTACK] == pytest.approx(40.0 * 0.7 + 3.0)
    assert result.scores[DEFEND] == pytest.approx(15.0 * 0.4 + 20.0 + 2.0)
    assert result.scores[HESITATE] == pytest.approx(15.0 * 0.5 + 1.0)


def test_higher_aggression_shifts_distribution_toward_attack() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=10.0, fear=10.0), ctx, random.Random(seed)).behavior_id for seed in range(500)
    )
    aggressive = Counter(
        decide(_mind(aggression=100.0, fear=10.0), ctx, random.Random(seed)).behavior_id for seed in range(500)
    )

    baseline_attack_rate = baseline[ATTACK] / sum(baseline.values())
    aggressive_attack_rate = aggressive[ATTACK] / sum(aggressive.values())
    assert aggressive_attack_rate > baseline_attack_rate + 0.15


def test_higher_learned_defend_shifts_distribution_toward_defend() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=50.0, fear=10.0), ctx, random.Random(seed)).behavior_id for seed in range(500)
    )
    defensive = Counter(
        decide(_mind(aggression=50.0, fear=10.0, learn_defend=80.0), ctx, random.Random(seed)).behavior_id
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
    choices = {decide(mind, ctx, random.Random(seed)).behavior_id for seed in range(200)}

    assert len(choices) >= 2
    assert top in choices
    assert any(choice != top for choice in choices)


def test_only_available_behaviors_can_be_chosen() -> None:
    blocked = BehaviorDefinition("HEAL", lambda _mind, _ctx: False, lambda _mind, _ctx: 999.0)
    registry = (*BEHAVIOR_REGISTRY, blocked)
    mind = _mind()
    ctx = DecisionContext()

    for seed in range(100):
        result = decide(mind, ctx, random.Random(seed), registry=registry)
        assert result.behavior_id != "HEAL"
        assert "HEAL" not in result.scores
        assert set(result.scores.keys()) == {ATTACK, DEFEND, HESITATE}
