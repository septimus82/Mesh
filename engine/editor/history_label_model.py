"""Pure helpers for deterministic history labels."""

from __future__ import annotations

from typing import Any


_COMMAND_ACTION_IDS: dict[str, str] = {
    "AddEntity": "editor.entity.add",
    "DeleteEntity": "editor.entity.delete",
    "RenameEntity": "editor.entity.rename",
    "MoveEntity": "editor.entity.move",
    "MoveEntities": "editor.entity.move_multi",
    "ChangeProperty": "editor.entity.param",
    "InspectorEdit": "editor.entity.field",
    "EditPrefabOverride": "editor.prefab.override.set",
    "ClearPrefabOverrides": "editor.prefab.override.clear",
    "ResetPrefabOverride": "editor.prefab.override.reset",
    "ResetPrefabOverrides": "editor.prefab.override.reset_all",
    "EditLight": "editor.light.edit",
    "AddLight": "editor.light.add",
    "DeleteLight": "editor.light.delete",
    "MoveLight": "editor.light.move",
    "EditOccluder": "editor.occluder.edit",
}

_COMMAND_LABELS: dict[str, str] = {
    "AddEntity": "Add Entity",
    "DeleteEntity": "Delete Entity",
    "RenameEntity": "Rename Entity",
    "MoveEntity": "Move Entity",
    "MoveEntities": "Move Entities",
    "ChangeProperty": "Set Param",
    "InspectorEdit": "Edit Field",
    "EditPrefabOverride": "Edit Prefab Override",
    "ClearPrefabOverrides": "Clear Prefab Overrides",
    "ResetPrefabOverride": "Reset Prefab Override",
    "ResetPrefabOverrides": "Reset Prefab Overrides",
    "AddLight": "Add Light",
    "DeleteLight": "Delete Light",
    "MoveLight": "Move Light",
    "EditLight": "Edit Light",
    "EditOccluder": "Edit Occluder",
}


def normalize_action_label(action_id: str, fallback_title: str | None) -> str:
    title = str(fallback_title or "").strip()
    if title:
        return title
    action = str(action_id or "").strip()
    return action or "Unknown Action"


def format_history_entry(action_id: str, action_title: str | None, detail: dict[str, Any] | None) -> str:
    base = normalize_action_label(action_id, action_title)
    suffix = _format_detail(detail)
    if not suffix:
        return base
    return f"{base} ({suffix})"


def format_history_label(base_label: str, detail: dict[str, Any] | None) -> str:
    base = str(base_label or "").strip() or "Unknown Action"
    suffix = _format_detail(detail)
    if not suffix:
        return base
    return f"{base} ({suffix})"


def action_id_for_command_type(command_type: Any) -> str | None:
    if not isinstance(command_type, str):
        return None
    return _COMMAND_ACTION_IDS.get(command_type)


def build_history_detail_for_command(cmd: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(cmd, dict):
        return None
    ctype = cmd.get("type")
    if not isinstance(ctype, str):
        return None
    detail: dict[str, Any] = {}
    entity_id = _extract_entity_id(cmd)
    if entity_id:
        detail["entity_id"] = entity_id
    if ctype == "RenameEntity":
        before = cmd.get("before")
        after = cmd.get("after")
        if isinstance(before, str) and before:
            detail["from"] = before
        if isinstance(after, str) and after:
            detail["to"] = after
    if ctype == "MoveEntities":
        moves = cmd.get("moves")
        if isinstance(moves, list):
            detail["count"] = len(moves)
    if ctype == "ChangeProperty":
        behaviour = cmd.get("behaviour")
        param = cmd.get("param")
        if isinstance(behaviour, str) and isinstance(param, str) and behaviour and param:
            detail["field"] = f"{behaviour}.{param}"
    if ctype == "InspectorEdit":
        field_key = cmd.get("field_key")
        if isinstance(field_key, str) and field_key:
            detail["field"] = field_key
    if ctype in {"EditLight", "AddLight", "DeleteLight", "MoveLight"}:
        light_id = _extract_light_id(cmd)
        if light_id:
            detail["light_id"] = light_id
        if ctype == "EditLight":
            field = cmd.get("field")
            if isinstance(field, str) and field:
                detail["field"] = field
    if ctype == "EditOccluder":
        occ_id = _extract_occluder_id(cmd)
        if occ_id:
            detail["occluder_id"] = occ_id
    if ctype == "EditPrefabOverride":
        key = cmd.get("key")
        if isinstance(key, str) and key:
            detail["field"] = key
    if ctype == "ResetPrefabOverride":
        behaviour = cmd.get("behaviour")
        param = cmd.get("param")
        if isinstance(behaviour, str) and isinstance(param, str) and behaviour and param:
            detail["field"] = f"{behaviour}.{param}"
    if ctype in {"ResetPrefabOverrides", "ClearPrefabOverrides"}:
        detail.setdefault("field", "all")
    return detail or None


def build_history_label_for_command(cmd: dict[str, Any]) -> str | None:
    if not isinstance(cmd, dict):
        return None
    ctype = cmd.get("type")
    if not isinstance(ctype, str):
        return None
    if ctype in {"InspectorEdit", "ChangeProperty", "EditLight"}:
        return _format_field_edit_label(cmd)
    if ctype == "EditOccluder":
        return _format_occluder_label(cmd)
    if ctype in {"AddLight", "DeleteLight", "MoveLight"}:
        detail = build_history_detail_for_command(cmd)
        return format_history_label(_COMMAND_LABELS.get(ctype, "Light"), detail)
    base = _COMMAND_LABELS.get(ctype)
    if not base:
        return None
    detail = build_history_detail_for_command(cmd)
    return format_history_label(base, detail)


def _format_detail(detail: dict[str, Any] | None) -> str:
    if not isinstance(detail, dict) or not detail:
        return ""
    parts: list[str] = []
    for key, label in (
        ("entity_id", "entity"),
        ("from", "from"),
        ("to", "to"),
        ("plane_id", "plane"),
        ("prefab_id", "prefab"),
        ("scene_id", "scene"),
        ("field", "field"),
        ("axis", "axis"),
        ("direction", "dir"),
        ("count", "count"),
        ("light_id", "light"),
        ("occluder_id", "occluder"),
    ):
        value = detail.get(key)
        if isinstance(value, (int, float)):
            parts.append(f"{label}:{value}")
        elif isinstance(value, str) and value:
            parts.append(f"{label}:{value}")
    return ", ".join(parts)


def _extract_entity_id(cmd: dict[str, Any]) -> str:
    for key in ("entity_id", "entity_name"):
        value = cmd.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = cmd.get("data")
    if isinstance(data, dict):
        for key in ("id", "entity_id", "mesh_name", "name"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_light_id(cmd: dict[str, Any]) -> str:
    for key in ("index", "light_index"):
        value = cmd.get(key)
        if isinstance(value, int):
            return f"{value}"
    return ""


def _extract_occluder_id(cmd: dict[str, Any]) -> str:
    raw_cmd = cmd.get("cmd")
    payload = None
    if isinstance(raw_cmd, dict):
        payload = raw_cmd.get("payload")
    if isinstance(payload, dict):
        occ_id = payload.get("occ_id")
        if isinstance(occ_id, str) and occ_id:
            return occ_id
        occ_idx = payload.get("occ_index")
        if isinstance(occ_idx, int):
            return f"{occ_idx}"
        idx = payload.get("index")
        if isinstance(idx, int):
            return f"{idx}"
    return ""


def _format_field_edit_label(cmd: dict[str, Any]) -> str:
    field = ""
    if cmd.get("type") == "InspectorEdit":
        field = str(cmd.get("field_key") or "")
    elif cmd.get("type") == "ChangeProperty":
        behaviour = cmd.get("behaviour")
        param = cmd.get("param")
        if isinstance(behaviour, str) and isinstance(param, str):
            field = f"{behaviour}.{param}"
    elif cmd.get("type") == "EditLight":
        field = str(cmd.get("field") or "")
    field = field.strip()
    entity_id = _extract_entity_id(cmd)
    light_id = _extract_light_id(cmd)
    target = entity_id or (f"light:{light_id}" if light_id else "")
    label = "Set"
    if cmd.get("type") == "EditLight":
        label = "Set Light"
    if field:
        label = f"{label} {field}"
    if target:
        label = f"{label} - {target}"
    change = _format_value_change(cmd.get("before"), cmd.get("after"))
    if change:
        label = f"{label} ({change})"
    return label


def _format_occluder_label(cmd: dict[str, Any]) -> str:
    base = "Edit Occluder"
    raw_cmd = cmd.get("cmd")
    kind = None
    if isinstance(raw_cmd, dict):
        kind = raw_cmd.get("kind")
    if kind == "finish_polygon":
        base = "Add Occluder"
    elif kind == "delete_polygon":
        base = "Delete Occluder"
    elif kind == "move_point":
        base = "Move Occluder Point"
    elif kind == "insert_point":
        base = "Insert Occluder Point"
    elif kind == "remove_point":
        base = "Remove Occluder Point"
    detail = build_history_detail_for_command(cmd)
    return format_history_label(base, detail)


def _format_value_change(before: Any, after: Any) -> str:
    before_text = _format_value(before)
    after_text = _format_value(after)
    if before_text and after_text:
        return f"{before_text} -> {after_text}"
    return ""


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        text = value.replace("\n", "\\n")
        return _truncate_text(text)
    return ""


def _format_float(value: float) -> str:
    text = f"{value:.3f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _truncate_text(text: str, limit: int = 24) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
