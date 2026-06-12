from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import engine.optional_arcade as optional_arcade
from engine.editor_prefab_variant_ops import (
    DiffRow,
    compute_prefab_override_diff,
)
from engine.editor_prefab_variant_ops import (
    apply_override_delta as _apply_override_delta,
)
from engine.editor_prefab_variant_ops import (
    clear_all_overrides as _clear_all_overrides,
)
from engine.editor_prefab_variant_ops import (
    revert_override_key as _revert_override_key,
)
from engine.logging_tools import get_logger
from engine.prefab_overrides import compute_prefab_overrides
from engine.swallowed_exceptions import _log_swallow

logger = get_logger(__name__)


def invalidate_prefab_editor_caches() -> None:
    from engine import editor_controller  # noqa: PLC0415
    from engine.command_palette import _list_prefab_ids_from_assets  # noqa: PLC0415
    from engine.prefabs import get_prefab_manager  # noqa: PLC0415

    get_prefab_manager().load(force=True)
    _list_prefab_ids_from_assets.cache_clear()
    editor_controller.PREFAB_PALETTE = None


def write_prefabs(path: "Path", entries: list[dict[str, Any]]) -> None:
    EditorPrefabController(None).write_prefab_entries(path, entries)


class EditorPrefabController:
    """Encapsulates prefab overrides + prefab shape management."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def prefab_override_info(self, entity_data: dict[str, Any]) -> tuple[dict[str, Any] | None, set[str]]:
        base_entity = self._editor._get_prefab_base_entity(entity_data)
        if base_entity is None:
            return None, set()
        overrides = compute_prefab_overrides(entity_data, base_entity)
        return base_entity, {o.field_path for o in overrides}

    def reset_selected_prefab_override(self, selected_item: dict[str, Any]) -> bool:
        if not self._editor.selected_entity:
            return False
        if selected_item.get("type") != "param":
            return False
        entity = self._editor.selected_entity
        entity_name = getattr(entity, "mesh_name", "")
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        base_entity, override_paths = self.prefab_override_info(entity_data)
        if base_entity is None:
            self._editor.set_status("Reset override: no prefab for selection")
            return False
        behaviour_name = selected_item.get("behaviour")
        param_name = selected_item.get("name")
        if not isinstance(behaviour_name, str) or not isinstance(param_name, str):
            return False
        field_path = f"behaviour_config.{behaviour_name}.{param_name}"
        if field_path not in override_paths:
            self._editor.set_status("Reset override: no prefab override")
            return False

        current_config = entity_data.get("behaviour_config", {})
        if not isinstance(current_config, dict):
            return False
        current_behaviour = current_config.get(behaviour_name, {})
        if not isinstance(current_behaviour, dict) or param_name not in current_behaviour:
            return False

        old_value = current_behaviour.get(param_name)
        base_cfg = base_entity.get("behaviour_config", {})
        base_value = None
        base_missing = True
        if isinstance(base_cfg, dict):
            base_behaviour = base_cfg.get(behaviour_name, {})
            if isinstance(base_behaviour, dict) and param_name in base_behaviour:
                base_value = base_behaviour.get(param_name)
                base_missing = False

        if base_missing:
            self._editor._remove_param_internal(behaviour_name, param_name, entity_name)
        else:
            self._editor._update_param_internal(behaviour_name, param_name, base_value, entity_name)

        self._editor._push_command(
            {
                "type": "ResetPrefabOverride",
                "entity_name": entity_name,
                "behaviour": behaviour_name,
                "param": param_name,
                "before": old_value,
                "after": base_value,
                "base_missing": base_missing,
            }
        )
        self._editor._refresh_inspector_items()
        self._editor.set_status("Reset override: ok")
        return True

    def reset_all_prefab_overrides(self) -> bool:
        if not self._editor.selected_entity:
            return False
        entity = self._editor.selected_entity
        entity_name = getattr(entity, "mesh_name", "")
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        base_entity, override_paths = self.prefab_override_info(entity_data)
        if base_entity is None:
            self._editor.set_status("Reset overrides: no prefab for selection")
            return False

        before_config = copy.deepcopy(entity_data.get("behaviour_config") or {})
        after_config = copy.deepcopy(before_config)
        before_shapes = {
            "collision_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("occluder_poly")),
        }
        changed = False

        base_cfg = base_entity.get("behaviour_config", {})
        if not isinstance(base_cfg, dict):
            base_cfg = {}

        for path in sorted(override_paths):
            if not path.startswith("behaviour_config."):
                if path in {"collision_poly", "occluder_poly"}:
                    base_shape = base_entity.get(path)
                    if base_shape is None:
                        self._editor.shape.apply_shape_payload(entity, path, [])
                    else:
                        self._editor.shape.apply_shape_payload(entity, path, base_shape)
                    changed = True
                continue
            parts = path.split(".")
            if len(parts) < 3:
                continue
            behaviour_name = parts[1]
            param_name = parts[2]
            base_behaviour = base_cfg.get(behaviour_name, {})
            base_missing = True
            base_value = None
            if isinstance(base_behaviour, dict) and param_name in base_behaviour:
                base_missing = False
                base_value = base_behaviour.get(param_name)

            target = after_config.get(behaviour_name)
            if not isinstance(target, dict):
                target = {}
                after_config[behaviour_name] = target
            if base_missing:
                if param_name in target:
                    target.pop(param_name, None)
                    changed = True
                    if not target:
                        after_config.pop(behaviour_name, None)
            else:
                if target.get(param_name) != base_value:
                    target[param_name] = base_value
                    changed = True

        after_shapes = {
            "collision_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("occluder_poly")),
        }

        if not changed:
            self._editor.set_status("Reset overrides: none to reset")
            return False

        self._editor._apply_behaviour_config_map(entity, after_config)
        self._editor._push_command(
            {
                "type": "ResetPrefabOverrides",
                "entity_name": entity_name,
                "before": before_config,
                "after": after_config,
                "before_shapes": before_shapes,
                "after_shapes": after_shapes,
            }
        )
        self._editor._refresh_inspector_items()
        self._editor.set_status("Reset overrides: ok")
        return True

    def prefab_variant_label(self, entity_data: dict[str, Any]) -> str | None:
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            return None
        label = prefab_id.strip()
        variant_id = entity_data.get("variant_id")
        if isinstance(variant_id, str) and variant_id.strip():
            label = f"{label} ({variant_id.strip()})"
        return label

    def prefab_variant_override_rows(self, entity_data: dict[str, Any]) -> list[DiffRow]:
        base_entity = self._editor._get_prefab_base_entity(entity_data)
        if base_entity is None:
            return []
        overrides = entity_data.get("prefab_overrides")
        rows = compute_prefab_override_diff(base_entity, entity_data, overrides if isinstance(overrides, dict) else {})
        return rows

    def entity_panels_prefab_override_rows(self) -> list[DiffRow]:
        if not self._editor.selected_entity:
            return []
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(self._editor.selected_entity)
        return self.prefab_variant_override_rows(entity_data)

    def prefab_override_base_value(self, base_entity: dict[str, Any], key: str) -> tuple[bool, Any]:
        if not isinstance(base_entity, dict):
            return False, None
        parts = str(key or "").split(".")
        current: Any = base_entity
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return False, None
            current = current.get(part)
        return True, current

    def apply_prefab_override_payload(self, entity_data: dict[str, Any], updated: dict[str, Any]) -> None:
        if "prefab_overrides" in updated:
            entity_data["prefab_overrides"] = updated.get("prefab_overrides")
        else:
            entity_data.pop("prefab_overrides", None)

    def apply_prefab_override_entity_value(
        self,
        sprite: optional_arcade.arcade.Sprite,
        key: str,
        value: Any,
        *,
        present: bool,
    ) -> None:
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(sprite)
        normalized = str(key or "")
        lower_key = normalized.lower()

        if not present:
            entity_data.pop(normalized, None)
            return

        if lower_key == "x":
            try:
                self._editor.window.scene_controller._apply_entity_mutation(sprite, x=float(value))
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EPFB-001", "engine/editor/editor_prefab_controller.py blanket swallow", once=True)
                return
            return
        if lower_key == "y":
            try:
                self._editor.window.scene_controller._apply_entity_mutation(sprite, y=float(value))
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EPFB-002", "engine/editor/editor_prefab_controller.py blanket swallow", once=True)
                return
            return
        if lower_key == "scale":
            try:
                self._editor.window.scene_controller._apply_entity_mutation(sprite, scale=float(value))
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EPFB-003", "engine/editor/editor_prefab_controller.py blanket swallow", once=True)
                return
            return
        if lower_key == "tag":
            self._editor.window.scene_controller._apply_entity_mutation(sprite, tag=str(value or ""))
            return
        if lower_key in {"rotation", "rotation_deg"}:
            try:
                rotation = float(value) % 360.0
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EPFB-004", "engine/editor/editor_prefab_controller.py blanket swallow", once=True)
                return
            entity_data["rotation"] = rotation
            sprite.angle = rotation
            return
        if lower_key == "mesh_name":
            new_name = str(value or "")
            entity_data["mesh_name"] = new_name
            setattr(sprite, "mesh_name", new_name)
            if id(sprite) in self._editor._hierarchy_name_cache:
                self._editor._hierarchy_name_cache[id(sprite)] = new_name
            return

        entity_data[normalized] = value

    def apply_prefab_override_command(self, cmd: Dict[str, Any], *, use_before: bool) -> None:
        entity_id = cmd.get("entity_id")
        entity_name = cmd.get("entity_name")
        entity = None
        if isinstance(entity_id, str) and entity_id:
            entity = self._editor._find_entity_by_id(entity_id)
        if entity is None and isinstance(entity_name, str) and entity_name:
            entity = self._editor._find_entity_by_name(entity_name)
        if entity is None:
            return

        key = cmd.get("key")
        if not isinstance(key, str) or not key.strip():
            return

        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        override_present = cmd.get("before_override_present") if use_before else cmd.get("after_override_present")
        override_value = cmd.get("before_override") if use_before else cmd.get("after_override")

        if override_present:
            updated = _apply_override_delta(entity_data, key, override_value)
        else:
            updated = _revert_override_key(entity_data, key)
        self.apply_prefab_override_payload(entity_data, updated)

        value_present = cmd.get("before_value_present") if use_before else cmd.get("after_value_present")
        value = cmd.get("before_value") if use_before else cmd.get("after_value")
        self.apply_prefab_override_entity_value(entity, key, value, present=bool(value_present))

    def apply_prefab_override_bulk_command(self, cmd: Dict[str, Any], *, use_before: bool) -> None:
        entity_id = cmd.get("entity_id")
        entity_name = cmd.get("entity_name")
        entity = None
        if isinstance(entity_id, str) and entity_id:
            entity = self._editor._find_entity_by_id(entity_id)
        if entity is None and isinstance(entity_name, str) and entity_name:
            entity = self._editor._find_entity_by_name(entity_name)
        if entity is None:
            return

        overrides = cmd.get("before_overrides") if use_before else cmd.get("after_overrides")
        if not isinstance(overrides, dict):
            overrides = {}

        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        if overrides:
            entity_data["prefab_overrides"] = overrides
        else:
            entity_data.pop("prefab_overrides", None)

        values = cmd.get("before_values") if use_before else cmd.get("after_values")
        missing = cmd.get("before_missing") if use_before else cmd.get("after_missing")
        if isinstance(values, dict):
            for key, value in values.items():
                self.apply_prefab_override_entity_value(entity, str(key), value, present=True)
        if isinstance(missing, list):
            for key in missing:
                self.apply_prefab_override_entity_value(entity, str(key), None, present=False)

    def entity_panels_apply_prefab_override(self, key: str, value: Any) -> bool:
        if not self._editor.selected_entity:
            return False
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(self._editor.selected_entity)
        base_entity = self._editor._get_prefab_base_entity(entity_data)
        if base_entity is None:
            return False
        override_key = str(key or "").strip()
        if not override_key:
            return False

        overrides = entity_data.get("prefab_overrides")
        before_override_present = isinstance(overrides, dict) and override_key in overrides
        before_override = overrides.get(override_key) if isinstance(overrides, dict) else None
        before_value_present = override_key in entity_data
        before_value = entity_data.get(override_key)

        updated = _apply_override_delta(entity_data, override_key, value)
        self.apply_prefab_override_payload(entity_data, updated)
        self.apply_prefab_override_entity_value(self._editor.selected_entity, override_key, value, present=True)

        entity_id = self._editor._entity_panels_selected_id_value()
        entity_name = getattr(self._editor.selected_entity, "mesh_name", "")
        self._editor._push_command(
            {
                "type": "EditPrefabOverride",
                "entity_id": entity_id,
                "entity_name": entity_name,
                "key": override_key,
                "before_override": before_override,
                "after_override": value,
                "before_override_present": before_override_present,
                "after_override_present": True,
                "before_value": before_value,
                "after_value": value,
                "before_value_present": before_value_present,
                "after_value_present": True,
            }
        )
        self._editor._refresh_entity_panels_list(sync_selected=True)
        return True

    def entity_panels_revert_prefab_override(self, row: DiffRow) -> bool:
        if not self._editor.selected_entity:
            return False
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(self._editor.selected_entity)
        base_entity = self._editor._get_prefab_base_entity(entity_data)
        if base_entity is None:
            return False
        override_key = str(row.key or "").strip()
        if not override_key:
            return False

        overrides = entity_data.get("prefab_overrides")
        before_override_present = isinstance(overrides, dict) and override_key in overrides
        before_override = overrides.get(override_key) if isinstance(overrides, dict) else None
        before_value_present = override_key in entity_data
        before_value = entity_data.get(override_key)

        base_present, base_value = self.prefab_override_base_value(base_entity, override_key)

        updated = _revert_override_key(entity_data, override_key)
        self.apply_prefab_override_payload(entity_data, updated)
        self.apply_prefab_override_entity_value(
            self._editor.selected_entity,
            override_key,
            base_value,
            present=base_present,
        )

        entity_id = self._editor._entity_panels_selected_id_value()
        entity_name = getattr(self._editor.selected_entity, "mesh_name", "")
        self._editor._push_command(
            {
                "type": "EditPrefabOverride",
                "entity_id": entity_id,
                "entity_name": entity_name,
                "key": override_key,
                "before_override": before_override,
                "after_override": base_value if base_present else None,
                "before_override_present": before_override_present,
                "after_override_present": False,
                "before_value": before_value,
                "after_value": base_value,
                "before_value_present": before_value_present,
                "after_value_present": base_present,
            }
        )
        self._editor._refresh_entity_panels_list(sync_selected=True)
        return True

    def entity_panels_clear_prefab_overrides(self) -> bool:
        if not self._editor.selected_entity:
            return False
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(self._editor.selected_entity)
        overrides = entity_data.get("prefab_overrides")
        if not isinstance(overrides, dict) or not overrides:
            return False
        base_entity = self._editor._get_prefab_base_entity(entity_data)
        if base_entity is None:
            return False

        before_overrides = copy.deepcopy(overrides)
        before_values: dict[str, Any] = {}
        before_missing: list[str] = []
        for key in overrides.keys():
            if key in entity_data:
                before_values[key] = entity_data.get(key)
            else:
                before_missing.append(key)

        after_values: dict[str, Any] = {}
        after_missing: list[str] = []
        for key in overrides.keys():
            base_present, base_value = self.prefab_override_base_value(base_entity, key)
            if base_present:
                after_values[key] = base_value
            else:
                after_missing.append(key)
            self.apply_prefab_override_entity_value(
                self._editor.selected_entity,
                key,
                base_value,
                present=base_present,
            )

        updated = _clear_all_overrides(entity_data)
        self.apply_prefab_override_payload(entity_data, updated)

        entity_id = self._editor._entity_panels_selected_id_value()
        entity_name = getattr(self._editor.selected_entity, "mesh_name", "")
        self._editor._push_command(
            {
                "type": "ClearPrefabOverrides",
                "entity_id": entity_id,
                "entity_name": entity_name,
                "before_overrides": before_overrides,
                "after_overrides": {},
                "before_values": before_values,
                "after_values": after_values,
                "before_missing": sorted(before_missing),
                "after_missing": sorted(after_missing),
            }
        )
        self._editor._refresh_entity_panels_list(sync_selected=True)
        return True

    def resolve_prefab_source_path(self, prefab_id: str) -> tuple["Path", bool]:
        from engine.paths import resolve_path  # noqa: PLC0415
        from engine.prefabs import get_prefab_manager  # noqa: PLC0415

        fallback_used = False
        manager = get_prefab_manager()
        source = manager.prefab_sources.get(prefab_id)
        if not isinstance(source, str) or not source.strip():
            fallback_used = True
            source = "assets/prefabs.json"
        resolved = resolve_path(source)
        if not resolved.exists():
            fallback_used = True
            resolved = resolve_path("assets/prefabs.json")
        return Path(resolved), fallback_used

    def load_prefab_entries(self, path: "Path") -> list[dict[str, Any]] | None:
        try:
            raw = path.read_text(encoding="utf-8") if path.exists() else "[]"
            data = copy.deepcopy(json.loads(raw))
        except Exception as exc:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EPFB-005", "engine/editor/editor_prefab_controller.py blanket swallow", once=True)
            self._editor.set_status(f"Promote shapes: failed to read {path}: {exc}")
            return None
        if not isinstance(data, list):
            self._editor.set_status(f"Promote shapes: {path} must contain a JSON list")
            return None
        return data

    def write_prefab_entries(self, path: "Path", entries: list[dict[str, Any]]) -> None:
        from engine.persistence_io import write_json_atomic  # noqa: PLC0415

        ordered = sorted(entries, key=lambda e: str(e.get("id") or ""))
        write_json_atomic(path, ordered, indent=2, sort_keys=False, trailing_newline=True)
        invalidate_prefab_editor_caches()

    def update_prefab_entry(
        self,
        path: "Path",
        prefab_id: str,
        updated: dict[str, Any],
        *,
        status_prefix: str,
    ) -> bool:
        entries = self.load_prefab_entries(path)
        if entries is None:
            return False
        target_idx = -1
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("id") == prefab_id:
                target_idx = idx
                break
        if target_idx < 0:
            self._editor.set_status(f"{status_prefix}: prefab '{prefab_id}' not found")
            return False
        entries[target_idx] = updated
        self.write_prefab_entries(path, entries)
        return True

    def promote_prefab_shapes(self) -> bool:
        if not self._editor.selected_entity:
            return False
        entity = self._editor.selected_entity
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            self._editor.set_status("Promote shapes: selected entity has no prefab")
            return False

        path, fallback_used = self.resolve_prefab_source_path(prefab_id)
        entries = self.load_prefab_entries(path)
        if entries is None:
            return False

        target_index = -1
        target_entry: dict[str, Any] | None = None
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict) and entry.get("id") == prefab_id:
                target_index = idx
                target_entry = entry
                break
        if target_index < 0 or target_entry is None:
            self._editor.set_status(f"Promote shapes: prefab '{prefab_id}' not found")
            return False

        entry_entity = target_entry.get("entity")
        if not isinstance(entry_entity, dict):
            self._editor.set_status(f"Promote shapes: prefab '{prefab_id}' not found")
            return False

        before_entry = copy.deepcopy(target_entry)
        updated = copy.deepcopy(entry_entity)
        updated["collision_poly"] = copy.deepcopy(entity_data.get("collision_poly"))
        updated["occluder_poly"] = copy.deepcopy(entity_data.get("occluder_poly"))

        target_entry = copy.deepcopy(target_entry)
        target_entry["entity"] = updated
        entries[target_index] = target_entry

        self.write_prefab_entries(path, entries)
        display_path = path.as_posix()
        suffix = " (fallback)" if fallback_used else ""
        self._editor.set_status(
            f"Promote shapes: wrote to {display_path}{suffix}",
        )

        after_entry = copy.deepcopy(target_entry)
        self._editor._push_command(
            {
                "type": "PromotePrefabShapes",
                "prefab_id": prefab_id,
                "source": display_path,
                "before": before_entry,
                "after": after_entry,
            }
        )

        from engine.prefabs import get_prefab_manager  # noqa: PLC0415

        get_prefab_manager().load(force=True)
        return True

    def apply_prefab_shapes(self, *, only_missing: bool) -> bool:
        if not self._editor.selected_entity:
            return False
        entity = self._editor.selected_entity
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(entity)
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            action = "Apply missing" if only_missing else "Reset"
            self._editor.set_status(f"{action} shapes: no prefab on selected entity")
            return False

        try:
            from engine.prefabs import get_prefab_manager  # noqa: PLC0415

            prefab = get_prefab_manager().get_prefab(prefab_id)
        except Exception:
            _log_swallow("EPFB-006", "engine/editor/editor_prefab_controller.py blanket swallow", once=True)
            prefab = None

        if not isinstance(prefab, dict) or not prefab:
            action = "Apply missing" if only_missing else "Reset"
            self._editor.set_status(f"{action} shapes: prefab '{prefab_id}' not found")
            return False

        prefab_entity = prefab.get("entity", {})
        if not isinstance(prefab_entity, dict):
            action = "Apply missing" if only_missing else "Reset"
            self._editor.set_status(f"{action} shapes: prefab '{prefab_id}' not found")
            return False

        before = {
            "collision_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("occluder_poly")),
        }
        changed = False

        for field in ("collision_poly", "occluder_poly"):
            if only_missing and entity_data.get(field):
                continue
            prefab_points = self._editor.shape.coerce_shape_points(prefab_entity.get(field))
            if prefab_points:
                self._editor.shape.set_entity_shape_points(entity, field, prefab_points)
                changed = True
            else:
                self._editor.shape.set_entity_shape_points(entity, field, [])
                changed = True

        after = {
            "collision_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("collision_poly")),
            "occluder_poly": self._editor.shape.shape_payload_for_undo(entity_data.get("occluder_poly")),
        }

        if changed and before != after:
            name = getattr(entity, "mesh_name", "") or getattr(entity, "name", "")
            self._editor._push_command(
                {
                    "type": "EditShapes",
                    "entity_name": name,
                    "prefab_id": prefab_id,
                    "before": before,
                    "after": after,
                }
            )
            logger.info(
                "[Editor] %s prefab shapes for '%s'",
                "Applied missing" if only_missing else "Reset",
                name or prefab_id,
            )
            return True

        return False
