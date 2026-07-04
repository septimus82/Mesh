"""Pure companion decision engine for autonomous monster behavior.

Phase MON-2a–2e: temperament, learned weights, mood, and inheritable traits
drive a data-driven behavior registry with weighted-random selection.
Reinforcement (praise/scold/wait) updates learned weights, trust, bond, fear,
and mood without runtime imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Protocol, Sequence

ATTACK = "ATTACK"
DEFEND = "DEFEND"
HESITATE = "HESITATE"
FLEE = "FLEE"

BehaviorId = str
TraitId = str

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
FLEE_HP_THRESHOLD = 0.35
FLEE_RELATIONSHIP_THRESHOLD = 40.0

MOOD_MIN = -100.0
MOOD_MAX = 100.0
MOOD_STEP = 12.0
MOOD_BATTLE_WIN = 10.0
MOOD_BATTLE_LOSS = 12.0
MOOD_FLEE = 15.0
MOOD_DECAY = 4.0
MOOD_LEARN_FACTOR_MAX = 0.2
MOOD_ATTACK_BIAS_SCALE = 18.0
MOOD_HESITATE_BIAS_SCALE = 18.0
TRAIT_SECOND_ROLL_CHANCE = 0.35

QUICK_LEARNER = "quick_learner"
STUBBORN = "stubborn"
BRAVE = "brave"
TIMID = "timid"
LOYAL = "loyal"
WILD = "wild"
PROTECTIVE = "protective"
GLUTTONOUS = "gluttonous"


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
class TraitMods:
    learn_mult: float = 1.0
    trust_gain_mult: float = 1.0
    bond_gain_mult: float = 1.0
    fear_gain_mult: float = 1.0
    loyalty_bonus: float = 0.0
    no_flee: bool = False
    behavior_bias: tuple[tuple[BehaviorId, float], ...] = ()


@dataclass(frozen=True, slots=True)
class TraitDefinition:
    trait_id: TraitId
    conflicts: frozenset[TraitId]
    learn_mult: float = 1.0
    trust_gain_mult: float = 1.0
    bond_gain_mult: float = 1.0
    fear_gain_mult: float = 1.0
    loyalty_bonus: float = 0.0
    no_flee: bool = False
    attack_bias: float = 0.0
    defend_bias: float = 0.0
    hesitate_bias: float = 0.0
    flee_bias: float = 0.0


@dataclass(frozen=True, slots=True)
class CompanionMind:
    """Headless companion state for MON-2a–2e decision making."""

    temperament: Temperament = field(default_factory=Temperament)
    learned: LearnedWeights = field(default_factory=LearnedWeights)
    trust: float = 50.0
    bond: float = 0.0
    mood: float = 0.0
    traits: tuple[TraitId, ...] = ()
    last_behavior: BehaviorId | None = None


def bonded_starter_companion_mind() -> CompanionMind:
    """Bonded starter baseline (MON-2d-fix): trust+bond average sits at the flee threshold."""
    return CompanionMind(
        temperament=Temperament(aggression=65.0, fear=12.0),
        learned=LearnedWeights(),
        trust=60.0,
        bond=40.0,
    )


def default_caught_companion_mind() -> CompanionMind:
    """Fresh mind for caught party members — not the bonded starter baseline."""
    return CompanionMind(
        temperament=Temperament(aggression=45.0, fear=25.0),
        learned=LearnedWeights(),
        trust=35.0,
        bond=15.0,
    )


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Opaque decision context; extended by later companion slices."""

    hp_fraction: float = 1.0


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


def _clamp_mood(value: float) -> float:
    return _clamp(value, MOOD_MIN, MOOD_MAX)


def mood_learn_factor(mood: float) -> float:
    """Learning reinforcement multiplier; ±0.2 at mood extremes."""

    normalized = _clamp_mood(mood) / MOOD_MAX if MOOD_MAX != 0.0 else 0.0
    return 1.0 + normalized * MOOD_LEARN_FACTOR_MAX


def _swing_mood(mind: CompanionMind, delta: float) -> CompanionMind:
    return replace(mind, mood=_clamp_mood(mind.mood + float(delta)))


def decay_mood(mind: CompanionMind) -> CompanionMind:
    """Move mood one decay step toward neutral."""

    if mind.mood > 0.0:
        return replace(mind, mood=max(0.0, mind.mood - MOOD_DECAY))
    if mind.mood < 0.0:
        return replace(mind, mood=min(0.0, mind.mood + MOOD_DECAY))
    return mind


def apply_battle_win(mind: CompanionMind) -> CompanionMind:
    return _swing_mood(mind, MOOD_BATTLE_WIN)


def apply_battle_loss(mind: CompanionMind) -> CompanionMind:
    return _swing_mood(mind, -MOOD_BATTLE_LOSS)


def apply_battle_flee(mind: CompanionMind) -> CompanionMind:
    return _swing_mood(mind, -MOOD_FLEE)


TRAIT_REGISTRY: dict[TraitId, TraitDefinition] = {
    QUICK_LEARNER: TraitDefinition(
        trait_id=QUICK_LEARNER,
        conflicts=frozenset({STUBBORN}),
        learn_mult=1.35,
    ),
    STUBBORN: TraitDefinition(
        trait_id=STUBBORN,
        conflicts=frozenset({QUICK_LEARNER}),
        learn_mult=0.7,
    ),
    BRAVE: TraitDefinition(
        trait_id=BRAVE,
        conflicts=frozenset({TIMID}),
        attack_bias=28.0,
    ),
    TIMID: TraitDefinition(
        trait_id=TIMID,
        conflicts=frozenset({BRAVE}),
        hesitate_bias=28.0,
    ),
    LOYAL: TraitDefinition(
        trait_id=LOYAL,
        conflicts=frozenset({WILD}),
        loyalty_bonus=35.0,
        no_flee=True,
        trust_gain_mult=1.15,
    ),
    WILD: TraitDefinition(
        trait_id=WILD,
        conflicts=frozenset({LOYAL}),
        attack_bias=16.0,
        flee_bias=12.0,
    ),
    PROTECTIVE: TraitDefinition(
        trait_id=PROTECTIVE,
        conflicts=frozenset(),
        defend_bias=22.0,
    ),
    GLUTTONOUS: TraitDefinition(
        trait_id=GLUTTONOUS,
        conflicts=frozenset(),
        bond_gain_mult=1.2,
        hesitate_bias=6.0,
    ),
}


def trait_mods(traits: Sequence[TraitId]) -> TraitMods:
    """Aggregate trait modifiers from the companion's innate traits."""

    learn_mult = 1.0
    trust_gain_mult = 1.0
    bond_gain_mult = 1.0
    fear_gain_mult = 1.0
    loyalty_bonus = 0.0
    no_flee = False
    attack_bias = 0.0
    defend_bias = 0.0
    hesitate_bias = 0.0
    flee_bias = 0.0

    for trait_id in traits:
        definition = TRAIT_REGISTRY.get(trait_id)
        if definition is None:
            continue
        learn_mult *= definition.learn_mult
        trust_gain_mult *= definition.trust_gain_mult
        bond_gain_mult *= definition.bond_gain_mult
        fear_gain_mult *= definition.fear_gain_mult
        loyalty_bonus += definition.loyalty_bonus
        no_flee = no_flee or definition.no_flee
        attack_bias += definition.attack_bias
        defend_bias += definition.defend_bias
        hesitate_bias += definition.hesitate_bias
        flee_bias += definition.flee_bias

    behavior_bias: list[tuple[BehaviorId, float]] = []
    if attack_bias:
        behavior_bias.append((ATTACK, attack_bias))
    if defend_bias:
        behavior_bias.append((DEFEND, defend_bias))
    if hesitate_bias:
        behavior_bias.append((HESITATE, hesitate_bias))
    if flee_bias:
        behavior_bias.append((FLEE, flee_bias))

    return TraitMods(
        learn_mult=learn_mult,
        trust_gain_mult=trust_gain_mult,
        bond_gain_mult=bond_gain_mult,
        fear_gain_mult=fear_gain_mult,
        loyalty_bonus=loyalty_bonus,
        no_flee=no_flee,
        behavior_bias=tuple(behavior_bias),
    )


def _traits_conflict(candidate: TraitId, selected: Sequence[TraitId]) -> bool:
    definition = TRAIT_REGISTRY.get(candidate)
    if definition is None:
        return True
    for trait_id in selected:
        if trait_id in definition.conflicts:
            return True
        other = TRAIT_REGISTRY.get(trait_id)
        if other is not None and candidate in other.conflicts:
            return True
    return False


def roll_traits(rng: RandomLike) -> tuple[TraitId, ...]:
    """Roll 1 (sometimes 2) non-conflicting innate traits at companion creation."""

    pool = tuple(TRAIT_REGISTRY.keys())
    if not pool:
        return ()

    first_index = int(rng.random() * len(pool)) % len(pool)
    selected = [pool[first_index]]
    if rng.random() < TRAIT_SECOND_ROLL_CHANCE:
        available = [trait_id for trait_id in pool if trait_id not in selected and not _traits_conflict(trait_id, selected)]
        if available:
            second_index = int(rng.random() * len(available)) % len(available)
            selected.append(available[second_index])
    return tuple(selected)


def _apply_learn_delta(mind: CompanionMind, delta: float) -> LearnedWeights:
    behavior = mind.last_behavior
    if behavior is None or behavior not in {ATTACK, DEFEND, HESITATE}:
        return mind.learned
    mods = trait_mods(mind.traits)
    scaled_delta = float(delta) * mood_learn_factor(mind.mood) * mods.learn_mult
    current = getattr(mind.learned, behavior)
    updated = _clamp_learned(current + scaled_delta)
    return replace(mind.learned, **{behavior: updated})


def praise(mind: CompanionMind) -> CompanionMind:
    """Reinforce the previous behavior; rebuild trust slowly and grow bond."""

    mods = trait_mods(mind.traits)
    return replace(
        mind,
        learned=_apply_learn_delta(mind, PRAISE_LEARN_DELTA),
        trust=_clamp_relationship(mind.trust + PRAISE_TRUST_DELTA * mods.trust_gain_mult),
        bond=_clamp_relationship(mind.bond + PRAISE_BOND_DELTA * mods.bond_gain_mult),
        mood=_clamp_mood(mind.mood + MOOD_STEP),
    )


def scold(mind: CompanionMind) -> CompanionMind:
    """Suppress the previous behavior quickly at the cost of trust and calm."""

    mods = trait_mods(mind.traits)
    return replace(
        mind,
        learned=_apply_learn_delta(mind, -SCOLD_LEARN_DELTA),
        trust=_clamp_relationship(mind.trust - SCOLD_TRUST_DELTA),
        bond=mind.bond,
        mood=_clamp_mood(mind.mood - MOOD_STEP),
        temperament=replace(
            mind.temperament,
            fear=_clamp_relationship(mind.temperament.fear + SCOLD_FEAR_DELTA * mods.fear_gain_mult),
        ),
    )


def wait(mind: CompanionMind) -> CompanionMind:
    """Let the moment pass with optional tiny bond drift and no weight change."""

    mods = trait_mods(mind.traits)
    return replace(
        mind,
        bond=_clamp_relationship(mind.bond + WAIT_BOND_DELTA * mods.bond_gain_mult),
    )


def _always_available(_mind: CompanionMind, _ctx: DecisionContext) -> bool:
    return True


def _score_attack(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.aggression * 0.7 + mind.learned.ATTACK


def _score_defend(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear * 0.4 + 20.0 + mind.learned.DEFEND


def _score_hesitate(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear * 0.5 + (100.0 - mind.trust) * 0.4 + mind.learned.HESITATE


def _avg_relationship(mind: CompanionMind) -> float:
    return (mind.trust + mind.bond) / 2.0


def _effective_relationship(mind: CompanionMind) -> float:
    return _avg_relationship(mind) + trait_mods(mind.traits).loyalty_bonus


def _flee_available(mind: CompanionMind, ctx: DecisionContext) -> bool:
    mods = trait_mods(mind.traits)
    if mods.no_flee:
        return False
    return (
        float(ctx.hp_fraction) < FLEE_HP_THRESHOLD
        and _effective_relationship(mind) < FLEE_RELATIONSHIP_THRESHOLD
    )


def _score_flee(mind: CompanionMind, _ctx: DecisionContext) -> float:
    return mind.temperament.fear + (100.0 - _effective_relationship(mind))


BEHAVIOR_REGISTRY: tuple[BehaviorDefinition, ...] = (
    BehaviorDefinition(ATTACK, _always_available, _score_attack),
    BehaviorDefinition(DEFEND, _always_available, _score_defend),
    BehaviorDefinition(HESITATE, _always_available, _score_hesitate),
    BehaviorDefinition(FLEE, _flee_available, _score_flee),
)


def _apply_mood_bias(scores: dict[BehaviorId, float], mood: float) -> None:
    if mood > 0.0:
        scores[ATTACK] = scores.get(ATTACK, 0.0) + (mood / MOOD_MAX) * MOOD_ATTACK_BIAS_SCALE
    elif mood < 0.0:
        scores[HESITATE] = scores.get(HESITATE, 0.0) + (-mood / MOOD_MAX) * MOOD_HESITATE_BIAS_SCALE


def _apply_trait_bias(scores: dict[BehaviorId, float], mods: TraitMods) -> None:
    for behavior_id, bias in mods.behavior_bias:
        scores[behavior_id] = scores.get(behavior_id, 0.0) + float(bias)


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
    mods = trait_mods(mind.traits)
    _apply_trait_bias(scores, mods)
    _apply_mood_bias(scores, mind.mood)
    return scores


def decide(
    mind: CompanionMind,
    ctx: DecisionContext,
    rng: RandomLike,
    *,
    registry: Sequence[BehaviorDefinition] = BEHAVIOR_REGISTRY,
) -> tuple[CompanionMind, DecisionResult]:
    """Choose a behavior and record it as ``last_behavior`` on the returned mind."""

    mind = decay_mood(mind)
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


def companion_mind_to_dict(mind: CompanionMind) -> dict[str, Any]:
    """Serialize a companion mind to a JSON-safe plain dict."""

    last_behavior = mind.last_behavior
    payload: dict[str, Any] = {
        "temperament": {
            "aggression": float(mind.temperament.aggression),
            "fear": float(mind.temperament.fear),
        },
        "learned": {
            ATTACK: float(mind.learned.ATTACK),
            DEFEND: float(mind.learned.DEFEND),
            HESITATE: float(mind.learned.HESITATE),
        },
        "trust": float(mind.trust),
        "bond": float(mind.bond),
        "mood": float(mind.mood),
        "traits": [str(trait_id) for trait_id in mind.traits],
        "last_behavior": str(last_behavior) if last_behavior is not None else None,
    }
    return payload


def companion_mind_from_dict(data: Mapping[str, Any]) -> CompanionMind:
    """Deserialize a companion mind from a plain dict."""

    temperament_raw = data.get("temperament", {})
    learned_raw = data.get("learned", {})
    temperament = Temperament(
        aggression=float(temperament_raw.get("aggression", 0.0) or 0.0) if isinstance(temperament_raw, Mapping) else 0.0,
        fear=float(temperament_raw.get("fear", 0.0) or 0.0) if isinstance(temperament_raw, Mapping) else 0.0,
    )
    learned = LearnedWeights(
        ATTACK=float(learned_raw.get(ATTACK, 0.0) or 0.0) if isinstance(learned_raw, Mapping) else 0.0,
        DEFEND=float(learned_raw.get(DEFEND, 0.0) or 0.0) if isinstance(learned_raw, Mapping) else 0.0,
        HESITATE=float(learned_raw.get(HESITATE, 0.0) or 0.0) if isinstance(learned_raw, Mapping) else 0.0,
    )
    raw_last = data.get("last_behavior")
    last_behavior = str(raw_last) if raw_last is not None else None
    traits_raw = data.get("traits", ())
    traits: tuple[str, ...]
    if isinstance(traits_raw, Sequence) and not isinstance(traits_raw, (str, bytes)):
        traits = tuple(str(entry) for entry in traits_raw)
    else:
        traits = ()
    return CompanionMind(
        temperament=temperament,
        learned=learned,
        trust=float(data.get("trust", 50.0) or 50.0),
        bond=float(data.get("bond", 0.0) or 0.0),
        mood=float(data.get("mood", 0.0) or 0.0),
        traits=traits,
        last_behavior=last_behavior,
    )
