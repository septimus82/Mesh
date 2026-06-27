from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from engine.ai_ops import build_prefab_entity_definition, find_prefab_palette_entry


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
        if op_type != "add_entity_from_prefab":
            return _result(False, f"Unsupported live operation type '{op_type}'")
        return self._add_entity_from_prefab(op, push_undo=push_undo)

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
            if op_type != "add_entity_from_prefab":
                warnings.append(f"Op {index}: unsupported live operation type '{op_type}'")
                continue

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
