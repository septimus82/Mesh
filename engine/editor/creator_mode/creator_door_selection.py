"""Read-only selected-door to workflow request adapter."""

from __future__ import annotations

from collections.abc import Mapping
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

    config = _door_config(snapshot)
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
    trigger = _first_text(config, snapshot, keys=("listen_event", "trigger")) or "interact"
    required_flag = _first_text(config, snapshot, keys=("requires_flag", "required_flag"))

    return CreatorDoorWorkflowRequest(
        source_scene=str(source_scene or "").strip(),
        destination_scene=destination_scene,
        destination_spawn_id=destination_spawn_id,
        door_name=_identity(snapshot, ("display_name", "name", "mesh_name")),
        source_entity_id=_identity(snapshot, ("id", "entity_id", "name", "mesh_name")),
        locked=_locked(config, snapshot),
        required_flag=required_flag,
        trigger=trigger,
    )


def _door_config(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("behaviour_config")
    if not isinstance(raw, Mapping):
        return {}

    wanted = {_normalize(name) for name in _DOOR_CONFIG_NAMES}
    merged: dict[str, Any] = {}
    for key, value in raw.items():
        if _normalize(key) in wanted and isinstance(value, Mapping):
            merged.update(dict(value))
    return merged


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
