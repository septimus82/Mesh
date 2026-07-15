from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from engine.logging_tools import get_logger

DEFAULT_INTERACT_MAX_DIST = 72.0
_GENERIC_LABELS = {"", "interact"}

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InteractionCandidate:
    entity: Any
    entity_id: str
    label: str
    distance: float
    facing_alignment: float
    priority: int
    behaviours: tuple[Any, ...]


def _entity_payload(entity: Any) -> dict[str, Any]:
    payload = getattr(entity, "mesh_entity_data", None)
    return payload if isinstance(payload, dict) else {}


def _entity_id(entity: Any) -> str:
    payload = _entity_payload(entity)
    for key in ("id", "entity_id", "mesh_id", "uuid", "guid"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return str(raw)
    for attr in ("mesh_id", "id", "entity_id", "mesh_name", "name"):
        raw = getattr(entity, attr, None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return str(raw)
    for key in ("mesh_name", "name", "label"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _coerce_positive_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result <= 0.0:
        return None
    return result


def _position(entity: Any) -> tuple[float, float] | None:
    try:
        x = float(getattr(entity, "center_x"))
        y = float(getattr(entity, "center_y"))
    except (TypeError, ValueError, AttributeError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return (x, y)


def _entity_dimension(entity: Any) -> float:
    values: list[float] = []
    for attr in ("width", "height"):
        value = _coerce_positive_float(getattr(entity, attr, None))
        if value is not None:
            values.append(value)
    return max(values) if values else 16.0


def _contact_threshold(actor: Any, entity: Any) -> float:
    # Center overlap/contact threshold: half of the combined largest sprite extents,
    # with a conservative fallback so tiny/headless sprites can still interact when
    # effectively standing on the same object.
    return max(8.0, (_entity_dimension(actor) + _entity_dimension(entity)) * 0.5)


def _facing_vector(actor: Any | None) -> tuple[float, float] | None:
    if actor is None:
        return None
    facing = None
    payload = _entity_payload(actor)
    raw = payload.get("facing")
    if isinstance(raw, str) and raw.strip():
        facing = raw.strip().lower()
    if facing is None:
        behaviours = getattr(actor, "mesh_behaviours_runtime", None)
        if isinstance(behaviours, list):
            for behaviour in behaviours:
                raw = getattr(behaviour, "_facing", None)
                if isinstance(raw, str) and raw.strip():
                    facing = raw.strip().lower()
                    break
    return {
        "up": (0.0, 1.0),
        "down": (0.0, -1.0),
        "left": (-1.0, 0.0),
        "right": (1.0, 0.0),
    }.get(str(facing or ""))


def _behaviour_list(entity: Any) -> list[Any]:
    behaviours = getattr(entity, "mesh_behaviours_runtime", [])
    return list(behaviours) if isinstance(behaviours, list) else []


def _expected_eligibility_error(exc: Exception) -> bool:
    return isinstance(exc, (AttributeError, KeyError, RuntimeError, TypeError, ValueError))


def _log_eligibility_error_once(behaviour: Any, exc: Exception) -> None:
    if getattr(behaviour, "_mesh_interact_eligibility_error_logged", False):
        return
    setattr(behaviour, "_mesh_interact_eligibility_error_logged", True)
    logger.warning("Interaction eligibility skipped %s after %r", behaviour.__class__.__name__, exc)


def _behaviour_can_interact(behaviour: Any, actor: Any) -> bool:
    on_interact = getattr(behaviour, "on_interact", None)
    if not callable(on_interact):
        return False
    hook = getattr(behaviour, "can_interact_with", None)
    if not callable(hook):
        return True
    try:
        return bool(hook(actor))
    except Exception as exc:
        if _expected_eligibility_error(exc):
            _log_eligibility_error_once(behaviour, exc)
            return False
        raise


def _eligible_behaviours(entity: Any, actor: Any) -> tuple[Any, ...]:
    seen: set[int] = set()
    result: list[Any] = []
    for behaviour in _behaviour_list(entity):
        marker = id(behaviour)
        if marker in seen:
            continue
        seen.add(marker)
        if _behaviour_can_interact(behaviour, actor):
            result.append(behaviour)
    return tuple(result)


def _read_radius_from_entity(entity: Any) -> float | None:
    payload = _entity_payload(entity)
    for source in (payload,):
        value = _coerce_positive_float(source.get("interact_radius"))
        if value is not None:
            return value
    return _coerce_positive_float(getattr(entity, "interact_radius", None))


def _effective_radius(entity: Any, behaviours: tuple[Any, ...], max_dist: float) -> float:
    authored = _read_radius_from_entity(entity)
    if authored is not None:
        return min(float(max_dist), authored)
    radii = [
        value
        for behaviour in behaviours
        if (value := _coerce_positive_float(getattr(behaviour, "interact_radius", None))) is not None
    ]
    if radii:
        return min(float(max_dist), max(radii))
    return float(max_dist)


def _read_priority(entity: Any, behaviours: tuple[Any, ...]) -> int:
    payload = _entity_payload(entity)
    values: list[int] = []
    for raw in (
        payload.get("interaction_priority"),
        payload.get("interact_priority"),
        getattr(entity, "interaction_priority", None),
        getattr(entity, "interact_priority", None),
    ):
        try:
            if raw is not None and not isinstance(raw, bool):
                values.append(int(raw))
        except (TypeError, ValueError):
            continue
    for behaviour in behaviours:
        raw = getattr(behaviour, "interaction_priority", None)
        try:
            if raw is not None and not isinstance(raw, bool):
                values.append(int(raw))
        except (TypeError, ValueError):
            continue
    return max(values) if values else 0


def _clean_label(value: Any, *, allow_generic: bool) -> str:
    if not isinstance(value, str):
        return ""
    label = value.strip()
    if not label:
        return ""
    if not allow_generic and label.strip().lower() in _GENERIC_LABELS:
        return ""
    return label


def _candidate_label(entity: Any, behaviours: tuple[Any, ...], actor: Any | None) -> str:
    for behaviour in behaviours:
        hook = getattr(behaviour, "get_interact_label", None)
        if callable(hook):
            try:
                label = _clean_label(hook(actor), allow_generic=False)
            except Exception as exc:
                if _expected_eligibility_error(exc):
                    _log_eligibility_error_once(behaviour, exc)
                    label = ""
                else:
                    raise
            if label:
                return label
    for behaviour in behaviours:
        label = _clean_label(getattr(behaviour, "interact_label", None), allow_generic=False)
        if label:
            return label
    payload = _entity_payload(entity)
    for key in ("interact_label", "label", "name", "mesh_name"):
        label = _clean_label(payload.get(key), allow_generic=True)
        if label:
            return label
    for attr in ("interact_label", "label", "name", "mesh_name"):
        label = _clean_label(getattr(entity, attr, None), allow_generic=True)
        if label:
            return label
    return ""


def _passes_runtime_gates(entity: Any, get_flag: Callable[[str, bool], bool] | None) -> bool:
    from .scene_entity_gating import runtime_entity_passes_flag_gates  # noqa: PLC0415

    try:
        return bool(runtime_entity_passes_flag_gates(entity, get_flag=get_flag))
    except Exception as exc:
        if _expected_eligibility_error(exc):
            logger.debug("Skipping interaction gated entity after %r", exc)
            return False
        raise


def _candidate_from_entity(
    entity: Any,
    *,
    actor: Any,
    actor_pos: tuple[float, float],
    max_dist: float,
    get_flag: Callable[[str, bool], bool] | None = None,
) -> InteractionCandidate | None:
    if entity is actor:
        return None
    if not _passes_runtime_gates(entity, get_flag):
        return None
    entity_pos = _position(entity)
    if entity_pos is None:
        return None
    behaviours = _eligible_behaviours(entity, actor)
    if not behaviours:
        return None
    radius = _effective_radius(entity, behaviours, max_dist)
    dx = entity_pos[0] - actor_pos[0]
    dy = entity_pos[1] - actor_pos[1]
    distance = math.hypot(dx, dy)
    if distance > radius:
        return None
    facing = _facing_vector(actor)
    alignment = 0.0
    if distance > 0.0 and facing is not None:
        alignment = ((dx / distance) * facing[0]) + ((dy / distance) * facing[1])
        if alignment < 0.0 and distance > _contact_threshold(actor, entity):
            return None
    elif facing is not None:
        alignment = 1.0
    priority = _read_priority(entity, behaviours)
    return InteractionCandidate(
        entity=entity,
        entity_id=_entity_id(entity),
        label=_candidate_label(entity, behaviours, actor),
        distance=float(distance),
        facing_alignment=float(alignment),
        priority=int(priority),
        behaviours=behaviours,
    )


def select_interaction_candidate(
    entities: Iterable[Any],
    *,
    actor: Any | None,
    max_dist: float = DEFAULT_INTERACT_MAX_DIST,
    get_flag: Callable[[str, bool], bool] | None = None,
) -> InteractionCandidate | None:
    if actor is None:
        return None
    actor_pos = _position(actor)
    if actor_pos is None:
        return None
    try:
        capped = float(max_dist)
    except (TypeError, ValueError):
        capped = DEFAULT_INTERACT_MAX_DIST
    if capped <= 0.0 or not math.isfinite(capped):
        return None
    candidates: list[InteractionCandidate] = []
    for entity in entities:
        try:
            candidate = _candidate_from_entity(
                entity,
                actor=actor,
                actor_pos=actor_pos,
                max_dist=capped,
                get_flag=get_flag,
            )
        except Exception as exc:
            if _expected_eligibility_error(exc):
                logger.debug("Skipping malformed interaction candidate after %r", exc)
                candidate = None
            else:
                raise
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            -int(item.priority),
            -float(item.facing_alignment),
            float(item.distance),
            str(item.entity_id),
        ),
    )


def _find_actor(window: Any, actor: Any | None = None) -> Any | None:
    if actor is not None:
        return actor
    scene = getattr(window, "scene_controller", None)
    finder = getattr(scene, "_find_player_sprite", None) if scene is not None else None
    if callable(finder):
        try:
            return finder()
        except Exception as exc:
            if _expected_eligibility_error(exc):
                return None
            raise
    return getattr(window, "player", None)


def _iter_scene_entities(window: Any) -> Iterable[Any]:
    entities = getattr(window, "all_sprites", None)
    if entities is not None:
        try:
            return list(entities)
        except (TypeError, ValueError):
            return []
    scene = getattr(window, "scene_controller", None)
    if scene is not None:
        entities = getattr(scene, "all_sprites", None)
        if entities is not None:
            try:
                return list(entities)
            except (TypeError, ValueError):
                return []
    return []


def resolve_interaction_candidate(
    window: Any,
    *,
    actor: Any | None = None,
    max_dist: float = DEFAULT_INTERACT_MAX_DIST,
) -> InteractionCandidate | None:
    actor = _find_actor(window, actor)
    if actor is None:
        return None
    getter = getattr(window, "get_flag", None)
    return select_interaction_candidate(
        _iter_scene_entities(window),
        actor=actor,
        max_dist=max_dist,
        get_flag=getter if callable(getter) else None,
    )


def is_interactable(entity: Any, *, actor: Any | None = None) -> bool:
    if actor is None:
        return any(callable(getattr(behaviour, "on_interact", None)) for behaviour in _behaviour_list(entity))
    return bool(_eligible_behaviours(entity, actor))


def pick_interactable(
    entities: Iterable[Any],
    *,
    player_pos: tuple[float, float],
    max_dist: float = DEFAULT_INTERACT_MAX_DIST,
    exclude_entity: Any | None = None,
    get_flag: Callable[[str, bool], bool] | None = None,
    actor: Any | None = None,
) -> Any | None:
    # Legacy compatibility seam: callers that only provide player_pos still get
    # entity selection, now via the same candidate machinery. Without an actor,
    # facing and can_interact_with(actor) hooks are unavailable, so a lightweight
    # actor shim is used only for pure distance-based legacy calls.
    if actor is None:
        actor = exclude_entity
    if actor is None:
        actor = type("_InteractionActor", (), {})()
        actor.center_x = float(player_pos[0])
        actor.center_y = float(player_pos[1])
        actor.mesh_entity_data = {}
        actor.mesh_behaviours_runtime = []
    candidate = select_interaction_candidate(
        entities,
        actor=actor,
        max_dist=max_dist,
        get_flag=get_flag,
    )
    return None if candidate is None else candidate.entity


def _resolve_interact_label(entity: Any | None) -> str:
    if isinstance(entity, InteractionCandidate):
        return entity.label
    if entity is None:
        return ""
    if isinstance(entity, dict):
        for key in ("interact_label", "label", "name", "mesh_name"):
            label = _clean_label(entity.get(key), allow_generic=True)
            if label:
                return label
        return ""
    behaviours = _behaviour_list(entity)
    return _candidate_label(entity, tuple(behaviours), None)


def format_interact_prompt_text(
    entity: Any | None,
    *,
    hint: str | None = None,
    label: str | None = None,
) -> str:
    if entity is None:
        return ""
    hint_label = "E" if hint is None else str(hint or "").strip()
    base = "Interact" if not hint_label else f"{hint_label}: Interact"
    if label is None:
        label = _resolve_interact_label(entity)
    label_text = str(label or "").strip()
    if label_text:
        return f"{base}: {label_text}"
    return base


def get_interaction_candidate_info(entity: Any | None) -> InteractionCandidate | None:
    if isinstance(entity, InteractionCandidate):
        return entity
    if entity is None:
        return None
    return InteractionCandidate(
        entity=entity,
        entity_id=_entity_id(entity),
        label=_resolve_interact_label(entity),
        distance=0.0,
        facing_alignment=0.0,
        priority=0,
        behaviours=tuple(_behaviour_list(entity)),
    )


def get_interact_prompt(window: Any, payload: Any | None = None) -> str | None:
    if payload is not None and not isinstance(payload, InteractionCandidate) and not is_interactable(payload):
        return None
    if payload is None:
        candidate = resolve_interaction_candidate(window)
        if candidate is None:
            label = getattr(window, "current_interactable_label", None)
            if not isinstance(label, str) or not label.strip():
                return None
            payload = {"label": label.strip()}
        else:
            payload = candidate

    manager = getattr(getattr(window, "input_controller", None), "manager", None)
    if manager is None:
        manager = getattr(window, "input", None)
    input_source = "keyboard_mouse"
    if manager is not None:
        input_source = str(getattr(manager, "input_source", input_source))

    from .input_hints import get_action_hint  # noqa: PLC0415

    hint = get_action_hint("interact", input_source)
    text = format_interact_prompt_text(payload, hint=hint)
    return text or None


def _call_interact(behaviour: Any, window: Any, actor: Any) -> None:
    on_interact = getattr(behaviour, "on_interact", None)
    if not callable(on_interact):
        return
    try:
        signature = inspect.signature(on_interact)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        positional = [
            param
            for param in signature.parameters.values()
            if param.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        ]
        has_varargs = any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in signature.parameters.values())
        if not has_varargs and len(positional) <= 1:
            on_interact(actor)
            return
    on_interact(window, actor)


def perform_interaction(
    window: Any,
    *,
    actor: Any | None = None,
    candidate: InteractionCandidate | None = None,
    max_dist: float = DEFAULT_INTERACT_MAX_DIST,
) -> bool:
    actor = _find_actor(window, actor)
    if actor is None:
        return False
    if candidate is None:
        candidate = resolve_interaction_candidate(window, actor=actor, max_dist=max_dist)
    else:
        getter = getattr(window, "get_flag", None)
        pos = _position(actor)
        candidate = (
            _candidate_from_entity(
                candidate.entity,
                actor=actor,
                actor_pos=pos,
                max_dist=max_dist,
                get_flag=getter if callable(getter) else None,
            )
            if pos is not None
            else None
        )
    if candidate is None:
        return False

    invoked: set[int] = set()
    handled = False
    # Interaction continues after a behaviour exception so optional/cosmetic
    # behaviours cannot suppress primary gameplay behaviours on the same entity.
    for behaviour in candidate.behaviours:
        marker = id(behaviour)
        if marker in invoked:
            continue
        invoked.add(marker)
        try:
            _call_interact(behaviour, window, actor)
            handled = True
        except Exception as exc:
            logger.warning("Interaction behaviour %s failed: %r", behaviour.__class__.__name__, exc)
    return handled
