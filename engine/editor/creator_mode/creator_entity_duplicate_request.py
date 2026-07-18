"""Selection -> authored entity duplicate request for Creator Mode."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CreatorEntityDuplicateRequest:
    """Canonical duplicate request for staging one authored entity copy."""

    ok: bool
    source_entity_id: str = ""
    source_label: str = ""
    source_scene: str = ""
    source_payload: dict[str, Any] | None = None
    source_fingerprint: str = ""
    duplicate_entity_id: str = ""
    from_x: float = 0.0
    from_y: float = 0.0
    to_x: float = 0.0
    to_y: float = 0.0
    dx: float = 0.0
    dy: float = 0.0
    reason: str = ""

    @property
    def available(self) -> bool:
        return bool(self.ok)


def build_creator_entity_duplicate_request(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    authored_scene: Mapping[str, Any] | None,
    duplicate_offset: tuple[float, float],
) -> CreatorEntityDuplicateRequest:
    """Build a duplicate proposal request from the current authored selection."""

    if selected is None:
        return CreatorEntityDuplicateRequest(ok=False, reason="Select one authored entity.")
    if not isinstance(selected, Mapping):
        return CreatorEntityDuplicateRequest(ok=False, reason="Selection is not an authored entity.")

    source_id = _stable_entity_id(selected)
    if not source_id:
        return CreatorEntityDuplicateRequest(
            ok=False,
            reason="This entity has no stable authored ID.",
        )
    if _is_runtime_or_helper(selected):
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            reason="Runtime-generated entities cannot be duplicated.",
        )

    scene = str(source_scene or "").strip()
    if not scene:
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            reason="Current scene path is unavailable.",
        )
    if not isinstance(authored_scene, Mapping):
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="Authored scene data is unavailable.",
        )
    entities = authored_scene.get("entities")
    if not isinstance(entities, Sequence) or isinstance(entities, (str, bytes)):
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="Authored scene entities are unavailable.",
        )

    source = _find_authored_entity_by_stable_id(entities, source_id)
    if source is None:
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="Source entity is not present in the authored scene.",
        )
    if _is_runtime_or_helper(source):
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="Runtime-generated entities cannot be duplicated.",
        )
    if _contains_self_reference(source, source_id):
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="This entity contains unsupported self-references.",
        )

    position = _resolve_position(source)
    if position is None:
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="Source entity position cannot be resolved.",
        )
    dx, dy = _coerce_offset(duplicate_offset)
    if dx is None or dy is None:
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="Duplicate offset is unavailable.",
        )

    used_ids = _used_stable_ids(entities)
    duplicate_id = next_duplicate_entity_id(source_id, used_ids)
    if duplicate_id in used_ids:
        return CreatorEntityDuplicateRequest(
            ok=False,
            source_entity_id=source_id,
            source_scene=scene,
            reason="The proposed duplicate ID is already in use.",
        )

    from_x, from_y = position
    payload = copy.deepcopy(dict(source))
    return CreatorEntityDuplicateRequest(
        ok=True,
        source_entity_id=source_id,
        source_label=_entity_label(source, source_id),
        source_scene=scene,
        source_payload=payload,
        source_fingerprint=fingerprint_entity_payload(payload),
        duplicate_entity_id=duplicate_id,
        from_x=from_x,
        from_y=from_y,
        to_x=from_x + dx,
        to_y=from_y + dy,
        dx=dx,
        dy=dy,
    )


def next_duplicate_entity_id(source_id: str, used_ids: set[str]) -> str:
    """Return canonical smallest-free ``<source_id>__dup<k>``."""

    base = str(source_id or "").strip()
    k = 1
    while True:
        candidate = f"{base}__dup{k}"
        if candidate not in used_ids:
            return candidate
        k += 1


def build_duplicate_entity_payload(
    source_payload: Mapping[str, Any],
    *,
    source_id: str,
    duplicate_id: str,
    x: float,
    y: float,
) -> dict[str, Any]:
    """Copy authored source payload and replace only identity and position."""

    clone = copy.deepcopy(dict(source_payload))
    if "id" in clone or "entity_id" not in clone:
        clone["id"] = duplicate_id
    if "entity_id" in clone:
        clone["entity_id"] = duplicate_id
    clone["x"] = float(x)
    clone["y"] = float(y)
    if clone.get("id") == source_id and "entity_id" not in clone:
        clone["id"] = duplicate_id
    return clone


def fingerprint_entity_payload(payload: Mapping[str, Any]) -> str:
    """Stable fingerprint of authored entity JSON for stale proposal detection."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def creator_entity_duplicate_request_key(request: CreatorEntityDuplicateRequest) -> str:
    """Stable duplicate-staging key for one duplicate request."""

    if not request.ok:
        return ""
    return "|".join(
        (
            request.source_scene,
            request.source_entity_id,
            request.source_fingerprint,
            request.duplicate_entity_id,
            f"{request.from_x:.6f}",
            f"{request.from_y:.6f}",
            f"{request.to_x:.6f}",
            f"{request.to_y:.6f}",
            f"{request.dx:.6f}",
            f"{request.dy:.6f}",
        )
    )


def _stable_entity_id(selected: Mapping[str, Any]) -> str:
    for key in ("id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _entity_label(selected: Mapping[str, Any], entity_id: str) -> str:
    for key in ("name", "mesh_name", "id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity_id


def _find_authored_entity_by_stable_id(
    entities: Sequence[Any],
    entity_id: str,
) -> dict[str, Any] | None:
    matches = [
        entity
        for entity in entities
        if isinstance(entity, dict) and _stable_entity_id(entity) == entity_id
    ]
    return matches[0] if len(matches) == 1 else None


def _used_stable_ids(entities: Sequence[Any]) -> set[str]:
    used: set[str] = set()
    for entity in entities:
        if isinstance(entity, Mapping):
            entity_id = _stable_entity_id(entity)
            if entity_id:
                used.add(entity_id)
    return used


def _resolve_position(entity: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        x = float(entity["x"])
        y = float(entity["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return x, y


def _coerce_offset(value: tuple[float, float]) -> tuple[float | None, float | None]:
    try:
        dx = float(value[0])
        dy = float(value[1])
    except (TypeError, ValueError, IndexError):
        return None, None
    if not math.isfinite(dx) or not math.isfinite(dy):
        return None, None
    return dx, dy


def _is_runtime_or_helper(selected: Mapping[str, Any]) -> bool:
    if bool(selected.get("_runtime_generated")) or bool(selected.get("runtime_generated")):
        return True
    if bool(selected.get("_editor_only")) or bool(selected.get("editor_only")):
        return True
    kind = str(selected.get("kind") or selected.get("_kind") or "").strip().lower()
    if kind in {"runtime", "helper", "marker", "editor_helper"}:
        return True
    tags = selected.get("tags")
    return isinstance(tags, (list, tuple)) and "editor_helper" in tags


def _contains_self_reference(payload: Mapping[str, Any], source_id: str) -> bool:
    identity_keys = {"id", "entity_id"}

    def walk(value: Any, path: tuple[str, ...]) -> bool:
        if isinstance(value, str):
            return value == source_id and (not path or path[-1] not in identity_keys)
        if isinstance(value, Mapping):
            return any(walk(child, (*path, str(key))) for key, child in value.items())
        if isinstance(value, (list, tuple)):
            return any(walk(child, path) for child in value)
        return False

    return walk(payload, ())
