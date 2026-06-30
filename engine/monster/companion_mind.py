"""Pure companion decision engine for autonomous monster behavior.

Phase MON-2a/2b: temperament + learned weights drive a data-driven behavior
registry with weighted-random selection. Reinforcement (praise/scold/wait)
updates learned weights, trust, bond, and fear without runtime imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Mapping, Protocol, Sequence

ATTACK = "ATTACK"
DEFEND = "DEFEND"
HESITATE = "HESITATE"

BehaviorId = str

PRAISE_LEARN_DELTA = 5.0
SCOLD_LEARN_DELTA = 8.0
PRAISE_TRUST_DELTA = 2.0
SCOLD_TRUST_DELTA = 5.0
PRAISE_BOND_DELTA = 1.0
SCOLD_FEAR_DELTA = 4.0
WAIT_BOND_DELTA = 0.25
LEARNED_MIN = -50.0
LEARNED_MAX = 50.0
RELATIONSHIP_MIN = 0.0
RELATIONSHIP_MAX = 100.0


class RandomLike(Protocol):
    def random(self) -> float:
        ...


@dataclass(frozen=True, slots=True)
class Temperament:
    aggression: float = 0.0
    fear: float = 0.0


@dataclass(frozen=True, slots=True)
class LearnedWeights:
    ATTACK: float = 0.0
    DEFEND: float = 0.0
    HESITATE: float = 0.0


@dataclass(frozen=True, slots=True)
class CompanionMind:
    """Headless companion state for MON-2a/2b decision making."""

    temperament: Temperament = field(default_factory=Temperament)
    learned: LearnedWeights = field(default_factory=LearnedWeights)
    trust: float = 50.0
    bond: float = 0.0
    last_behavior: BehaviorId | None = None
    # MON-2d+: mood, traits multipliers plug in here without changing decide().


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Opaque decision context; extended by later companion slices."""

    pass


@dataclass(frozen=True, slots=True)
class BehaviorDefinition:
    behavior_id: BehaviorId
    available: Callable[[CompanionMind, DecisionContext], bool]
    score: Callable[[CompanionMind, DecisionContext], float]


@dataclass(frozen=True, slots=True)
class DecisionResult:
    behavior_id: BehaviorId
    scores: Mapping[BehaviorId, float]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _clamp_relationship(value: float) -> float:
    return _clamp(value, RELATIONSHIP_MIN, RELATIONSHIP_MAX)


def _clamp_learned(value: float) -> float:
    return _clamp(value, LEARNED_MIN, LEARNED_MAX)


def _apply_learn_delta(mind: CompanionMind, delta: float) -> LearnedWeights:
    behavior = mind.last_behavior
    if behavior is None or behavior not in {ATTACK, DEFEND, HESITATE}:
        return mind.learned
    current = getattr(mind.learned, behavior)
    updated = _clamp_learned(current + float(delta))
    return replace(mind.learned, **{behavior: updated})


def praise(mind: CompanionMind) -> CompanionMind:
    """Reinforce the previous behavior; rebuild trust slowly and grow bond."""

    return replace(
        mind,
        learned=_apply_learn_delta(mind, PRAISE_LEARN_DELTA),
        trust=_clamp_relationship(mind.trust + PRAISE_TRUST_DELTA),
        bond=_clamp_relationship(mind.bond + PRAISE_BOND_DELTA),
    )


def scold(mind: CompanionMind) -> CompanionMind:
    """Suppress the previous behavior quickly at the cost of trust and calm."""

    return replace(
        mind,
        learned=_apply_learn_delta(mind, -SCOLD_LEARN_DELTA),
        trust=_clamp_relationship(mind.trust - SCOLD_TRUST_DELTA),
        bond=mind.bond,
        temperament=replace(
            mind.temperament,
            fear=_clamp_relationship(mind.temperament.fear + SCOLD_FEAR_DELTA),
        ),
    )


def wait(mind: CompanionMind) -> CompanionMind:
    """Let the moment pass with optional tiny bond drift and no weight change."""

    return replace(
        mind,
        bond=_clamp_relationship(mind.bond + WAIT_BOND_DELTA),
    )


def _always_available(_mind: CompanionMind, _ctx: DecisionContext) -> bool:
    return True


def _score_attack(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.aggression * 0.7 + mind.learned.ATTACK


def _score_defend(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear * 0.4 + 20.0 + mind.learned.DEFEND


def _score_hesitate(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear * 0.5 + (100.0 - mind.trust) * 0.4 + mind.learned.HESITATE


BEHAVIOR_REGISTRY: tuple[BehaviorDefinition, ...] = (
    BehaviorDefinition(ATTACK, _always_available, _score_attack),
    BehaviorDefinition(DEFEND, _always_available, _score_defend),
    BehaviorDefinition(HESITATE, _always_available, _score_hesitate),
)


def score_behaviors(
    mind: CompanionMind,
    ctx: DecisionContext,
    *,
    registry: Sequence[BehaviorDefinition] = BEHAVIOR_REGISTRY,
) -> dict[BehaviorId, float]:
    """Return scores for every behavior that is currently available."""

    scores: dict[BehaviorId, float] = {}
    for behavior in registry:
        if behavior.available(mind, ctx):
            scores[behavior.behavior_id] = float(behavior.score(mind, ctx))
    return scores


def decide(
    mind: CompanionMind,
    ctx: DecisionContext,
    rng: RandomLike,
    *,
    registry: Sequence[BehaviorDefinition] = BEHAVIOR_REGISTRY,
) -> tuple[CompanionMind, DecisionResult]:
    """Choose a behavior and record it as ``last_behavior`` on the returned mind."""

    scores = score_behaviors(mind, ctx, registry=registry)
    if not scores:
        raise ValueError("No available behaviors to choose from")
    chosen = _weighted_random_choice(scores, rng)
    updated_mind = replace(mind, last_behavior=chosen)
    return updated_mind, DecisionResult(behavior_id=chosen, scores=scores)


def _weighted_random_choice(scores: Mapping[BehaviorId, float], rng: RandomLike) -> BehaviorId:
    total = sum(max(0.0, float(weight)) for weight in scores.values())
    if total <= 0.0:
        options = tuple(scores.keys())
        index = int(rng.random() * len(options)) % len(options)
        return options[index]

    threshold = float(rng.random()) * total
    cumulative = 0.0
    for behavior_id, weight in scores.items():
        cumulative += max(0.0, float(weight))
        if threshold < cumulative:
            return behavior_id
    return next(reversed(scores))
