"""Read-only selected-door to workflow request adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .creator_door_workflow import CreatorDoorWorkflowRequest
from .creator_terms import classify_entity_snapshot

_DOOR_CONFIG_NAMES = ("SceneExit", "SceneTransition")


def build_creator_door_request_from_selection(
    snapshot: Mapping[str, Any] | None,
    *,
    source_scene: str = "",
) -> CreatorDoorWorkflowRequest | None:
    """Build a door workflow request from selected entity data when possible."""

    if not isinstance(snapshot, Mapping):
        return None
    if classify_entity_snapshot(snapshot) != "Door":
        return None

    transition_behaviour = _transition_behaviour(snapshot)
    config = _door_config(snapshot, transition_behaviour)
    destination_scene = _first_text(
        config,
        snapshot,
        keys=("target_scene", "scene", "destination", "target"),
    )
    destination_spawn_id = _first_text(
        config,
        snapshot,
        keys=("spawn_id", "target_spawn", "target_spawn_id"),
    )
    trigger = _trigger(config, snapshot, transition_behaviour)
    entity_require_flags = _entity_require_flags(snapshot)
    required_flag = (
        _first_text(config, snapshot, keys=("requires_flag", "required_flag"))
        or (entity_require_flags[0] if entity_require_flags else "")
    )

    return CreatorDoorWorkflowRequest(
        source_scene=str(source_scene or "").strip(),
        destination_scene=destination_scene,
        destination_spawn_id=destination_spawn_id,
        door_name=_identity(snapshot, ("display_name", "name", "mesh_name")),
        source_entity_id=_identity(snapshot, ("id", "entity_id", "name", "mesh_name")),
        locked=_locked(config, snapshot),
        required_flag=required_flag,
        trigger=trigger,
        transition_behaviour=transition_behaviour,
        scene_exit_listen_event=_first_text(config, snapshot, keys=("listen_event",)),
        interactable_event=_interactable_event(snapshot),
        entity_require_flags=entity_require_flags,
    )


def _transition_behaviour(snapshot: Mapping[str, Any]) -> str:
    attached = _attached_behaviour_names(snapshot)
    if _normalize("SceneTransition") in attached:
        return "SceneTransition"
    if _normalize("SceneExit") in attached:
        return "SceneExit"
    return ""


def _door_config(snapshot: Mapping[str, Any], transition_behaviour: str) -> dict[str, Any]:
    if not transition_behaviour:
        return {}

    wanted = _normalize(transition_behaviour)
    merged: dict[str, Any] = {}
    for entry in _behaviour_entries(snapshot):
        if _normalize(entry.get("type") or entry.get("name") or entry.get("behaviour")) != wanted:
            continue
        params = entry.get("params")
        if isinstance(params, Mapping):
            merged.update(dict(params))

    raw = snapshot.get("behaviour_config")
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if _normalize(key) != wanted or not isinstance(value, Mapping):
                continue
            merged.update(dict(value))
    return merged


def _attached_behaviour_names(snapshot: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    raw = snapshot.get("behaviours")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for entry in raw:
            if isinstance(entry, str):
                names.add(_normalize(entry))
            elif isinstance(entry, Mapping):
                names.add(_normalize(entry.get("type") or entry.get("name") or entry.get("behaviour")))
    elif isinstance(raw, Mapping):
        names |= {_normalize(key) for key in raw.keys()}
    return {name for name in names if name}


def _behaviour_entries(snapshot: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = snapshot.get("behaviours")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(entry for entry in raw if isinstance(entry, Mapping))


def _trigger(config: Mapping[str, Any], snapshot: Mapping[str, Any], transition_behaviour: str) -> str:
    explicit = _first_text(config, snapshot, keys=("trigger",))
    if explicit:
        return explicit
    if transition_behaviour == "SceneTransition":
        trigger_on_touch = _lookup(config, "trigger_on_touch")
        allow_interact = _lookup(config, "allow_interact")
        if _truthy(trigger_on_touch) and not _truthy(allow_interact, default=True):
            return "touch"
        return "interact"
    if transition_behaviour == "SceneExit":
        return "interact"
    return "interact"


def _first_text(
    *sources: Mapping[str, Any],
    keys: tuple[str, ...],
) -> str:
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in keys:
            value = _lookup(source, key)
            if value is not None and value != "":
                return str(value).strip()
    return ""


def _identity(snapshot: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _locked(config: Mapping[str, Any], snapshot: Mapping[str, Any]) -> bool:
    locked = _lookup(config, "locked")
    if locked is None:
        locked = _lookup(snapshot, "locked")
    if isinstance(locked, str):
        return locked.strip().lower() in {"1", "true", "yes", "on", "locked"}
    if locked is not None:
        return bool(locked)
    return bool(_first_text(config, snapshot, keys=("requires_flag", "required_flag")))


def _interactable_event(snapshot: Mapping[str, Any]) -> str:
    if _normalize("Interactable") not in _attached_behaviour_names(snapshot):
        return ""
    raw = snapshot.get("behaviour_config")
    if not isinstance(raw, Mapping):
        return ""
    for key, value in raw.items():
        if _normalize(key) == _normalize("Interactable") and isinstance(value, Mapping):
            return _first_text(value, keys=("interact_event",))
    return ""


def _entity_require_flags(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    value = _lookup(snapshot, "require_flags")
    if isinstance(value, str):
        clean = value.strip()
        return (clean,) if clean else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(flag).strip() for flag in value if str(flag or "").strip())
    return ()


def _truthy(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "touch"}
    return bool(value)


def _lookup(source: Mapping[str, Any], key: str) -> object:
    if key in source:
        return source[key]
    wanted = _normalize(key)
    for existing_key, value in source.items():
        if _normalize(existing_key) == wanted:
            return value
    return None


def _normalize(value: object) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
