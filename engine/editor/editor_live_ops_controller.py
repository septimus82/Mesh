from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from engine.ai_ops import _deep_merge, build_prefab_entity_definition, find_prefab_palette_entry


@dataclass(frozen=True)
class LiveOpProposal:
    ops: list[dict[str, Any]]
    base_revision: int
    preview_summary: str
    dry_run: dict[str, Any]


class EditorLiveOpsController:
    """Apply AI-style operations to the live editor scene."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self._active_proposal: LiveOpProposal | None = None

    def apply_live_op(self, op: dict[str, Any], *, push_undo: bool = True) -> dict[str, Any]:
        if not isinstance(op, dict):
            return _result(False, "Operation must be an object")
        op_type = str(op.get("type") or "")
        if op_type == "add_entity_from_prefab":
            return self._add_entity_from_prefab(op, push_undo=push_undo)
        if op_type == "set_behaviour_params":
            return self._set_behaviour_params(op, push_undo=push_undo)
        if op_type == "delete_entity":
            return self._delete_entity(op, push_undo=push_undo)
        if op_type == "move_entity":
            return self._move_entity(op, push_undo=push_undo)
        if op_type == "set_entity_display_label":
            return self._set_entity_display_label(op, push_undo=push_undo)
        return _result(False, f"Unsupported live operation type '{op_type}'")

    def stage_proposal(self, ops: list[dict[str, Any]]) -> LiveOpProposal:
        """Validate a proposed live-op batch without mutating the scene."""
        copied_ops = [copy.deepcopy(op) for op in ops] if isinstance(ops, list) else []
        dry_run, preview_summary = self._dry_run_batch(copied_ops)
        proposal = LiveOpProposal(
            ops=copied_ops,
            base_revision=int(getattr(self._editor, "content_revision", 0)),
            preview_summary=preview_summary,
            dry_run=dry_run,
        )
        self._active_proposal = proposal
        return proposal

    def accept_proposal(self, proposal: LiveOpProposal) -> dict[str, Any]:
        """Commit a valid proposal if it still matches the current scene revision."""
        if not isinstance(proposal, LiveOpProposal):
            return _result(False, "Proposal must be a LiveOpProposal")
        dry_run = proposal.dry_run if isinstance(proposal.dry_run, dict) else {}
        if dry_run.get("ok") is not True:
            return _result(
                False,
                "Proposal dry-run failed; regenerate before accepting",
                {"warnings": list(dry_run.get("warnings") or [])},
            )

        current_revision = int(getattr(self._editor, "content_revision", 0))
        if int(proposal.base_revision) != current_revision:
            return _result(
                False,
                "Proposal is stale; regenerate against current state",
                {
                    "stale": True,
                    "base_revision": int(proposal.base_revision),
                    "current_revision": current_revision,
                },
            )

        child_commands: list[dict[str, Any]] = []
        for op in proposal.ops:
            result = self.apply_live_op(op, push_undo=False)
            if result.get("ok") is not True:
                self._revert_applied_children(child_commands)
                return _result(False, str(result.get("message") or "Failed to apply proposal"), result.get("data"))
            data = result.get("data")
            command = data.get("command") if isinstance(data, dict) else None
            if isinstance(command, dict):
                child_commands.append(copy.deepcopy(command))

        self._editor._push_command(
            {
                "type": "ApplyAIOpBatch",
                "label": f"Apply AI Proposal ({len(child_commands)} ops)",
                "children": child_commands,
                "preview_summary": proposal.preview_summary,
            }
        )
        if self._active_proposal is proposal:
            self._active_proposal = None
        return _result(
            True,
            f"Applied AI proposal ({len(child_commands)} ops)",
            {
                "applied": len(child_commands),
                "affected_ids": list(dry_run.get("affected_ids") or []),
            },
        )

    def reject_proposal(self, proposal: LiveOpProposal) -> dict[str, Any]:
        """Drop a proposal without mutating the live scene."""
        if self._active_proposal is proposal:
            self._active_proposal = None
        return _result(True, "Rejected AI proposal", {"rejected": True})

    def _add_entity_from_prefab(self, op: dict[str, Any], *, push_undo: bool = True) -> dict[str, Any]:
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
        command = {
            "type": "AddEntity",
            "entity_name": str(entity_def.get("name") or ""),
            "data": copy.deepcopy(entity_def),
        }
        if push_undo:
            self._editor._push_command(command)
        entity_id = entity_def.get("id") or entity_def.get("entity_id") or entity_def.get("name")
        data = {
            "entity_name": entity_def.get("name"),
            "entity_id": entity_id,
        }
        if not push_undo:
            data["command"] = command
        return _result(
            True,
            f"Added prefab '{prefab_id}' to live scene",
            data,
        )

    def _dry_run_batch(self, ops: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
        warnings: list[str] = []
        affected_ids: list[str] = []
        preview_lines: list[str] = []

        scene_controller = getattr(self._editor.window, "scene_controller", None)
        scene = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return {"ok": False, "warnings": ["No live scene is loaded"], "affected_ids": []}, "No valid changes"
        staged_scene = copy.deepcopy(scene)
        entities = staged_scene.setdefault("entities", [])
        if not isinstance(entities, list):
            return {"ok": False, "warnings": ["Live scene entities is not a list"], "affected_ids": []}, "No valid changes"

        for index, op in enumerate(ops):
            if not isinstance(op, dict):
                warnings.append(f"Op {index}: operation must be an object")
                continue
            op_type = str(op.get("type") or "")
            if op_type == "add_entity_from_prefab":
                entity_def, warning = self._dry_run_add_entity_from_prefab(op, staged_scene)
                if warning:
                    warnings.append(f"Op {index}: {warning}")
                    continue
                if entity_def is None:
                    warnings.append(f"Op {index}: failed to validate add_entity_from_prefab")
                    continue

                entities.append(entity_def)
                entity_name = str(entity_def.get("name") or "")
                affected_ids.append(str(entity_def.get("id") or entity_def.get("entity_id") or entity_name))
                preview_lines.append(
                    f"Add prefab '{op.get('prefab_id') or op.get('prefab_name')}' as '{entity_name}' "
                    f"at ({float(entity_def.get('x', 0.0)):g}, {float(entity_def.get('y', 0.0)):g})"
                )
                continue

            if op_type == "set_behaviour_params":
                entity, behaviour_name, params, warning = self._dry_run_set_behaviour_params(op, staged_scene)
                if warning:
                    warnings.append(f"Op {index}: {warning}")
                    continue
                if entity is None or behaviour_name is None or params is None:
                    warnings.append(f"Op {index}: failed to validate set_behaviour_params")
                    continue

                current = _entity_behaviour_config(entity, behaviour_name)
                entity.setdefault("behaviour_config", {})[behaviour_name] = _deep_merge(current, params)
                entity_id = _entity_identity(entity)
                affected_ids.append(entity_id)
                preview_lines.append(f"Set {behaviour_name} params on '{entity_id}'")
                continue

            if op_type == "delete_entity":
                entity, warning = self._dry_run_delete_entity(op, staged_scene)
                if warning:
                    warnings.append(f"Op {index}: {warning}")
                    continue
                if entity is None:
                    warnings.append(f"Op {index}: failed to validate delete_entity")
                    continue

                entity_id = _entity_identity(entity)
                entities.remove(entity)
                affected_ids.append(entity_id)
                preview_lines.append(f"Delete entity '{entity_id}'")
                continue

            if op_type == "move_entity":
                entity, target_x, target_y, warning = self._dry_run_move_entity(op, staged_scene)
                if warning:
                    warnings.append(f"Op {index}: {warning}")
                    continue
                if entity is None or target_x is None or target_y is None:
                    warnings.append(f"Op {index}: failed to validate move_entity")
                    continue

                entity_id = _entity_identity(entity)
                from_x = float(entity.get("x", 0.0) or 0.0)
                from_y = float(entity.get("y", 0.0) or 0.0)
                entity["x"] = float(target_x)
                entity["y"] = float(target_y)
                affected_ids.append(entity_id)
                direction = str(op.get("direction") or "").strip()
                direction_suffix = f" ({direction})" if direction else ""
                preview_lines.append(
                    f"Move '{entity_id}' from ({from_x:g}, {from_y:g}) "
                    f"to ({float(target_x):g}, {float(target_y):g}){direction_suffix}"
                )
                continue

            if op_type == "set_entity_display_label":
                entity, label, warning = self._dry_run_set_entity_display_label(op, staged_scene)
                if warning:
                    warnings.append(f"Op {index}: {warning}")
                    continue
                if entity is None or label is None:
                    warnings.append(f"Op {index}: failed to validate set_entity_display_label")
                    continue

                entity_id = _stable_entity_identity(entity)
                before = str(entity.get("name") or "")
                entity["name"] = label
                affected_ids.append(entity_id)
                preview_lines.append(
                    f"Rename '{entity_id}' display label from '{before}' to '{label}'"
                )
                continue

            if op_type:
                warnings.append(f"Op {index}: unsupported live operation type '{op_type}'")
                continue
            warnings.append(f"Op {index}: unsupported live operation type '{op_type}'")

        dry_run = {"ok": not warnings and bool(ops), "warnings": warnings, "affected_ids": affected_ids}
        return dry_run, "\n".join(preview_lines) if preview_lines else "No valid changes"

    def _dry_run_add_entity_from_prefab(
        self, op: dict[str, Any], staged_scene: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        scene_controller = getattr(self._editor.window, "scene_controller", None)
        current_scene = str(getattr(scene_controller, "current_scene_path", "") or "")
        requested_scene = op.get("scene_path")
        if isinstance(requested_scene, str) and requested_scene and requested_scene != current_scene:
            return None, f"targets '{requested_scene}', but current scene is '{current_scene}'"

        prefab_id = str(op.get("prefab_id") or op.get("prefab_name") or "").strip()
        if not prefab_id:
            return None, "add_entity_from_prefab requires prefab_id"

        palette = getattr(self._editor, "prefab_palette", None)
        if not isinstance(palette, list):
            palette = []
        match = find_prefab_palette_entry(palette, prefab_id, include_id=True)
        if match is None:
            return None, f"Prefab '{prefab_id}' not found"

        try:
            x = float(op.get("x", 0.0))
            y = float(op.get("y", 0.0))
        except (TypeError, ValueError):
            return None, "x and y must be numeric"

        return (
            build_prefab_entity_definition(
                match,
                prefab_id,
                x,
                y,
                staged_scene,
                name=str(op["name"]) if isinstance(op.get("name"), str) and op.get("name") else None,
            ),
            None,
        )

    def _set_behaviour_params(self, op: dict[str, Any], *, push_undo: bool = True) -> dict[str, Any]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return _result(False, scene_mismatch)

        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return _result(False, "set_behaviour_params requires entity_id")
        behaviour_name = str(op.get("behaviour_name") or op.get("behaviour") or "").strip()
        if not behaviour_name:
            return _result(False, "set_behaviour_params requires behaviour_name")
        params = op.get("params")
        if not isinstance(params, dict):
            return _result(False, "set_behaviour_params requires params object")

        entity = self._find_live_entity(entity_ref)
        if entity is None:
            return _result(False, f"Entity '{entity_ref}' not found")
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        if not _entity_has_behaviour(entity_data, behaviour_name):
            return _result(False, f"Behaviour '{behaviour_name}' not found on '{entity_ref}'")

        entity_name = _sprite_entity_name(entity)
        current = _entity_behaviour_config(entity_data, behaviour_name)
        child_commands: list[dict[str, Any]] = []
        for key, value in params.items():
            key_text = str(key)
            before = copy.deepcopy(current.get(key_text))
            after = _deep_merge(before, value) if isinstance(before, dict) and isinstance(value, dict) else copy.deepcopy(value)
            command = {
                "type": "ChangeProperty",
                "entity_name": entity_name,
                "behaviour": behaviour_name,
                "param": key_text,
                "before": before,
                "after": after,
            }
            self._editor.command_dispatch.apply_command(command)
            child_commands.append(command)
            current[key_text] = copy.deepcopy(after)

        command = _single_or_batch_command(child_commands, f"Set {behaviour_name} Params")
        if push_undo and command is not None:
            self._editor._push_command(command)
        self._refresh_editor_surfaces()
        data: dict[str, Any] = {"entity_name": entity_name, "entity_id": entity_ref, "behaviour": behaviour_name}
        if not push_undo and command is not None:
            data["command"] = command
        return _result(True, f"Updated {behaviour_name} on '{entity_name}'", data)

    def _delete_entity(self, op: dict[str, Any], *, push_undo: bool = True) -> dict[str, Any]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return _result(False, scene_mismatch)

        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return _result(False, "delete_entity requires entity_id")
        entity = self._find_live_entity(entity_ref)
        if entity is None:
            return _result(False, f"Entity '{entity_ref}' not found")

        entity_name = _sprite_entity_name(entity)
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        command = {
            "type": "DeleteEntity",
            "entity_name": entity_name,
            "data": copy.deepcopy(entity_data),
        }
        self._editor.command_dispatch.apply_command(command)
        if push_undo:
            self._editor._push_command(command)
        self._refresh_editor_surfaces()
        data = {"entity_name": entity_name, "entity_id": entity_ref}
        if not push_undo:
            data["command"] = command
        return _result(True, f"Deleted entity '{entity_name}'", data)

    def _move_entity(self, op: dict[str, Any], *, push_undo: bool = True) -> dict[str, Any]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return _result(False, scene_mismatch)

        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return _result(False, "move_entity requires entity_id")
        try:
            target_x = float(op.get("x"))
            target_y = float(op.get("y"))
        except (TypeError, ValueError):
            return _result(False, "move_entity requires numeric x and y")

        entity = self._find_live_entity(entity_ref)
        if entity is None:
            return _result(False, f"Entity '{entity_ref}' not found")

        entity_name = _sprite_entity_name(entity)
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        before_x = float(entity_data.get("x", getattr(entity, "center_x", 0.0)) or 0.0)
        before_y = float(entity_data.get("y", getattr(entity, "center_y", 0.0)) or 0.0)
        command = {
            "type": "MoveEntity",
            "entity_name": entity_name,
            "before": {"x": before_x, "y": before_y},
            "after": {"x": float(target_x), "y": float(target_y)},
        }
        self._editor.window.scene_controller._apply_entity_mutation(
            entity,
            x=float(target_x),
            y=float(target_y),
        )
        if push_undo:
            self._editor._push_command(command)
        self._refresh_editor_surfaces()
        data: dict[str, Any] = {
            "entity_name": entity_name,
            "entity_id": entity_ref,
            "x": float(target_x),
            "y": float(target_y),
        }
        if not push_undo:
            data["command"] = command
        return _result(True, f"Moved entity '{entity_name}'", data)

    def _set_entity_display_label(self, op: dict[str, Any], *, push_undo: bool = True) -> dict[str, Any]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return _result(False, scene_mismatch)

        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return _result(False, "set_entity_display_label requires entity_id")
        field = str(op.get("field") or "name").strip()
        if field != "name":
            return _result(False, "set_entity_display_label may only update the name display label")
        label = op.get("label")
        if not isinstance(label, str) or not label.strip():
            return _result(False, "set_entity_display_label requires a non-empty label")
        proposed = label.strip()
        if any(_unsupported_label_control_character(ch) for ch in proposed):
            return _result(False, "set_entity_display_label label contains unsupported characters")

        entity = self._find_live_entity_by_stable_id(entity_ref)
        if entity is None:
            return _result(False, f"Entity '{entity_ref}' not found")
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        if _stable_entity_identity(entity_data) != entity_ref:
            return _result(False, f"Entity '{entity_ref}' stable identity cannot be resolved")
        current = entity_data.get("name")
        if not isinstance(current, str):
            return _result(False, f"Entity '{entity_ref}' has no editable display label")
        expected = op.get("expected_current_label")
        if isinstance(expected, str) and current != expected:
            return _result(False, f"Entity '{entity_ref}' display label changed; regenerate proposal")
        if current == proposed:
            return _result(False, "set_entity_display_label label is unchanged")

        command = {
            "type": "SetEntityDisplayLabel",
            "entity_id": entity_ref,
            "field": "name",
            "before": current,
            "after": proposed,
        }
        self._apply_entity_display_label(entity, proposed)
        if push_undo:
            self._editor._push_command(command)
        self._refresh_editor_surfaces()
        data: dict[str, Any] = {
            "entity_id": entity_ref,
            "field": "name",
            "before": current,
            "after": proposed,
        }
        if not push_undo:
            data["command"] = command
        return _result(True, f"Renamed entity '{entity_ref}' display label", data)

    def _dry_run_set_behaviour_params(
        self, op: dict[str, Any], staged_scene: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None, str | None]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return None, None, None, scene_mismatch
        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return None, None, None, "set_behaviour_params requires entity_id"
        entity = _find_scene_entity(staged_scene, entity_ref)
        if entity is None:
            return None, None, None, f"Entity '{entity_ref}' not found"
        behaviour_name = str(op.get("behaviour_name") or op.get("behaviour") or "").strip()
        if not behaviour_name:
            return None, None, None, "set_behaviour_params requires behaviour_name"
        if not _entity_has_behaviour(entity, behaviour_name):
            return None, None, None, f"Behaviour '{behaviour_name}' not found on '{entity_ref}'"
        params = op.get("params")
        if not isinstance(params, dict):
            return None, None, None, "set_behaviour_params requires params object"
        return entity, behaviour_name, copy.deepcopy(params), None

    def _dry_run_delete_entity(
        self, op: dict[str, Any], staged_scene: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return None, scene_mismatch
        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return None, "delete_entity requires entity_id"
        entity = _find_scene_entity(staged_scene, entity_ref)
        if entity is None:
            return None, f"Entity '{entity_ref}' not found"
        return entity, None

    def _dry_run_move_entity(
        self, op: dict[str, Any], staged_scene: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, float | None, float | None, str | None]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return None, None, None, scene_mismatch
        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return None, None, None, "move_entity requires entity_id"
        entity = _find_scene_entity(staged_scene, entity_ref)
        if entity is None:
            return None, None, None, f"Entity '{entity_ref}' not found"
        try:
            target_x = float(op.get("x"))
            target_y = float(op.get("y"))
        except (TypeError, ValueError):
            return None, None, None, "move_entity requires numeric x and y"
        return entity, target_x, target_y, None

    def _dry_run_set_entity_display_label(
        self, op: dict[str, Any], staged_scene: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        scene_mismatch = self._scene_mismatch_message(op)
        if scene_mismatch:
            return None, None, scene_mismatch
        entity_ref = _op_entity_ref(op)
        if not entity_ref:
            return None, None, "set_entity_display_label requires entity_id"
        field = str(op.get("field") or "name").strip()
        if field != "name":
            return None, None, "set_entity_display_label may only update the name display label"
        entity = _find_scene_entity_by_stable_id(staged_scene, entity_ref)
        if entity is None:
            return None, None, f"Entity '{entity_ref}' not found"
        current = entity.get("name")
        if not isinstance(current, str):
            return None, None, f"Entity '{entity_ref}' has no editable display label"
        expected = op.get("expected_current_label")
        if isinstance(expected, str) and current != expected:
            return None, None, f"Entity '{entity_ref}' display label changed; regenerate proposal"
        label = op.get("label")
        if not isinstance(label, str) or not label.strip():
            return None, None, "set_entity_display_label requires a non-empty label"
        proposed = label.strip()
        if current == proposed:
            return None, None, "set_entity_display_label label is unchanged"
        if any(_unsupported_label_control_character(ch) for ch in proposed):
            return None, None, "set_entity_display_label label contains unsupported characters"
        return entity, proposed, None

    def _scene_mismatch_message(self, op: dict[str, Any]) -> str:
        scene_controller = getattr(self._editor.window, "scene_controller", None)
        current_scene = str(getattr(scene_controller, "current_scene_path", "") or "")
        requested_scene = op.get("scene_path")
        if isinstance(requested_scene, str) and requested_scene and requested_scene != current_scene:
            return f"Live op targets '{requested_scene}', but current scene is '{current_scene}'"
        return ""

    def _find_live_entity(self, entity_ref: str) -> Any:
        finder_by_id = getattr(self._editor, "_find_entity_by_id", None)
        if callable(finder_by_id):
            entity = finder_by_id(entity_ref)
            if entity is not None:
                return entity
        finder_by_name = getattr(self._editor, "_find_entity_by_name", None)
        if callable(finder_by_name):
            return finder_by_name(entity_ref)
        return None

    def _find_live_entity_by_stable_id(self, entity_ref: str) -> Any:
        finder_by_id = getattr(self._editor, "_find_entity_by_id", None)
        if callable(finder_by_id):
            entity = finder_by_id(entity_ref)
            if entity is not None:
                return entity
        scene_controller = getattr(self._editor.window, "scene_controller", None)
        for sprite in getattr(scene_controller, "all_sprites", ()) or ():
            data = getattr(sprite, "mesh_entity_data", None)
            if isinstance(data, dict) and _stable_entity_identity(data) == entity_ref:
                return sprite
        return None

    def _apply_entity_display_label(self, entity: Any, label: str) -> None:
        data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        data["name"] = label
        if hasattr(entity, "mesh_name"):
            setattr(entity, "mesh_name", label)

    def _revert_applied_children(self, child_commands: list[dict[str, Any]]) -> None:
        dispatcher = getattr(self._editor, "command_dispatch", None)
        revert = getattr(dispatcher, "revert_command", None)
        if not callable(revert):
            return
        for command in reversed(child_commands):
            revert(command)
        self._refresh_editor_surfaces()

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


def _op_entity_ref(op: dict[str, Any]) -> str:
    for key in ("entity_id", "entity_name", "entity", "name", "id"):
        value = op.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _sprite_entity_name(sprite: Any) -> str:
    value = getattr(sprite, "mesh_name", "")
    if isinstance(value, str) and value:
        return value
    data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(data, dict):
        identity = _entity_identity(data)
        if identity:
            return identity
    return ""


def _find_scene_entity(scene: dict[str, Any], entity_ref: str) -> dict[str, Any] | None:
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return None
    for entity in entities:
        if isinstance(entity, dict) and _entity_matches(entity, entity_ref):
            return entity
    return None


def _entity_matches(entity: dict[str, Any], entity_ref: str) -> bool:
    return any(entity.get(key) == entity_ref for key in ("id", "entity_id", "name", "mesh_name"))


def _find_scene_entity_by_stable_id(scene: dict[str, Any], entity_ref: str) -> dict[str, Any] | None:
    entities = scene.get("entities")
    if not isinstance(entities, list):
        return None
    for entity in entities:
        if isinstance(entity, dict) and _stable_entity_identity(entity) == entity_ref:
            return entity
    return None


def _stable_entity_identity(entity: dict[str, Any]) -> str:
    for key in ("id", "entity_id"):
        value = entity.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _entity_identity(entity: dict[str, Any]) -> str:
    for key in ("id", "entity_id", "name", "mesh_name"):
        value = entity.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _entity_behaviour_config(entity: dict[str, Any], behaviour_name: str) -> dict[str, Any]:
    root = entity.setdefault("behaviour_config", {})
    if not isinstance(root, dict):
        entity["behaviour_config"] = {}
        root = entity["behaviour_config"]
    current = root.get(behaviour_name, {})
    if not isinstance(current, dict):
        current = {}
    return copy.deepcopy(current)


def _entity_has_behaviour(entity: dict[str, Any], behaviour_name: str) -> bool:
    behaviours = entity.get("behaviours")
    if isinstance(behaviours, list):
        for entry in behaviours:
            if entry == behaviour_name:
                return True
            if isinstance(entry, dict) and entry.get("type") == behaviour_name:
                return True
    config = entity.get("behaviour_config")
    return isinstance(config, dict) and behaviour_name in config


def _unsupported_label_control_character(ch: str) -> bool:
    if ch in ("\t", "\n", "\r"):
        return True
    return ord(ch) < 32 or ord(ch) == 127


def _single_or_batch_command(commands: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    if not commands:
        return None
    if len(commands) == 1:
        return copy.deepcopy(commands[0])
    return {
        "type": "ApplyAIOpBatch",
        "label": label,
        "children": [copy.deepcopy(command) for command in commands],
    }
