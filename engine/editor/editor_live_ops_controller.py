from __future__ import annotations

import copy
from typing import Any

from engine.ai_ops import build_prefab_entity_definition, find_prefab_palette_entry


class EditorLiveOpsController:
    """Apply AI-style operations to the live editor scene."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def apply_live_op(self, op: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(op, dict):
            return _result(False, "Operation must be an object")
        op_type = str(op.get("type") or "")
        if op_type != "add_entity_from_prefab":
            return _result(False, f"Unsupported live operation type '{op_type}'")
        return self._add_entity_from_prefab(op)

    def _add_entity_from_prefab(self, op: dict[str, Any]) -> dict[str, Any]:
        scene_controller = getattr(self._editor.window, "scene_controller", None)
        current_scene = str(getattr(scene_controller, "current_scene_path", "") or "")
        requested_scene = op.get("scene_path")
        if isinstance(requested_scene, str) and requested_scene and requested_scene != current_scene:
            return _result(False, f"Live op targets '{requested_scene}', but current scene is '{current_scene}'")

        scene = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return _result(False, "No live scene is loaded")
        entities = scene.setdefault("entities", [])
        if not isinstance(entities, list):
            return _result(False, "Live scene entities is not a list")

        prefab_id = str(op.get("prefab_id") or op.get("prefab_name") or "").strip()
        if not prefab_id:
            return _result(False, "add_entity_from_prefab requires prefab_id")

        palette = getattr(self._editor, "prefab_palette", None)
        if not isinstance(palette, list):
            palette = []
        match = find_prefab_palette_entry(palette, prefab_id, include_id=True)
        if match is None:
            return _result(False, f"Prefab '{prefab_id}' not found")

        entity_def = build_prefab_entity_definition(
            match,
            prefab_id,
            float(op.get("x", 0.0)),
            float(op.get("y", 0.0)),
            scene,
            name=str(op["name"]) if isinstance(op.get("name"), str) and op.get("name") else None,
        )

        sprite = self._editor._create_entity_internal(entity_def)
        if sprite is None:
            return _result(False, f"Failed to create sprite for prefab '{prefab_id}'")

        entities.append(entity_def)
        self._refresh_editor_surfaces()
        self._editor._push_command(
            {
                "type": "AddEntity",
                "entity_name": str(entity_def.get("name") or ""),
                "data": copy.deepcopy(entity_def),
            }
        )
        return _result(
            True,
            f"Added prefab '{prefab_id}' to live scene",
            {
                "entity_name": entity_def.get("name"),
                "entity_id": entity_def.get("id") or entity_def.get("entity_id") or entity_def.get("name"),
            },
        )

    def _refresh_editor_surfaces(self) -> None:
        for name in ("_refresh_hierarchy_list", "_refresh_inspector_items"):
            refresher = getattr(self._editor, name, None)
            if callable(refresher):
                refresher()
        panels_refresher = getattr(self._editor, "_refresh_entity_panels_list", None)
        if callable(panels_refresher):
            panels_refresher(sync_selected=True)


def _result(ok: bool, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": ok, "message": message, "data": data}
