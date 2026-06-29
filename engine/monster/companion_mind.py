"""Pure companion decision engine for autonomous monster behavior.

Phase MON-2a: temperament + learned weights drive a data-driven behavior
registry with weighted-random selection. No runtime, battle, or UI imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol, Sequence

ATTACK = "ATTACK"
DEFEND = "DEFEND"
HESITATE = "HESITATE"

BehaviorId = str


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
    """Headless companion state for MON-2a decision making."""

    temperament: Temperament = field(default_factory=Temperament)
    learned: LearnedWeights = field(default_factory=LearnedWeights)
    # MON-2b+: trust, bond, mood, traits plug in here without changing decide().


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


def _always_available(_mind: CompanionMind, _ctx: DecisionContext) -> bool:
    return True


def _score_attack(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.aggression * 0.7 + mind.learned.ATTACK


def _score_defend(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear * 0.4 + 20.0 + mind.learned.DEFEND


def _score_hesitate(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear * 0.5 + mind.learned.HESITATE


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
) -> DecisionResult:
    """Choose a behavior via weighted-random selection over available scores."""

    scores = score_behaviors(mind, ctx, registry=registry)
    if not scores:
        raise ValueError("No available behaviors to choose from")
    chosen = _weighted_random_choice(scores, rng)
    return DecisionResult(behavior_id=chosen, scores=scores)


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
