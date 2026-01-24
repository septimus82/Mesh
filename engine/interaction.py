from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


DEFAULT_INTERACT_MAX_DIST = 72.0


def _entity_id(entity: Any) -> str:
    data = getattr(entity, "mesh_entity_data", None)
    if isinstance(data, dict):
        raw = data.get("id") or data.get("entity_id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    raw = getattr(entity, "mesh_name", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def is_interactable(entity: Any) -> bool:
    behaviours = getattr(entity, "mesh_behaviours_runtime", [])
    if not isinstance(behaviours, list):
        return False
    for behaviour in behaviours:
        on_interact = getattr(behaviour, "on_interact", None)
        if callable(on_interact):
            return True
    return False


def pick_interactable(
    entities: Iterable[Any],
    *,
    player_pos: tuple[float, float],
    max_dist: float = DEFAULT_INTERACT_MAX_DIST,
    exclude_entity: Any | None = None,
    get_flag: Callable[[str, bool], bool] | None = None,
) -> Any | None:
    px, py = float(player_pos[0]), float(player_pos[1])
    max_dist_sq = float(max_dist) ** 2

    best = None
    best_dist_sq: float | None = None
    best_id = ""

    for entity in entities:
        if exclude_entity is not None and entity is exclude_entity:
            continue
        from .scene_entity_gating import runtime_entity_passes_flag_gates  # noqa: PLC0415

        if not runtime_entity_passes_flag_gates(entity, get_flag=get_flag):
            continue
        if not is_interactable(entity):
            continue
        try:
            dx = float(getattr(entity, "center_x")) - px
            dy = float(getattr(entity, "center_y")) - py
        except Exception:  # noqa: BLE001
            continue

        dist_sq = dx * dx + dy * dy
        if dist_sq > max_dist_sq:
            continue

        entity_id = _entity_id(entity)
        if best is None:
            best = entity
            best_dist_sq = dist_sq
            best_id = entity_id
            continue

        assert best_dist_sq is not None
        if dist_sq < best_dist_sq:
            best = entity
            best_dist_sq = dist_sq
            best_id = entity_id
            continue
        if dist_sq == best_dist_sq and entity_id < best_id:
            best = entity
            best_dist_sq = dist_sq
            best_id = entity_id

    return best


def _resolve_interact_label(entity: Any | None) -> str:
    if entity is None:
        return ""
    if isinstance(entity, dict):
        for key in ("interact_label", "label", "name"):
            raw = entity.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    data = getattr(entity, "mesh_entity_data", None)
    if isinstance(data, dict):
        for key in ("interact_label", "label", "name"):
            raw = data.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    for attr in ("mesh_name", "name"):
        raw = getattr(entity, attr, None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def format_interact_prompt_text(
    entity: Any | None,
    *,
    hint: str | None = None,
    label: str | None = None,
) -> str:
    if entity is None:
        return ""
    if hint is None:
        hint_label = "E"
    else:
        hint_label = str(hint or "").strip()
    base = "Interact" if not hint_label else f"{hint_label}: Interact"
    if label is None:
        label = _resolve_interact_label(entity)
    label_text = str(label or "").strip()
    if label_text:
        return f"{base}: {label_text}"
    return base


@dataclass(frozen=True, slots=True)
class InteractionCandidate:
    entity_id: str
    entity_name: str


def get_interaction_candidate_info(entity: Any | None) -> InteractionCandidate | None:
    if entity is None:
        return None
    entity_id = _entity_id(entity)
    name = getattr(entity, "mesh_name", None)
    entity_name = str(name).strip() if name is not None else ""
    return InteractionCandidate(entity_id=entity_id, entity_name=entity_name)


def get_interact_prompt(window: Any, payload: Any | None = None) -> str | None:
    if payload is not None and not is_interactable(payload):
        return None
    if payload is None:
        label = getattr(window, "current_interactable_label", None)
        if not isinstance(label, str) or not label.strip():
            return None
        payload = {"label": label.strip()}

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


def perform_interaction(window: Any, *, max_dist: float = DEFAULT_INTERACT_MAX_DIST) -> bool:
    scene = getattr(window, "scene_controller", None)
    finder = getattr(scene, "_find_player_sprite", None) if scene is not None else None
    if not callable(finder):
        return False

    try:
        actor = finder()
    except Exception:  # noqa: BLE001
        return False
    if actor is None:
        return False

    entities = getattr(window, "all_sprites", None)
    if entities is None:
        entities = getattr(scene, "all_sprites", None)
    if entities is None:
        return False

    target = pick_interactable(
        list(entities),
        player_pos=(float(getattr(actor, "center_x", 0.0)), float(getattr(actor, "center_y", 0.0))),
        max_dist=max_dist,
        exclude_entity=actor,
        get_flag=getattr(window, "get_flag", None),
    )
    if target is None:
        return False

    behaviours = getattr(target, "mesh_behaviours_runtime", [])
    if not isinstance(behaviours, list):
        return False

    ok = False
    for behaviour in behaviours:
        on_interact = getattr(behaviour, "on_interact", None)
        if callable(on_interact):
            ok = True
            on_interact(window, actor)
    return ok
