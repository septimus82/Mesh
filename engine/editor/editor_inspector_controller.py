from __future__ import annotations

import copy
from typing import Any, Dict, Optional, cast

from engine.editor.editor_dock_query import get_dock_snapshot

import engine.optional_arcade as optional_arcade
from engine.behaviours import get_behaviour_param_defs
from engine.logging_tools import get_logger

logger = get_logger(__name__)


class EditorInspectorController:
    """Encapsulates inspector component input handling and edits."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def set_inspector_active(self, value: bool) -> None:
        editor = self._editor
        editor.inspector_active = bool(value)
        if not editor.inspector_active:
            return
        editor.palette_active = False
        editor.hierarchy_active = False
        self.refresh_inspector_items()

    def toggle_inspector_focus(self) -> bool:
        editor = self._editor
        if not editor.selected_entity:
            return False
        editor.inspector_active = not editor.inspector_active
        if editor.inspector_active:
            editor.palette_active = False
            editor.hierarchy_active = False
            self.refresh_inspector_items()
        return True

    def handle_inspector_component_input(self, key: int, modifiers: int) -> bool:
        """Handle keyboard input for component inspector navigation and editing."""
        snapshot = get_dock_snapshot(self._editor)
        if snapshot is None or snapshot.right_tab != "Inspector":
            return False
        if not self._editor.selected_entity:
            return False

        from engine.editor.inspector_components_model import (
            InspectorCursor,
            NUMERIC_STEP_NORMAL,
            NUMERIC_STEP_SHIFT,
            apply_inspector_edit,
            build_inspector_sections,
            clamp_inspector_cursor,
            get_cursor_row,
            move_cursor,
            toggle_section,
        )

        entity_json = self.get_selected_entity_json_for_inspector()
        if entity_json is None:
            return False

        sections = build_inspector_sections(
            entity_json, None, self._editor._inspector_sections_expanded
        )
        if not sections:
            return False

        cursor = InspectorCursor(
            section_id=self._editor._inspector_cursor[0],
            row_index=self._editor._inspector_cursor[1],
        )
        cursor = clamp_inspector_cursor(cursor, sections)

        if self._editor._inspector_text_edit_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return self.inspector_commit_text_edit()
            if key == optional_arcade.arcade.key.ESCAPE:
                self.inspector_cancel_text_edit()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor._inspector_text_buffer = self._editor._inspector_text_buffer[:-1]
                return True
            return True

        if key == optional_arcade.arcade.key.UP:
            new_cursor = move_cursor(cursor, sections, "up")
            self._editor._inspector_cursor = (new_cursor.section_id, new_cursor.row_index)
            return True

        if key == optional_arcade.arcade.key.DOWN:
            new_cursor = move_cursor(cursor, sections, "down")
            self._editor._inspector_cursor = (new_cursor.section_id, new_cursor.row_index)
            return True

        row = get_cursor_row(cursor, sections)
        if row is None:
            return False

        if row.kind == "header":
            if key in (
                optional_arcade.arcade.key.ENTER,
                optional_arcade.arcade.key.RETURN,
                optional_arcade.arcade.key.LEFT,
                optional_arcade.arcade.key.RIGHT,
                optional_arcade.arcade.key.SPACE,
            ):
                self._editor._inspector_sections_expanded = toggle_section(
                    self._editor._inspector_sections_expanded, row.key
                )
                return True
            return False

        if row.kind == "field" and row.editable:
            if row.field_kind in ("float", "int"):
                if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                    step = (
                        NUMERIC_STEP_SHIFT
                        if (modifiers & optional_arcade.arcade.key.MOD_SHIFT)
                        else NUMERIC_STEP_NORMAL
                    )
                    delta = -step if key == optional_arcade.arcade.key.LEFT else step
                    new_json, changed = apply_inspector_edit(
                        entity_json, cursor, sections, delta, is_text_commit=False
                    )
                    if changed:
                        self.apply_inspector_entity_update(new_json, row.key)
                    return True

            if row.field_kind == "string":
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    self.inspector_begin_text_edit(str(row.value or ""))
                    return True

            if row.field_kind == "bool":
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    new_json, changed = apply_inspector_edit(
                        entity_json, cursor, sections, True, is_text_commit=False
                    )
                    if changed:
                        self.apply_inspector_entity_update(new_json, row.key)
                    return True

        return False

    def handle_inspector_input(self, key: int, modifiers: int) -> bool:
        items = self.get_inspector_items()
        if not items:
            return False

        if key == optional_arcade.arcade.key.UP:
            self._editor.inspector_selection_index = max(
                0, self._editor.inspector_selection_index - 1
            )
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self._editor.inspector_selection_index = min(
                len(items) - 1, self._editor.inspector_selection_index + 1
            )
            return True

        selected_item = items[self._editor.inspector_selection_index]
        if key == optional_arcade.arcade.key.R and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
            if modifiers & optional_arcade.arcade.key.MOD_CTRL:
                return bool(self._editor._reset_all_prefab_overrides())
            return bool(self._editor._reset_selected_prefab_override(selected_item))
        if selected_item["type"] != "param":
            return False

        behaviour_name = selected_item["behaviour"]
        param_name = selected_item["name"]
        current_value = selected_item["value"]
        param_type = selected_item["kind"]

        new_value = current_value
        changed = False

        if param_type == "bool":
            if key in (
                optional_arcade.arcade.key.ENTER,
                optional_arcade.arcade.key.SPACE,
                optional_arcade.arcade.key.LEFT,
                optional_arcade.arcade.key.RIGHT,
            ):
                new_value = not current_value
                changed = True
        elif param_type in ("int", "float"):
            delta: float = 0.0
            if key == optional_arcade.arcade.key.LEFT:
                delta = -1 if param_type == "int" else -0.1
            elif key == optional_arcade.arcade.key.RIGHT:
                delta = 1 if param_type == "int" else 0.1

            if delta != 0:
                if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                    delta *= 10

                if param_type == "int":
                    new_value = int(current_value + delta)
                else:
                    new_value = round(current_value + delta, 2)
                changed = True

        if changed:
            self._editor._update_param(behaviour_name, param_name, new_value)
            self.refresh_inspector_items()
            return True

        return False

    def refresh_inspector_items(self) -> None:
        self._editor._cached_inspector_items = self.build_inspector_items()

    def get_inspector_items(self) -> list[dict[str, Any]]:
        if not self._editor._cached_inspector_items and self._editor.selected_entity:
            self.refresh_inspector_items()
        return cast(list[dict[str, Any]], self._editor._cached_inspector_items)

    def build_inspector_items(self) -> list[dict[str, Any]]:
        if not self._editor.selected_entity:
            return []

        items: list[dict[str, Any]] = []
        sprite = self._editor.selected_entity

        items.append(
            {
                "type": "header",
                "text": f"Entity: {getattr(sprite, 'mesh_name', '<unnamed>')}",
                "kind": "entity_header",
            }
        )

        behaviours = getattr(sprite, "mesh_behaviours", [])
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(sprite)
        config_root = self._editor.window.scene_controller._ensure_behaviour_config_root(
            entity_data
        )
        _base_entity, override_paths = self._editor._prefab_override_info(entity_data)

        for b_name in behaviours:
            items.append(
                {
                    "type": "header",
                    "text": f"Behaviour: {b_name}",
                    "kind": "behaviour_header",
                }
            )

            param_defs = get_behaviour_param_defs(b_name)
            current_config = config_root.get(b_name, {})

            all_keys = set(param_defs.keys()) | set(current_config.keys())
            sorted_keys = sorted(list(all_keys))

            for key in sorted_keys:
                if key in current_config:
                    val = current_config[key]
                    is_default = False
                elif key in param_defs:
                    val = param_defs[key].default
                    is_default = True
                else:
                    val = None
                    is_default = True

                kind = "string"
                if key in param_defs:
                    def_type = param_defs[key].type
                    if def_type in (int, "int"):
                        kind = "int"
                    elif def_type in (float, "float"):
                        kind = "float"
                    elif def_type in (bool, "bool"):
                        kind = "bool"
                else:
                    if isinstance(val, bool):
                        kind = "bool"
                    elif isinstance(val, int):
                        kind = "int"
                    elif isinstance(val, float):
                        kind = "float"

                items.append(
                    {
                        "type": "param",
                        "name": key,
                        "value": val,
                        "kind": kind,
                        "behaviour": b_name,
                        "is_default": is_default,
                        "is_override": f"behaviour_config.{b_name}.{key}" in override_paths,
                    }
                )

        return items

    def build_selection_overlay_lines(self) -> list[str]:
        editor = self._editor
        lines: list[str] = []
        if not editor.selected_entity:
            lines.append("No selection")
            return lines

        if editor.inspector_active:
            items = self.get_inspector_items()
            lines.extend(["[INSPECTOR ACTIVE]", "UP/DOWN: Select", "LEFT/RIGHT: Edit"])
            if any(item.get("is_override") for item in items if item.get("type") == "param"):
                lines.append("Shift+R: Reset override | Ctrl+Shift+R: Reset all")
            lines.append("----------------")

            if items:
                editor.inspector_selection_index = max(
                    0, min(editor.inspector_selection_index, len(items) - 1)
                )

            max_visible = 20
            start_idx = 0
            if editor.inspector_selection_index > max_visible / 2:
                start_idx = max(0, int(editor.inspector_selection_index - max_visible / 2))
            end_idx = min(len(items), start_idx + max_visible)

            for i in range(start_idx, end_idx):
                item = items[i]
                is_selected = (i == editor.inspector_selection_index)
                prefix = "> " if is_selected else "  "

                if item["type"] == "header":
                    lines.append(f"{prefix}{item['text']}")
                elif item["type"] == "param":
                    val_str = str(item["value"])
                    if item["kind"] == "bool":
                        val_str = "ON" if item["value"] else "OFF"
                    mod_marker = "!" if item.get("is_override") else ("" if item["is_default"] else "*")
                    lines.append(f"{prefix}  {item['name']}: {val_str} {mod_marker}")

            lines.append("----------------")
            return lines

        name = editor._get_display_name_for_sprite(editor.selected_entity)
        x = editor.selected_entity.center_x
        y = editor.selected_entity.center_y
        lines.append(f"Selected: {name}")
        lines.append(f"Pos: ({x:.1f}, {y:.1f})")
        tags = editor._get_entity_tags(editor.selected_entity)
        if tags:
            lines.append(f"Tags: {', '.join(tags)}")
        lines.append("(Press TAB to edit params)")
        return lines

    def get_selected_entity_json_for_inspector(self) -> dict[str, Any] | None:
        """Get the JSON data for the currently selected entity."""
        from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415

        primary_id = selected_entity_id(self._editor)
        if not primary_id:
            return None

        scene_controller = getattr(self._editor.window, "scene_controller", None)
        if scene_controller is None:
            return None

        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return None

        entities = loaded_data.get("entities", [])
        for ent in entities:
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == primary_id:
                    return ent

        return None

    def inspector_begin_text_edit(self, initial: str) -> None:
        self._editor._inspector_text_edit_active = True
        self._editor._inspector_text_buffer = initial

    def inspector_cancel_text_edit(self) -> None:
        self._editor._inspector_text_edit_active = False
        self._editor._inspector_text_buffer = ""

    def inspector_commit_text_edit(self) -> bool:
        if not self._editor._inspector_text_edit_active:
            return False

        from engine.editor.inspector_components_model import (
            InspectorCursor,
            apply_inspector_edit,
            build_inspector_sections,
            clamp_inspector_cursor,
            get_cursor_row,
        )

        entity_json = self.get_selected_entity_json_for_inspector()
        if entity_json is None:
            self.inspector_cancel_text_edit()
            return False

        sections = build_inspector_sections(
            entity_json, None, self._editor._inspector_sections_expanded
        )
        cursor = InspectorCursor(
            section_id=self._editor._inspector_cursor[0],
            row_index=self._editor._inspector_cursor[1],
        )
        cursor = clamp_inspector_cursor(cursor, sections)

        row = get_cursor_row(cursor, sections)
        if row is None or row.kind != "field":
            self.inspector_cancel_text_edit()
            return False

        new_json, changed = apply_inspector_edit(
            entity_json, cursor, sections, self._editor._inspector_text_buffer, is_text_commit=True
        )

        if changed:
            self.apply_inspector_entity_update(new_json, row.key)

        self.inspector_cancel_text_edit()
        return True

    def apply_inspector_entity_update(self, new_entity_json: dict[str, Any], field_key: str) -> None:
        """Apply entity JSON update, push undo command, and mark dirty."""
        if not self._editor.selected_entity:
            return

        old_json = self.get_selected_entity_json_for_inspector()
        if old_json is None:
            return

        from engine.editor.inspector_components_model import _get_nested_value  # noqa: PLC0415

        old_value = _get_nested_value(old_json, field_key)
        new_value = _get_nested_value(new_entity_json, field_key)

        self._editor._push_command(
            {
                "type": "InspectorEdit",
                "entity_id": self.get_entity_id_for_inspector(),
                "field_key": field_key,
                "before": old_value,
                "after": new_value,
            }
        )

        scene_controller = getattr(self._editor.window, "scene_controller", None)
        if scene_controller is None:
            return

        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return

        entity_id = self.get_entity_id_for_inspector()
        entities = loaded_data.get("entities", [])
        for i, ent in enumerate(entities):
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == entity_id:
                    entities[i] = new_entity_json
                    break

        self.apply_inspector_to_sprite(field_key, new_value)
        self._editor._mark_dirty()

    def get_entity_id_for_inspector(self) -> str | None:
        from engine.editor.editor_selection_model import selected_entity_id  # noqa: PLC0415

        return selected_entity_id(self._editor)

    def apply_inspector_to_sprite(self, field_key: str, value: Any) -> None:
        if not self._editor.selected_entity:
            return

        sprite = self._editor.selected_entity

        if field_key == "x":
            self._editor.window.scene_controller._apply_entity_mutation(sprite, x=float(value))
        elif field_key == "y":
            self._editor.window.scene_controller._apply_entity_mutation(sprite, y=float(value))
        elif field_key == "rotation":
            try:
                rotation = float(value) % 360.0
            except (ValueError, TypeError):
                return
            sprite.angle = rotation
            entity_data = getattr(sprite, "mesh_entity_data", {})
            if isinstance(entity_data, dict):
                entity_data["rotation"] = rotation
        elif field_key == "scale":
            try:
                scale = float(value)
            except (ValueError, TypeError):
                return
            sprite.scale = scale
            entity_data = getattr(sprite, "mesh_entity_data", {})
            if isinstance(entity_data, dict):
                entity_data["scale"] = scale

    def handle_inspector_text_input(self, text: str) -> bool:
        if self._editor._inspector_text_edit_active:
            if text and text.isprintable():
                self._editor._inspector_text_buffer += text
                return True
        return False

    def handle_component_inspector_v1_input(self, key: int, modifiers: int) -> bool:
        """Handle keyboard input for component inspector v1 navigation and editing."""
        snapshot = get_dock_snapshot(self._editor)
        if snapshot is None or snapshot.right_tab != "Inspector":
            return False
        if not self._editor.selected_entity:
            return False

        from engine.editor.components_model import (
            COMPONENT_TITLES,
            ComponentKind,
            add_component,
            build_components,
            get_addable_components,
            remove_component,
        )
        from engine.editor.components_ops import (
            apply_inspector_delta,
            get_step_for_field,
            reset_field_to_default,
        )
        from engine.editor.entity_panels import (
            get_component_inspector_row_count,
            resolve_component_inspector_selection,
        )

        entity_json = self.get_selected_entity_json_for_inspector()
        if entity_json is None:
            return False

        if self._editor._add_component_picker_active:
            return self.handle_add_component_picker_input(key, entity_json)

        components = build_components(entity_json, self._editor.selected_entity)
        row_count = get_component_inspector_row_count(components, include_add_row=True)

        if row_count > 0:
            self._editor._component_inspector_index = max(
                0, min(self._editor._component_inspector_index, row_count - 1)
            )
        else:
            self._editor._component_inspector_index = 0

        selection = resolve_component_inspector_selection(
            components, self._editor._component_inspector_index
        )

        if self._editor._inspector_text_edit_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return self.component_inspector_commit_text_edit(entity_json, selection)
            if key == optional_arcade.arcade.key.ESCAPE:
                self.inspector_cancel_text_edit()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor._inspector_text_buffer = self._editor._inspector_text_buffer[:-1]
                return True
            return True

        if key == optional_arcade.arcade.key.UP:
            self._editor._component_inspector_index = max(
                0, self._editor._component_inspector_index - 1
            )
            return True

        if key == optional_arcade.arcade.key.DOWN:
            self._editor._component_inspector_index = min(
                row_count - 1, self._editor._component_inspector_index + 1
            )
            return True

        if selection is None:
            return False

        sel_type = selection.get("type")

        if sel_type == "header":
            comp_kind = selection.get("component_kind")
            removable = selection.get("removable", False)
            if key in (optional_arcade.arcade.key.DELETE, optional_arcade.arcade.key.BACKSPACE):
                if removable and comp_kind:
                    new_json = remove_component(entity_json, comp_kind)
                    self.apply_component_entity_update(new_json)
                    return True
            return False

        if sel_type == "field":
            comp_kind = selection.get("component_kind")
            field_key = selection.get("field_key")
            field = selection.get("field")

            if not field or not field.editable:
                return False
            if not isinstance(comp_kind, str) or not isinstance(field_key, str):
                return False
            comp_kind_t = cast(ComponentKind, comp_kind)
            field_key_t = field_key

            if key == optional_arcade.arcade.key.R:
                new_json = reset_field_to_default(entity_json, comp_kind_t, field_key_t)
                self.apply_component_entity_update(new_json)
                return True

            if field.kind in ("float", "int"):
                if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                    step = get_step_for_field(comp_kind_t, field_key_t)
                    delta = -step if key == optional_arcade.arcade.key.LEFT else step
                    shift = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
                    new_json = apply_inspector_delta(entity_json, comp_kind_t, field_key_t, delta, shift)
                    self.apply_component_entity_update(new_json)
                    return True

            if field.kind == "enum":
                if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                    delta = -1.0 if key == optional_arcade.arcade.key.LEFT else 1.0
                    new_json = apply_inspector_delta(entity_json, comp_kind_t, field_key_t, delta, False)
                    self.apply_component_entity_update(new_json)
                    return True

            if field.kind == "bool":
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    new_json = apply_inspector_delta(entity_json, comp_kind_t, field_key_t, 1.0, False)
                    self.apply_component_entity_update(new_json)
                    return True

            if field.kind in ("string", "asset"):
                if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                    self.inspector_begin_text_edit(str(field.value or ""))
                    return True

            return False

        if sel_type == "add_row":
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                addable = get_addable_components(entity_json)
                if addable:
                    self._editor._add_component_picker_active = True
                    self._editor._add_component_picker_index = 0
                    self._editor._add_component_picker_options = list(addable)
                return True

        return False

    def handle_add_component_picker_input(self, key: int, entity_json: Dict[str, Any]) -> bool:
        from engine.editor.components_model import ComponentKind, add_component  # noqa: PLC0415

        if key == optional_arcade.arcade.key.ESCAPE:
            self._editor._add_component_picker_active = False
            return True

        if key == optional_arcade.arcade.key.UP:
            self._editor._add_component_picker_index = max(
                0, self._editor._add_component_picker_index - 1
            )
            return True

        if key == optional_arcade.arcade.key.DOWN:
            max_idx = len(self._editor._add_component_picker_options) - 1
            self._editor._add_component_picker_index = min(
                max_idx, self._editor._add_component_picker_index + 1
            )
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            if 0 <= self._editor._add_component_picker_index < len(
                self._editor._add_component_picker_options
            ):
                kind = self._editor._add_component_picker_options[
                    self._editor._add_component_picker_index
                ]
                kind_t = cast(ComponentKind, kind)
                new_json = add_component(entity_json, kind_t)
                self.apply_component_entity_update(new_json)
            self._editor._add_component_picker_active = False
            return True

        return True

    def component_inspector_commit_text_edit(
        self, entity_json: Dict[str, Any], selection: Optional[Dict[str, Any]]
    ) -> bool:
        if not self._editor._inspector_text_edit_active:
            return False
        if selection is None or selection.get("type") != "field":
            self.inspector_cancel_text_edit()
            return False

        from engine.editor.components_model import set_component_field  # noqa: PLC0415

        comp_kind = selection.get("component_kind")
        field_key = selection.get("field_key")
        field = selection.get("field")

        if not comp_kind or not field_key:
            self.inspector_cancel_text_edit()
            return False

        new_value: Any = self._editor._inspector_text_buffer
        if field and field.kind == "float":
            try:
                new_value = float(self._editor._inspector_text_buffer)
            except ValueError:
                self.inspector_cancel_text_edit()
                return False
        elif field and field.kind == "int":
            try:
                new_value = int(self._editor._inspector_text_buffer)
            except ValueError:
                self.inspector_cancel_text_edit()
                return False

        new_json = set_component_field(entity_json, comp_kind, field_key, new_value)
        self.apply_component_entity_update(new_json)
        self.inspector_cancel_text_edit()
        return True

    def apply_component_entity_update(self, new_entity_json: Dict[str, Any]) -> None:
        if not self._editor.selected_entity:
            return

        entity_id = self.get_entity_id_for_inspector()
        if not entity_id:
            return

        scene_controller = getattr(self._editor.window, "scene_controller", None)
        if scene_controller is None:
            return

        loaded_data = getattr(scene_controller, "_loaded_scene_data", None)
        if not isinstance(loaded_data, dict):
            return

        entities = loaded_data.get("entities", [])
        for i, ent in enumerate(entities):
            if isinstance(ent, dict):
                ent_id = ent.get("id") or ent.get("mesh_name") or ent.get("name")
                if ent_id == entity_id:
                    entities[i] = new_entity_json
                    break

        sync_runtime = getattr(self._editor, "_sync_sprite_from_component_json", None)
        if callable(sync_runtime):
            sync_runtime(new_entity_json)

        self._editor._mark_dirty()
        self._editor._refresh_entity_panels_list(sync_selected=True)

    # ------------------------------------------------------------------
    # Behaviour Parameter Editing (extracted from editor_controller.py)
    # ------------------------------------------------------------------

    def update_param(self, behaviour_name: str, param_name: str, value: Any) -> None:
        """Update a behaviour parameter with undo support."""
        editor = self._editor
        if not editor.selected_entity:
            return

        entity_name = getattr(editor.selected_entity, "mesh_name", "")

        # Get old value for undo
        entity_data = editor.window.scene_controller._ensure_entity_data_dict(editor.selected_entity)
        config_root = editor.window.scene_controller._ensure_behaviour_config_root(entity_data)
        current_config = config_root.get(behaviour_name, {})
        old_value = current_config.get(param_name)

        # If not in config, check param defs default
        if old_value is None:
            param_defs = get_behaviour_param_defs(behaviour_name)
            if param_name in param_defs:
                old_value = param_defs[param_name].default

        self.update_param_internal(behaviour_name, param_name, value, entity_name)

        editor._push_command({
            "type": "ChangeProperty",
            "entity_name": entity_name,
            "behaviour": behaviour_name,
            "param": param_name,
            "before": old_value,
            "after": value
        })

    def update_param_internal(self, behaviour_name: str, param_name: str, value: Any, entity_name: str) -> None:
        """Update behaviour parameter without undo (for undo/redo replay)."""
        editor = self._editor
        entity = editor._find_entity_by_name(entity_name)
        if not entity and editor.selected_entity:
            selected_name = getattr(editor.selected_entity, "mesh_name", "") or ""
            if not entity_name or selected_name == entity_name:
                entity = editor.selected_entity
        if not entity:
            return

        # 1. Update Entity Data (for saving)
        entity_data = editor.window.scene_controller._ensure_entity_data_dict(entity)
        config_root = editor.window.scene_controller._ensure_behaviour_config_root(entity_data)
        behaviour_config = config_root.setdefault(behaviour_name, {})
        behaviour_config[param_name] = value

        # Also update the list-based config if present (legacy/mixed support)
        entries = editor.window.scene_controller._get_behaviour_configs_for_sprite(entity)
        behaviour_index = -1
        for idx, entry in enumerate(entries):
            if entry.get("type") == behaviour_name:
                behaviour_index = idx
                params = entry.setdefault("params", {})
                if isinstance(params, dict):
                    params[param_name] = value
                break

        # 2. Update Runtime Instance
        runtime_behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        if 0 <= behaviour_index < len(runtime_behaviours):
            behaviour = runtime_behaviours[behaviour_index]

            # Update config dict on behaviour
            if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
                behaviour.config[param_name] = value

            # Update attribute if it exists
            if hasattr(behaviour, param_name):
                setattr(behaviour, param_name, value)

            # Call hook
            if hasattr(behaviour, "on_config_updated") and callable(behaviour.on_config_updated):
                try:
                    behaviour.on_config_updated(param_name, value)
                except Exception as e:
                    logger.error("[Editor] Error updating behaviour: %s", e)

    def remove_param_internal(self, behaviour_name: str, param_name: str, entity_name: str) -> None:
        """Remove a behaviour parameter (for undo/redo)."""
        editor = self._editor
        entity = editor._find_entity_by_name(entity_name)
        if not entity and editor.selected_entity:
            selected_name = getattr(editor.selected_entity, "mesh_name", "") or ""
            if not entity_name or selected_name == entity_name:
                entity = editor.selected_entity
        if not entity:
            return

        entity_data = editor.window.scene_controller._ensure_entity_data_dict(entity)
        config_root = editor.window.scene_controller._ensure_behaviour_config_root(entity_data)
        behaviour_config = config_root.get(behaviour_name)
        if isinstance(behaviour_config, dict):
            behaviour_config.pop(param_name, None)
            if not behaviour_config:
                config_root.pop(behaviour_name, None)

        entries = editor.window.scene_controller._get_behaviour_configs_for_sprite(entity)
        for entry in entries:
            if entry.get("type") == behaviour_name:
                params = entry.get("params")
                if isinstance(params, dict):
                    params.pop(param_name, None)
                break

        runtime_behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        for behaviour in runtime_behaviours:
            if getattr(behaviour, "mesh_behaviour_type", None) == behaviour_name:
                if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
                    behaviour.config.pop(param_name, None)
                if hasattr(behaviour, param_name):
                    try:
                        setattr(behaviour, param_name, None)
                    except Exception:
                        pass
                if hasattr(behaviour, "on_config_updated") and callable(behaviour.on_config_updated):
                    try:
                        behaviour.on_config_updated(param_name, None)
                    except Exception as e:
                        logger.error("[Editor] Error updating behaviour: %s", e)

    def apply_behaviour_config_map(self, entity: optional_arcade.arcade.Sprite, config_map: dict[str, Any]) -> None:
        """Apply a full behaviour config map to an entity (for undo/redo)."""
        editor = self._editor
        entity_data = editor.window.scene_controller._ensure_entity_data_dict(entity)
        entity_data["behaviour_config"] = copy.deepcopy(config_map)

        entries = editor.window.scene_controller._get_behaviour_configs_for_sprite(entity)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            behaviour_type = entry.get("type")
            if not isinstance(behaviour_type, str):
                continue
            params = config_map.get(behaviour_type, {})
            if isinstance(params, dict):
                entry["params"] = copy.deepcopy(params)

        runtime_behaviours = getattr(entity, "mesh_behaviours_runtime", [])
        for behaviour in runtime_behaviours:
            behaviour_type = getattr(behaviour, "mesh_behaviour_type", None)
            if not isinstance(behaviour_type, str):
                continue
            params = config_map.get(behaviour_type, {})
            if isinstance(params, dict):
                if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
                    behaviour.config.clear()
                    behaviour.config.update(copy.deepcopy(params))
                for key, value in params.items():
                    if hasattr(behaviour, key):
                        try:
                            setattr(behaviour, key, value)
                        except Exception:
                            pass
                if hasattr(behaviour, "on_config_updated") and callable(behaviour.on_config_updated):
                    for key, value in params.items():
                        try:
                            behaviour.on_config_updated(key, value)
                        except Exception as e:
                            logger.error("[Editor] Error updating behaviour: %s", e)

    def get_prefab_base_entity(self, entity_data: dict[str, Any]) -> dict[str, Any] | None:
        """Get the base prefab entity data for comparison."""
        prefab_id = entity_data.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            return None
        variant_id = entity_data.get("variant_id")
        try:
            from engine.prefabs import get_prefab_manager  # noqa: PLC0415

            resolved = get_prefab_manager().resolve_with_variant(prefab_id.strip(), variant_id)
        except Exception:
            return None
        if not isinstance(resolved, dict):
            return None
        base_entity = resolved.get("entity")
        if not isinstance(base_entity, dict):
            return None
        return base_entity
