from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, cast


@dataclass(frozen=True, slots=True)
class EntitySummary:
    id: str
    name: str
    type: str
    x: float
    y: float


def _resolve_entity_id(entity: dict[str, Any], index: int) -> str:
    for key in ("id", "entity_id"):
        raw = entity.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    mesh_name = entity.get("mesh_name")
    if isinstance(mesh_name, str) and mesh_name.strip():
        return mesh_name.strip()
    name = entity.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return f"idx:{index}"


def _resolve_entity_name(entity: dict[str, Any]) -> str:
    for key in ("mesh_name", "name", "id"):
        raw = entity.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "<unnamed>"


def _resolve_entity_type(entity: dict[str, Any]) -> str:
    for key in ("prefab_id", "type", "tag"):
        raw = entity.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "entity"


def list_entities(scene_json: dict[str, Any]) -> list[EntitySummary]:
    entities = scene_json.get("entities")
    if not isinstance(entities, list):
        return []
    summaries: list[EntitySummary] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        entity_id = _resolve_entity_id(entity, index)
        summaries.append(
            EntitySummary(
                id=entity_id,
                name=_resolve_entity_name(entity),
                type=_resolve_entity_type(entity),
                x=float(entity.get("x", 0.0) or 0.0),
                y=float(entity.get("y", 0.0) or 0.0),
            )
        )
    return summaries


def select_entity(scene_json: dict[str, Any], entity_id: str) -> str | None:
    if _find_entity(scene_json, entity_id) is None:
        return None
    return str(entity_id)


def update_entity_field(scene_json: dict[str, Any], entity_id: str, field: str, value: Any) -> dict[str, Any]:
    entity = _find_entity(scene_json, entity_id)
    if entity is None:
        return scene_json

    key = str(field or "").strip().lower()
    if key in {"x", "y"}:
        try:
            entity[key] = float(value)
        except Exception:  # noqa: BLE001  # REASON: invalid numeric position edits should leave scene entity coordinates unchanged
            return scene_json
        return scene_json

    if key in {"mesh_name", "interact_label"}:
        entity[key] = str(value or "")
        return scene_json

    if key in {"rotation_deg", "rotation"}:
        try:
            rot = float(value)
        except Exception:  # noqa: BLE001  # REASON: invalid rotation edits should leave scene entity rotation unchanged
            return scene_json
        entity["rotation"] = rot % 360.0
        return scene_json

    if key in {"tags", "tags_add", "tags_remove"}:
        tags = _normalize_tags(entity.get("tags"))
        if key == "tags_add":
            _apply_tag_delta(entity, tags, add=_normalize_tags(value))
            return scene_json
        if key == "tags_remove":
            _apply_tag_delta(entity, tags, remove=_normalize_tags(value))
            return scene_json
        if isinstance(value, dict):
            add = _normalize_tags(value.get("add"))
            remove = _normalize_tags(value.get("remove"))
            _apply_tag_delta(entity, tags, add=add, remove=remove)
            return scene_json
        entity["tags"] = _normalize_tags(value)
        return scene_json

    return scene_json


def _find_entity(scene_json: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    entities = scene_json.get("entities")
    if not isinstance(entities, list):
        return None
    key = str(entity_id or "").strip()
    if key.startswith("idx:"):
        try:
            idx = int(key.split(":", 1)[1])
        except Exception:  # noqa: BLE001  # REASON: malformed idx entity ids should fall back to the non-index entity lookup path
            idx = -1
        if 0 <= idx < len(entities) and isinstance(entities[idx], dict):
            return cast(dict[str, Any], entities[idx])
        return None
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        if key and key == _resolve_entity_id(entity, -1):
            return entity
    return None


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(value, Iterable):
        tags: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                continue
            cleaned = entry.strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags
    return []


def _apply_tag_delta(
    entity: dict[str, Any],
    tags: list[str],
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    updated = list(tags)
    if add:
        for tag in add:
            if tag not in updated:
                updated.append(tag)
    if remove:
        updated = [tag for tag in updated if tag not in set(remove)]
    entity["tags"] = updated
    return entity
