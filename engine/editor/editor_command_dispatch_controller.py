"""Controller for undo/redo command dispatch.

This module extracts _revert_command and _apply_command from EditorModeController
for the Vertical Slice Diet V2.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = logging.getLogger(__name__)


class EditorCommandDispatchController:
    """Handles undo/redo command dispatch logic.

    Extracted from EditorModeController to reduce god-file size.
    """

    def __init__(self, editor: "EditorModeController") -> None:
        self.editor = editor

    def revert_command(self, cmd: Dict[str, Any]) -> None:
        """Revert (undo) a command by type dispatch."""
        from engine.editor_light_occluder_ops import invert_occluder_command  # noqa: PLC0415

        ctype = cmd["type"]
        entity_name_raw = cmd.get("entity_name")
        entity_name = entity_name_raw if isinstance(entity_name_raw, str) else ""

        if ctype == "MoveEntity":
            entity = self.editor._find_entity_by_name(entity_name)
            if entity:
                self.editor.window.scene_controller._apply_entity_mutation(entity, x=cmd["before"]["x"], y=cmd["before"]["y"])

        elif ctype == "RotateEntities":
            self.editor._apply_rotate_entities_cmd(cmd, use_before=True)

        elif ctype == "ScaleEntities":
            self.editor._apply_scale_entities_cmd(cmd, use_before=True)

        elif ctype == "ChangeProperty":
            self.editor._update_param_internal(cmd["behaviour"], cmd["param"], cmd["before"], entity_name)

        elif ctype == "SetEntityDisplayLabel":
            self._apply_entity_display_label_command(cmd, use_before=True)

        elif ctype == "SetEntityAlpha":
            self._apply_entity_alpha_command(cmd, use_before=True)

        elif ctype == "DuplicateEntity":
            self._revert_duplicate_entity_command(cmd)

        elif ctype == "AddEntity":
            entity = self.editor._find_entity_by_name(entity_name)
            if entity:
                self.editor._delete_entity_internal(entity)
            self._remove_scene_entity(cmd)

        elif ctype == "ApplyAIOpBatch":
            for child in reversed(_command_children(cmd)):
                self.revert_command(child)

        elif ctype == "DeleteEntity":
            self._append_scene_entity(cmd.get("data"))
            self.editor._create_entity_internal(cmd["data"])

        elif ctype == "ModifyPatrolPath":
             self.editor._update_param_internal("patrol", "points", cmd["before"], entity_name)

        elif ctype == "ResizeZone":
             self.editor._update_param_internal("trigger_zone", "trigger_radius", cmd["before"], entity_name)

        elif ctype == "ResizeHitbox":
             self.editor._update_param_internal("hitbox", "width", cmd["before"]["width"], entity_name)
             self.editor._update_param_internal("hitbox", "height", cmd["before"]["height"], entity_name)

        elif ctype == "EditShape":
            field = cmd.get("field")
            if isinstance(field, str):
                entity = self.editor._find_entity_by_name(entity_name)
                if entity:
                    before = cmd.get("before") or []
                    self.editor.shape.apply_shape_payload(entity, field, before)

        elif ctype == "EditShapes":
            entity_id = cmd.get("entity_id")
            entity = None
            if isinstance(entity_id, str) and entity_id:
                entity = self.editor._find_entity_by_id(entity_id)
            if entity is None:
                entity = self.editor._find_entity_by_name(entity_name)
            if not entity:
                logger.debug("[Editor] EditShapes undo skipped; entity not found (id=%s name=%s)", entity_id, entity_name)
            else:
                before = cmd.get("before", {})
                if isinstance(before, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in before:
                            self.editor.shape.apply_shape_payload(entity, field, before.get(field))

        elif ctype == "ResetPrefabOverride":
            behaviour_name = cmd.get("behaviour")
            param_name = cmd.get("param")
            before = cmd.get("before")
            if isinstance(behaviour_name, str) and isinstance(param_name, str):
                self.editor._update_param_internal(behaviour_name, param_name, before, entity_name)

        elif ctype == "ResetPrefabOverrides":
            entity = self.editor._find_entity_by_name(entity_name) if entity_name else None
            before_cfg = cmd.get("before")
            if entity and isinstance(before_cfg, dict):
                self.editor._apply_behaviour_config_map(entity, before_cfg)
                before_shapes = cmd.get("before_shapes")
                if isinstance(before_shapes, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in before_shapes:
                            self.editor.shape.apply_shape_payload(entity, field, before_shapes.get(field))
                if self.editor.selected_entity is entity:
                    self.editor._refresh_inspector_items()

        elif ctype == "EditPrefabOverride":
            self.editor._apply_prefab_override_command(cmd, use_before=True)

        elif ctype == "ClearPrefabOverrides":
            self.editor._apply_prefab_override_bulk_command(cmd, use_before=True)

        elif ctype in ("FixSceneIssue", "FixSceneIssues"):
            from engine.editor.scene_lint_ops import (  # noqa: PLC0415
                FixSceneIssueCommand,
                FixSceneIssuesCommand,
                apply_fix_command,
                invert_fix_command,
            )

            sc = getattr(self.editor.window, "scene_controller", None)
            scene_data = getattr(sc, "_loaded_scene_data", None) if sc else None
            if isinstance(scene_data, dict) and sc is not None:
                cmd_obj: FixSceneIssueCommand | FixSceneIssuesCommand
                if ctype == "FixSceneIssues":
                    cmd_obj = FixSceneIssuesCommand.from_dict(cmd)
                else:
                    cmd_obj = FixSceneIssueCommand.from_dict(cmd)
                fix_inverse = invert_fix_command(scene_data, cmd_obj, scene_data)
                new_scene = apply_fix_command(scene_data, fix_inverse, self.editor._get_repo_root())
                sc._loaded_scene_data = new_scene
                self.editor._refresh_after_scene_fix()

        elif ctype == "PromotePrefabShapes":
            prefab_id = cmd.get("prefab_id")
            source = cmd.get("source")
            before = cmd.get("before")
            if not isinstance(prefab_id, str) or not isinstance(source, str) or not isinstance(before, dict):
                return
            from pathlib import Path

            path = Path(source)
            if not path.exists():
                self.editor.set_status(f"Promote shapes undo: source missing for '{prefab_id}'")
                return
            ok = self.editor._update_prefab_entry(path, prefab_id, before, status_prefix="Promote shapes undo")
            if ok:
                from engine.prefabs import get_prefab_manager  # noqa: PLC0415

                get_prefab_manager().load(force=True)

        elif ctype == "RenameEntity":
            entity = None
            for key in (cmd.get("current_name"), cmd.get("after"), cmd.get("before")):
                if isinstance(key, str) and key:
                    entity = self.editor._find_entity_by_name(key)
                    if entity:
                        break
            if entity:
                self.editor._apply_entity_rename(entity, cmd.get("before", ""))
                cmd["current_name"] = cmd.get("before", "")
                if self.editor.selected_entity is entity:
                    self.editor._refresh_inspector_items()
                self.editor._refresh_hierarchy_list()

        elif ctype == "EditAnimation":
            entity = self.editor._find_entity_by_name(entity_name) or self.editor.selected_entity
            if entity:
                self.editor._set_animator_config(entity, copy.deepcopy(cmd.get("before", {})))
                self.editor._refresh_animation_cache()

        elif ctype == "EditDialogue":
            self.editor._update_param_internal("Dialogue", "dialogue", copy.deepcopy(cmd.get("before", {})), entity_name)

        elif ctype == "PaintTile":
            layer = cmd.get("layer")
            col = cmd.get("col")
            row = cmd.get("row")
            before = cmd.get("before")
            if layer is not None and before is not None and col is not None and row is not None:
                self.editor.window.scene_controller.set_tile(str(layer), int(col), int(row), int(before))

        elif ctype == "AddLight":
            index = cmd.get("index", 0)
            lights = self.editor._get_scene_lights()
            if 0 <= index < len(lights):
                lights.pop(index)
            self.editor._sync_lighting_runtime()
            if self.editor.lights_selection is not None and self.editor.lights_selection == index:
                self.editor.lights_selection = None

        elif ctype == "MoveLight":
            index = cmd.get("index")
            from_pos = cmd.get("from")
            if index is not None and from_pos:
                lights = self.editor._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index]["x"], lights[index]["y"] = from_pos
                    self.editor._sync_lighting_runtime()

        elif ctype == "EditLight":
            index = cmd.get("index")
            field = cmd.get("field")
            value = cmd.get("before")
            if index is not None and field is not None:
                lights = self.editor._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index][field] = value
                    self.editor._sync_lighting_runtime()

        elif ctype == "DeleteLight":
            index = cmd.get("index", 0)
            light = cmd.get("light")
            lights = self.editor._get_scene_lights()
            if light is not None:
                lights.insert(index, light)
                self.editor._sync_lighting_runtime()

        elif ctype == "EditOccluder":
            raw_cmd = cmd.get("cmd")
            if isinstance(raw_cmd, dict):
                scene_controller = getattr(self.editor.window, "scene_controller", None)
                scene = getattr(scene_controller, "_loaded_scene_data", None)
                if not isinstance(scene, dict):
                    scene = {}
                    if scene_controller is not None:
                        setattr(scene_controller, "_loaded_scene_data", scene)
                occluder_inverse = invert_occluder_command(raw_cmd)
                from engine.editor_light_occluder_ops import apply_occluder_command  # noqa: PLC0415
                apply_occluder_command(
                    scene,
                    {"kind": occluder_inverse.kind, "payload": occluder_inverse.payload},
                )
                self.editor._sync_occluders_runtime()

        elif ctype == "AltDragDuplicate":
            self.editor._revert_alt_drag_duplicate_cmd(cmd)

        elif ctype == "AlignEntities":
            self._revert_align_entities(cmd)

        elif ctype == "EditBackgroundPlanes":
            self.editor._apply_background_planes_payload(cmd.get("before", []))

    def apply_command(self, cmd: Dict[str, Any]) -> None:
        """Apply (redo) a command by type dispatch."""
        from engine.editor_light_occluder_ops import apply_occluder_command  # noqa: PLC0415

        ctype = cmd["type"]
        entity_name_raw = cmd.get("entity_name")
        entity_name = entity_name_raw if isinstance(entity_name_raw, str) else ""

        if ctype == "MoveEntity":
            entity = self.editor._find_entity_by_name(entity_name)
            if entity:
                self.editor.window.scene_controller._apply_entity_mutation(entity, x=cmd["after"]["x"], y=cmd["after"]["y"])

        elif ctype == "RotateEntities":
            self.editor._apply_rotate_entities_cmd(cmd, use_before=False)

        elif ctype == "ScaleEntities":
            self.editor._apply_scale_entities_cmd(cmd, use_before=False)

        elif ctype == "ChangeProperty":
            self.editor._update_param_internal(cmd["behaviour"], cmd["param"], cmd["after"], entity_name)

        elif ctype == "SetEntityDisplayLabel":
            self._apply_entity_display_label_command(cmd, use_before=False)

        elif ctype == "SetEntityAlpha":
            self._apply_entity_alpha_command(cmd, use_before=False)

        elif ctype == "DuplicateEntity":
            self._apply_duplicate_entity_command(cmd)

        elif ctype == "AddEntity":
            self._append_scene_entity(cmd.get("data"))
            self.editor._create_entity_internal(cmd["data"])

        elif ctype == "ApplyAIOpBatch":
            for child in _command_children(cmd):
                self.apply_command(child)

        elif ctype == "DeleteEntity":
            entity = self.editor._find_entity_by_name(entity_name)
            if entity:
                self.editor._delete_entity_internal(entity)
            self._remove_scene_entity(cmd)

        elif ctype == "ModifyPatrolPath":
             self.editor._update_param_internal("patrol", "points", cmd["after"], entity_name)

        elif ctype == "ResizeZone":
             self.editor._update_param_internal("trigger_zone", "trigger_radius", cmd["after"], entity_name)

        elif ctype == "ResizeHitbox":
             self.editor._update_param_internal("hitbox", "width", cmd["after"]["width"], entity_name)
             self.editor._update_param_internal("hitbox", "height", cmd["after"]["height"], entity_name)

        elif ctype == "EditShape":
            field = cmd.get("field")
            if isinstance(field, str):
                entity = self.editor._find_entity_by_name(entity_name)
                if entity:
                    after = cmd.get("after") or []
                    self.editor.shape.apply_shape_payload(entity, field, after)

        elif ctype == "EditShapes":
            entity_id = cmd.get("entity_id")
            entity = None
            if isinstance(entity_id, str) and entity_id:
                entity = self.editor._find_entity_by_id(entity_id)
            if entity is None:
                entity = self.editor._find_entity_by_name(entity_name)
            if not entity:
                logger.debug("[Editor] EditShapes redo skipped; entity not found (id=%s name=%s)", entity_id, entity_name)
            else:
                after = cmd.get("after", {})
                if isinstance(after, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in after:
                            self.editor.shape.apply_shape_payload(entity, field, after.get(field))

        elif ctype == "ResetPrefabOverride":
            behaviour_name = cmd.get("behaviour")
            param_name = cmd.get("param")
            base_missing = bool(cmd.get("base_missing"))
            if isinstance(behaviour_name, str) and isinstance(param_name, str):
                if base_missing:
                    self.editor._remove_param_internal(behaviour_name, param_name, entity_name)
                else:
                    self.editor._update_param_internal(behaviour_name, param_name, cmd.get("after"), entity_name)

        elif ctype == "ResetPrefabOverrides":
            entity = self.editor._find_entity_by_name(entity_name) if entity_name else None
            after_cfg = cmd.get("after")
            if entity and isinstance(after_cfg, dict):
                self.editor._apply_behaviour_config_map(entity, after_cfg)
                after_shapes = cmd.get("after_shapes")
                if isinstance(after_shapes, dict):
                    for field in ("collision_poly", "occluder_poly"):
                        if field in after_shapes:
                            self.editor.shape.apply_shape_payload(entity, field, after_shapes.get(field))
                if self.editor.selected_entity is entity:
                    self.editor._refresh_inspector_items()

        elif ctype == "EditPrefabOverride":
            self.editor._apply_prefab_override_command(cmd, use_before=False)

        elif ctype == "ClearPrefabOverrides":
            self.editor._apply_prefab_override_bulk_command(cmd, use_before=False)

        elif ctype in ("FixSceneIssue", "FixSceneIssues"):
            from engine.editor.scene_lint_ops import (  # noqa: PLC0415
                FixSceneIssueCommand,
                FixSceneIssuesCommand,
                apply_fix_command,
            )

            sc = getattr(self.editor.window, "scene_controller", None)
            scene_data = getattr(sc, "_loaded_scene_data", None) if sc else None
            if isinstance(scene_data, dict) and sc is not None:
                cmd_obj: FixSceneIssueCommand | FixSceneIssuesCommand
                if ctype == "FixSceneIssues":
                    cmd_obj = FixSceneIssuesCommand.from_dict(cmd)
                else:
                    cmd_obj = FixSceneIssueCommand.from_dict(cmd)
                new_scene = apply_fix_command(scene_data, cmd_obj, self.editor._get_repo_root())
                sc._loaded_scene_data = new_scene
                self.editor._refresh_after_scene_fix()

        elif ctype == "PromotePrefabShapes":
            prefab_id = cmd.get("prefab_id")
            source = cmd.get("source")
            after = cmd.get("after")
            if not isinstance(prefab_id, str) or not isinstance(source, str) or not isinstance(after, dict):
                return
            from pathlib import Path

            path = Path(source)
            if not path.exists():
                self.editor.set_status(f"Promote shapes redo: source missing for '{prefab_id}'")
                return
            ok = self.editor._update_prefab_entry(path, prefab_id, after, status_prefix="Promote shapes redo")
            if ok:
                from engine.prefabs import get_prefab_manager  # noqa: PLC0415

                get_prefab_manager().load(force=True)

        elif ctype == "RenameEntity":
            entity = None
            for key in (cmd.get("current_name"), cmd.get("before"), cmd.get("after")):
                if isinstance(key, str) and key:
                    entity = self.editor._find_entity_by_name(key)
                    if entity:
                        break
            if entity:
                self.editor._apply_entity_rename(entity, cmd.get("after", ""))
                cmd["current_name"] = cmd.get("after", "")
                if self.editor.selected_entity is entity:
                    self.editor._refresh_inspector_items()
                self.editor._refresh_hierarchy_list()

        elif ctype == "EditAnimation":
            entity = self.editor._find_entity_by_name(entity_name) or self.editor.selected_entity
            if entity:
                self.editor._set_animator_config(entity, copy.deepcopy(cmd.get("after", {})))
                self.editor._refresh_animation_cache()

        elif ctype == "EditDialogue":
            self.editor._update_param_internal("Dialogue", "dialogue", copy.deepcopy(cmd.get("after", {})), entity_name)

        elif ctype == "PaintTile":
            layer = cmd.get("layer")
            col = cmd.get("col")
            row = cmd.get("row")
            after = cmd.get("after")
            if layer is not None and after is not None and col is not None and row is not None:
                self.editor.window.scene_controller.set_tile(str(layer), int(col), int(row), int(after))

        elif ctype == "AddLight":
            index = cmd.get("index", 0)
            light = cmd.get("light", {})
            lights = self.editor._get_scene_lights()
            lights.insert(index, copy.deepcopy(light))
            self.editor._sync_lighting_runtime()
            self.editor.lights_selection = index

        elif ctype == "MoveLight":
            index = cmd.get("index")
            to_pos = cmd.get("to")
            if index is not None and to_pos:
                lights = self.editor._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index]["x"], lights[index]["y"] = to_pos
                    self.editor._sync_lighting_runtime()

        elif ctype == "EditLight":
            index = cmd.get("index")
            field = cmd.get("field")
            value = cmd.get("after")
            if index is not None and field is not None:
                lights = self.editor._get_scene_lights()
                if 0 <= index < len(lights):
                    lights[index][field] = value
                    self.editor._sync_lighting_runtime()

        elif ctype == "DeleteLight":
            index = cmd.get("index", 0)
            lights = self.editor._get_scene_lights()
            if 0 <= index < len(lights):
                lights.pop(index)
                self.editor._sync_lighting_runtime()

        elif ctype == "EditOccluder":
            raw_cmd = cmd.get("cmd")
            if isinstance(raw_cmd, dict):
                scene_controller = getattr(self.editor.window, "scene_controller", None)
                scene = getattr(scene_controller, "_loaded_scene_data", None)
                if not isinstance(scene, dict):
                    scene = {}
                    if scene_controller is not None:
                        setattr(scene_controller, "_loaded_scene_data", scene)
                apply_occluder_command(scene, raw_cmd)
                self.editor._sync_occluders_runtime()

        elif ctype == "AltDragDuplicate":
            self.editor._apply_alt_drag_duplicate_cmd(cmd)

        elif ctype == "AlignEntities":
            self._apply_align_entities(cmd)

        elif ctype == "EditBackgroundPlanes":
            self.editor._apply_background_planes_payload(cmd.get("after", []))

    # -------------------------------------------------------------------------
    # AlignEntities helpers
    # -------------------------------------------------------------------------

    def _apply_align_entities(self, cmd: Dict[str, Any]) -> None:
        """Apply an AlignEntities command (redo)."""
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        moves = cmd.get("moves", [])
        for move in moves:
            entity_id = move.get("entity_id", "")
            after = move.get("after", {})
            sprite = get_sprite_for_entity_id(self.editor, entity_id)
            if sprite:
                sprite.center_x = after.get("x", sprite.center_x)
                sprite.center_y = after.get("y", sprite.center_y)
                sc = getattr(self.editor.window, "scene_controller", None)
                if sc:
                    sc._apply_entity_mutation(sprite, x=sprite.center_x, y=sprite.center_y)

    def _revert_align_entities(self, cmd: Dict[str, Any]) -> None:
        """Revert an AlignEntities command (undo)."""
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        moves = cmd.get("moves", [])
        for move in moves:
            entity_id = move.get("entity_id", "")
            before = move.get("before", {})
            sprite = get_sprite_for_entity_id(self.editor, entity_id)
            if sprite:
                sprite.center_x = before.get("x", sprite.center_x)
                sprite.center_y = before.get("y", sprite.center_y)
                sc = getattr(self.editor.window, "scene_controller", None)
                if sc:
                    sc._apply_entity_mutation(sprite, x=sprite.center_x, y=sprite.center_y)

    def _scene_entities(self) -> list[dict[str, Any]] | None:
        sc = getattr(self.editor.window, "scene_controller", None)
        scene = getattr(sc, "_loaded_scene_data", None) if sc is not None else None
        if not isinstance(scene, dict):
            return None
        entities = scene.setdefault("entities", [])
        if not isinstance(entities, list):
            return None
        return entities

    def _entity_identity(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        for key in ("id", "entity_id", "name", "mesh_name"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    def _append_scene_entity(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        entities = self._scene_entities()
        if entities is None:
            return
        identity = self._entity_identity(payload)
        if identity:
            for entity in entities:
                if self._entity_identity(entity) == identity:
                    return
        entities.append(copy.deepcopy(payload))

    def _remove_scene_entity(self, cmd: Dict[str, Any]) -> None:
        entities = self._scene_entities()
        if entities is None:
            return
        identity = self._entity_identity(cmd.get("data"))
        if not identity:
            entity_name = cmd.get("entity_name")
            identity = entity_name if isinstance(entity_name, str) else ""
        if not identity:
            return
        entities[:] = [entity for entity in entities if self._entity_identity(entity) != identity]

    def _apply_entity_display_label_command(self, cmd: Dict[str, Any], *, use_before: bool) -> None:
        entity_id = cmd.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id:
            return
        entity = self.editor._find_entity_by_id(entity_id)
        if entity is None:
            sc = getattr(getattr(self.editor, "window", None), "scene_controller", None)
            for sprite in getattr(sc, "all_sprites", ()) or ():
                data = getattr(sprite, "mesh_entity_data", None)
                if isinstance(data, dict) and any(
                    data.get(key) == entity_id for key in ("id", "entity_id")
                ):
                    entity = sprite
                    break
        if entity is None:
            return
        value = cmd.get("before" if use_before else "after")
        if not isinstance(value, str):
            return
        data = getattr(entity, "mesh_entity_data", None)
        if isinstance(data, dict):
            data["name"] = value
        if hasattr(entity, "mesh_name"):
            setattr(entity, "mesh_name", value)
        if self.editor.selected_entity is entity:
            refresh_inspector = getattr(self.editor, "_refresh_inspector_items", None)
            if callable(refresh_inspector):
                refresh_inspector()
        refresh_hierarchy = getattr(self.editor, "_refresh_hierarchy_list", None)
        if callable(refresh_hierarchy):
            refresh_hierarchy()

    def _apply_entity_alpha_command(self, cmd: Dict[str, Any], *, use_before: bool) -> None:
        entity_id = cmd.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id:
            return
        entity = self.editor._find_entity_by_id(entity_id)
        if entity is None:
            sc = getattr(getattr(self.editor, "window", None), "scene_controller", None)
            for sprite in getattr(sc, "all_sprites", ()) or ():
                data = getattr(sprite, "mesh_entity_data", None)
                if isinstance(data, dict) and any(
                    data.get(key) == entity_id for key in ("id", "entity_id")
                ):
                    entity = sprite
                    break
        if entity is None:
            return
        state = cmd.get("before" if use_before else "after")
        if not isinstance(state, dict):
            return
        data = getattr(entity, "mesh_entity_data", None)
        if not isinstance(data, dict):
            return
        if bool(state.get("present")):
            try:
                alpha = float(state.get("value"))
            except (TypeError, ValueError):
                return
            data["alpha"] = alpha
            if hasattr(entity, "alpha"):
                setattr(entity, "alpha", int(round(alpha * 255.0)))
        else:
            data.pop("alpha", None)
            if hasattr(entity, "alpha"):
                setattr(entity, "alpha", 255)
        if self.editor.selected_entity is entity:
            refresh_inspector = getattr(self.editor, "_refresh_inspector_items", None)
            if callable(refresh_inspector):
                refresh_inspector()
        refresh_hierarchy = getattr(self.editor, "_refresh_hierarchy_list", None)
        if callable(refresh_hierarchy):
            refresh_hierarchy()

    def _apply_duplicate_entity_command(self, cmd: Dict[str, Any]) -> None:
        payload = cmd.get("data")
        if not isinstance(payload, dict):
            return
        duplicate_id = self._entity_identity(payload)
        if not duplicate_id:
            return
        entities = self._scene_entities()
        if entities is not None:
            if any(self._entity_identity(entity) == duplicate_id for entity in entities):
                return
            entities.append(copy.deepcopy(payload))
        sprite = self.editor._create_entity_internal(copy.deepcopy(payload))
        self._select_single_entity(duplicate_id, sprite)
        self._refresh_after_duplicate_command()

    def _revert_duplicate_entity_command(self, cmd: Dict[str, Any]) -> None:
        payload = cmd.get("data")
        duplicate_id = self._entity_identity(payload)
        if not duplicate_id:
            duplicate_raw = cmd.get("duplicate_entity_id")
            duplicate_id = duplicate_raw if isinstance(duplicate_raw, str) else ""
        if not duplicate_id:
            return
        finder = getattr(self.editor, "_find_entity_by_id", None)
        sprite = finder(duplicate_id) if callable(finder) else None
        if sprite is None:
            sprite = self._find_sprite_by_stable_id(duplicate_id)
        if sprite is not None:
            self.editor._delete_entity_internal(sprite)
        entities = self._scene_entities()
        if entities is not None:
            entities[:] = [entity for entity in entities if self._entity_identity(entity) != duplicate_id]
        self._restore_entity_selection(cmd.get("previous_selection"))
        self._refresh_after_duplicate_command()

    def _find_sprite_by_stable_id(self, entity_id: str) -> Any:
        sc = getattr(getattr(self.editor, "window", None), "scene_controller", None)
        for sprite in getattr(sc, "all_sprites", ()) or ():
            data = getattr(sprite, "mesh_entity_data", None)
            if isinstance(data, dict) and self._entity_identity(data) == entity_id:
                return sprite
        return None

    def _select_single_entity(self, entity_id: str, sprite: Any | None) -> None:
        if entity_id:
            setattr(self.editor, "_selected_entity_ids", {entity_id})
            setattr(self.editor, "_primary_entity_id", entity_id)
        if sprite is None and entity_id:
            finder = getattr(self.editor, "_find_entity_by_id", None)
            if callable(finder):
                sprite = finder(entity_id)
        if sprite is not None:
            setattr(self.editor, "selected_entity", sprite)

    def _restore_entity_selection(self, selection: Any) -> None:
        if not isinstance(selection, dict):
            return
        selected_ids = {
            str(item)
            for item in selection.get("selected_ids", ()) or ()
            if isinstance(item, str) and item
        }
        primary_id = str(selection.get("primary_id") or selection.get("selected_id") or "")
        setattr(self.editor, "_selected_entity_ids", selected_ids)
        setattr(self.editor, "_primary_entity_id", primary_id)
        selected_sprite = self._find_sprite_by_stable_id(primary_id) if primary_id else None
        if selected_sprite is not None:
            setattr(self.editor, "selected_entity", selected_sprite)

    def _refresh_after_duplicate_command(self) -> None:
        for name in ("_refresh_hierarchy_list", "_refresh_inspector_items"):
            refresher = getattr(self.editor, name, None)
            if callable(refresher):
                refresher()
        panels_refresher = getattr(self.editor, "_refresh_entity_panels_list", None)
        if callable(panels_refresher):
            panels_refresher(sync_selected=True)


def _command_children(cmd: Dict[str, Any]) -> list[Dict[str, Any]]:
    children = cmd.get("children")
    if not isinstance(children, list):
        return []
    return [child for child in children if isinstance(child, dict)]
