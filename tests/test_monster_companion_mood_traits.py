from __future__ import annotations

import random
from collections import Counter
from dataclasses import replace

import pytest

from engine.monster.companion_mind import (
    ATTACK,
    BRAVE,
    FLEE,
    HESITATE,
    LOYAL,
    MOOD_DECAY,
    MOOD_STEP,
    QUICK_LEARNER,
    TIMID,
    TRAIT_REGISTRY,
    CompanionMind,
    DecisionContext,
    LearnedWeights,
    Temperament,
    apply_battle_flee,
    apply_battle_loss,
    apply_battle_win,
    companion_mind_from_dict,
    companion_mind_to_dict,
    decay_mood,
    decide,
    mood_learn_factor,
    praise,
    roll_traits,
    scold,
    score_behaviors,
)

pytestmark = pytest.mark.fast


def _mind(
    *,
    aggression: float = 50.0,
    fear: float = 10.0,
    learn_attack: float = 0.0,
    trust: float = 50.0,
    bond: float = 0.0,
    mood: float = 0.0,
    traits: tuple[str, ...] = (),
    last_behavior: str | None = None,
) -> CompanionMind:
    return CompanionMind(
        temperament=Temperament(aggression=aggression, fear=fear),
        learned=LearnedWeights(ATTACK=learn_attack),
        trust=trust,
        bond=bond,
        mood=mood,
        traits=traits,
        last_behavior=last_behavior,
    )


def test_praise_and_scold_swing_mood() -> None:
    mind = _mind(last_behavior=ATTACK)
    praised = praise(mind)
    assert praised.mood == pytest.approx(MOOD_STEP)

    scolded = scold(replace(praised, last_behavior=ATTACK))
    assert scolded.mood == pytest.approx(0.0)


def test_battle_outcomes_swing_mood() -> None:
    mind = _mind()
    won = apply_battle_win(mind)
    lost = apply_battle_loss(won)
    fled = apply_battle_flee(lost)
    assert won.mood > 0.0
    assert lost.mood < won.mood
    assert fled.mood < lost.mood


def test_mood_decays_toward_zero_on_tick() -> None:
    positive = decay_mood(_mind(mood=40.0))
    assert positive.mood == pytest.approx(40.0 - MOOD_DECAY)

    negative = decay_mood(_mind(mood=-30.0))
    assert negative.mood == pytest.approx(-30.0 + MOOD_DECAY)

    neutral = decay_mood(_mind(mood=0.0))
    assert neutral.mood == 0.0


def test_decide_applies_mood_decay_each_tick() -> None:
    mind = _mind(mood=20.0)
    updated, _ = decide(mind, DecisionContext(), random.Random(1))
    assert updated.mood == pytest.approx(20.0 - MOOD_DECAY)


def test_high_mood_biases_attack_low_mood_biases_hesitate() -> None:
    ctx = DecisionContext()
    neutral = Counter(
        decide(_mind(aggression=20.0, fear=10.0), ctx, random.Random(seed))[1].behavior_id for seed in range(500)
    )
    happy = Counter(
        decide(_mind(aggression=20.0, fear=10.0, mood=85.0), ctx, random.Random(seed))[1].behavior_id
        for seed in range(500)
    )
    sad = Counter(
        decide(_mind(aggression=20.0, fear=10.0, mood=-85.0), ctx, random.Random(seed))[1].behavior_id
        for seed in range(500)
    )

    assert happy[ATTACK] / sum(happy.values()) > neutral[ATTACK] / sum(neutral.values()) + 0.05
    assert sad[HESITATE] / sum(sad.values()) > neutral[HESITATE] / sum(neutral.values()) + 0.05


def test_mood_amplifies_learning_at_extremes() -> None:
    base = praise(replace(_mind(last_behavior=ATTACK), mood=0.0))
    high = praise(replace(_mind(last_behavior=ATTACK), mood=100.0))
    low = praise(replace(_mind(last_behavior=ATTACK), mood=-100.0))

    assert mood_learn_factor(100.0) == pytest.approx(1.2)
    assert mood_learn_factor(-100.0) == pytest.approx(0.8)
    assert high.learned.ATTACK > base.learned.ATTACK
    assert low.learned.ATTACK < base.learned.ATTACK


def test_roll_traits_is_deterministic_and_non_conflicting() -> None:
    first = roll_traits(random.Random(4242))
    second = roll_traits(random.Random(4242))
    assert first == second
    assert 1 <= len(first) <= 2
    assert len(first) == len(set(first))
    for left in first:
        for right in first:
            if left == right:
                continue
            assert right not in TRAIT_REGISTRY[left].conflicts
            assert left not in TRAIT_REGISTRY[right].conflicts


def test_roll_traits_can_produce_two_traits_for_some_seeds() -> None:
    counts = {len(roll_traits(random.Random(seed))) for seed in range(200)}
    assert 1 in counts
    assert 2 in counts


def test_brave_trait_biases_attack() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=20.0, fear=10.0), ctx, random.Random(seed))[1].behavior_id for seed in range(500)
    )
    brave = Counter(
        decide(_mind(aggression=20.0, fear=10.0, traits=(BRAVE,)), ctx, random.Random(seed))[1].behavior_id
        for seed in range(500)
    )
    assert brave[ATTACK] / sum(brave.values()) > baseline[ATTACK] / sum(baseline.values()) + 0.08


def test_timid_trait_biases_hesitate() -> None:
    ctx = DecisionContext()
    baseline = Counter(
        decide(_mind(aggression=20.0, fear=10.0, trust=50.0), ctx, random.Random(seed))[1].behavior_id
        for seed in range(500)
    )
    timid = Counter(
        decide(_mind(aggression=20.0, fear=10.0, trust=50.0, traits=(TIMID,)), ctx, random.Random(seed))[1].behavior_id
        for seed in range(500)
    )
    assert timid[HESITATE] / sum(timid.values()) > baseline[HESITATE] / sum(baseline.values()) + 0.08


def test_quick_learner_trait_speeds_reinforcement_learning() -> None:
    base = praise(replace(_mind(last_behavior=ATTACK), traits=()))
    quick = praise(replace(_mind(last_behavior=ATTACK), traits=(QUICK_LEARNER,)))
    assert quick.learned.ATTACK > base.learned.ATTACK


def test_loyal_trait_never_enters_flee_pool() -> None:
    mind = _mind(trust=5.0, bond=0.0, fear=80.0, traits=(LOYAL,))
    ctx = DecisionContext(hp_fraction=0.1)
    scores = score_behaviors(mind, ctx)
    assert FLEE not in scores


def test_mood_and_traits_survive_serialize_round_trip() -> None:
    mind = _mind(
        aggression=44.0,
        fear=18.0,
        learn_attack=6.5,
        trust=71.0,
        bond=12.0,
        mood=36.0,
        traits=(BRAVE, QUICK_LEARNER),
        last_behavior=ATTACK,
    )
    restored = companion_mind_from_dict(companion_mind_to_dict(mind))
    assert restored == mind
