import argparse
import json
from typing import Any

from engine.logging_tools import suppress_stdout
from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.prefab_overrides import (
    FieldOverride,
    compute_prefab_overrides,
    reset_all_prefab_overrides,
    reset_prefab_override,
)
from engine.prefabs import get_prefab_manager
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload


def _load_scene_payload(scene_path: str) -> tuple[dict[str, Any], Any] | tuple[None, None]:
    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return None, None
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: prefab override CLI should report scene JSON parse failures deterministically before inspecting entity overrides
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return None, None
    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return None, None
    return data, resolved


def _find_entity(scene_payload: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    entities = scene_payload.get("entities")
    if not isinstance(entities, list):
        return None
    for entry in entities:
        if isinstance(entry, dict) and entry.get("id") == entity_id:
            return entry
    return None


def _resolve_prefab_base_entity(entity: dict[str, Any]) -> dict[str, Any] | None:
    prefab_id = entity.get("prefab_id")
    if not isinstance(prefab_id, str) or not prefab_id.strip():
        return None
    variant_id = entity.get("variant_id")
    try:
        with suppress_stdout():
            resolved = get_prefab_manager().resolve_with_variant(prefab_id.strip(), variant_id)
    except Exception:
        return None
    if not isinstance(resolved, dict):
        return None
    base_entity = resolved.get("entity")
    if not isinstance(base_entity, dict):
        return None
    return base_entity


def _emit_overrides_text(overrides: list[FieldOverride]) -> None:
    if not overrides:
        print("no overrides")
        return
    for override in overrides:
        print(f"{override.field_path}: {override.base_value!r} -> {override.override_value!r}")


def _emit_overrides_json(scene_path: str, entity_id: str, overrides: list[FieldOverride]) -> None:
    payload = {
        "scene": scene_path,
        "entity": entity_id,
        "overrides": [
            {
                "field_path": override.field_path,
                "base_value": override.base_value,
                "override_value": override.override_value,
            }
            for override in overrides
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def _handle_scene_prefab_diff(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene", "") or "").strip()
    entity_id = str(getattr(args, "entity", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing --scene")
        return 2
    if not entity_id:
        print("[Mesh][CLI] Error: missing --entity")
        return 2

    payload, _resolved = _load_scene_payload(scene_path)
    if payload is None:
        return 1

    entity = _find_entity(payload, entity_id)
    if entity is None:
        print(f"[Mesh][CLI] Error: entity not found: {scene_path} id={entity_id}")
        return 1

    base_entity = _resolve_prefab_base_entity(entity)
    if base_entity is None:
        print(f"[Mesh][CLI] Error: prefab not found for entity: {scene_path} id={entity_id}")
        return 1

    overrides = compute_prefab_overrides(entity, base_entity)
    fmt = str(getattr(args, "format", "text") or "text").strip().lower()
    if fmt == "json":
        _emit_overrides_json(scene_path, entity_id, overrides)
    else:
        _emit_overrides_text(overrides)
    return 0


def _handle_scene_prefab_reset(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene", "") or "").strip()
    entity_id = str(getattr(args, "entity", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing --scene")
        return 2
    if not entity_id:
        print("[Mesh][CLI] Error: missing --entity")
        return 2

    payload, resolved = _load_scene_payload(scene_path)
    if payload is None or resolved is None:
        return 1

    entity = _find_entity(payload, entity_id)
    if entity is None:
        print(f"[Mesh][CLI] Error: entity not found: {scene_path} id={entity_id}")
        return 1

    base_entity = _resolve_prefab_base_entity(entity)
    if base_entity is None:
        print(f"[Mesh][CLI] Error: prefab not found for entity: {scene_path} id={entity_id}")
        return 1

    field_path = getattr(args, "field", None)
    reset_all = bool(getattr(args, "all", False))

    removed = 0
    if field_path:
        changed = reset_prefab_override(entity, base_entity, str(field_path))
        removed = 1 if changed else 0
    elif reset_all:
        removed = reset_all_prefab_overrides(entity, base_entity)
    else:
        print("[Mesh][CLI] Error: must provide --field or --all")
        return 2

    if removed == 0:
        print(f"[Mesh][CLI] No overrides removed: {scene_path} id={entity_id}")
        return 0

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(payload)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after reset: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    print(f"[Mesh][CLI] Reset overrides: {scene_path} id={entity_id} removed={removed}")
    return 0
