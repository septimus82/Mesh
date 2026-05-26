from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade


class EditorInspectorInputController:
    """Mouse input routing for Inspector dock content."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        editor = self._editor
        if not getattr(editor, "active", False):
            return False
        if not self._is_inspector_tab():
            return False

        dock = self._right_dock()
        if dock is None or not dock.contains_point(float(x), float(y)):
            return False
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        if self._has_entity_selection():
            return self._handle_component_inspector_click(float(x), float(y))
        return self._handle_hd2d_scene_panel_click(float(x), float(y))

    def _is_inspector_tab(self) -> bool:
        dock = getattr(self._editor, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        return (getattr(snapshot, "right_tab", "Inspector") or "Inspector") == "Inspector"

    def _right_dock(self) -> Any | None:
        from engine.editor.editor_dock_query import get_effective_dock_widths
        from engine.editor.editor_shell_layout import compute_editor_shell_layout

        window = getattr(self._editor, "window", None)
        window_w = int(getattr(window, "width", 1280) or 1280)
        window_h = int(getattr(window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(self._editor, window_w)
        return compute_editor_shell_layout(window_w, window_h, left_w, right_w).right_dock

    def _has_entity_selection(self) -> bool:
        primary_id = getattr(self._editor, "_primary_selected_id", None)
        selected_ids = getattr(self._editor, "_selected_entity_ids", [])
        return bool(primary_id) or (isinstance(selected_ids, list) and bool(selected_ids))

    def _handle_hd2d_scene_panel_click(self, x: float, y: float) -> bool:
        hit = self._hit_hd2d_scene_row(x, y)
        if hit is None:
            return True
        row, bounds = hit

        if row.kind == "header":
            expanded = dict(getattr(self._editor, "_hd2d_panel_sections_expanded", {}) or {})
            expanded[row.key] = not expanded.get(row.key, True)
            self._editor._hd2d_panel_sections_expanded = expanded
            return True

        if row.kind == "toggle":
            self._toggle_hd2d_setting(str(row.key))
            return True

        if row.kind == "presets":
            preset_id = self._hit_hd2d_preset_button(x, y, bounds)
            if preset_id:
                self._apply_hd2d_preset(preset_id)
            return True

        return True

    def _hit_hd2d_scene_row(self, x: float, y: float) -> tuple[Any, tuple[float, float, float, float]] | None:
        from engine.ui_overlays.hd2d_settings_panel_overlay import (
            LINE_HEIGHT,
            PADDING,
            ROW_HEIGHT,
            SECTION_GAP,
            TAB_HEADER_HEIGHT,
            _build_panel_rows,
        )

        dock = self._right_dock()
        if dock is None:
            return None
        scene = self._scene_payload()
        settings = scene.get("settings") if isinstance(scene.get("settings"), dict) else {}
        rows = _build_panel_rows(settings)
        sections_expanded = getattr(self._editor, "_hd2d_panel_sections_expanded", {}) or {}

        content_left = dock.left + PADDING
        content_width = dock.width - 2 * PADDING
        top = dock.top - TAB_HEADER_HEIGHT - PADDING - LINE_HEIGHT - SECTION_GAP
        section_is_expanded = True

        for row in rows:
            if row.kind == "header":
                section_is_expanded = bool(sections_expanded.get(row.key, True))
            elif not section_is_expanded:
                continue

            bottom = top - ROW_HEIGHT
            if content_left <= x <= content_left + content_width and bottom <= y <= top:
                return row, (content_left, top, content_width, ROW_HEIGHT)
            top = bottom - 2
            if top < dock.bottom + PADDING:
                break
        return None

    def _hit_hd2d_preset_button(
        self,
        x: float,
        y: float,
        bounds: tuple[float, float, float, float],
    ) -> str | None:
        from engine.editor.hd2d_look_presets_model import list_hd2d_presets
        from engine.ui_overlays.hd2d_settings_panel_overlay import ROW_HEIGHT

        left, top, width, _height = bounds
        presets = list_hd2d_presets()
        if not presets:
            return None
        btn_width = (width - 16) / max(len(presets), 1) - 4
        btn_height = ROW_HEIGHT - 4
        btn_y = top - ROW_HEIGHT / 2
        btn_left = left + 8
        for preset in presets:
            btn_right = btn_left + btn_width
            if btn_left <= x <= btn_right and btn_y - btn_height / 2 <= y <= btn_y + btn_height / 2:
                return str(preset.id)
            btn_left += btn_width + 4
        return None

    def _handle_component_inspector_click(self, x: float, y: float) -> bool:
        from engine.editor.editor_shell_layout import TAB_HEADER_HEIGHT
        from engine.editor.inspector_components_model import build_inspector_sections
        from engine.ui_overlays.component_inspector_overlay import LINE_HEIGHT, PADDING, SECTION_HEADER_HEIGHT

        dock = self._right_dock()
        if dock is None:
            return True
        entity_json = self._selected_entity_json()
        if entity_json is None:
            return True

        expanded = getattr(self._editor, "_inspector_sections_expanded", {}) or {}
        sections = build_inspector_sections(entity_json, None, expanded)
        left = dock.left + PADDING
        right = dock.right - PADDING
        if not left <= x <= right:
            return True

        top = dock.top - TAB_HEADER_HEIGHT - PADDING
        for section in sections:
            for row_index, row in enumerate(section.visible_rows):
                height = SECTION_HEADER_HEIGHT if row.kind == "header" else LINE_HEIGHT
                bottom = top - height
                if bottom <= y <= top:
                    self._editor._inspector_cursor = (section.id, row_index)
                    return True
                top = bottom
            if top < dock.bottom + PADDING:
                break
        return True

    def _toggle_hd2d_setting(self, key: str) -> None:
        from engine.editor.editor_actions_parts.hd2d_actions import _toggle_hd2d_setting

        window = getattr(self._editor, "window", None)
        if window is not None:
            _toggle_hd2d_setting(window, key)

    def _apply_hd2d_preset(self, preset_id: str) -> None:
        from engine.editor.editor_actions_parts.hd2d_actions import _apply_hd2d_preset

        window = getattr(self._editor, "window", None)
        if window is not None:
            _apply_hd2d_preset(window, preset_id)

    def _scene_payload(self) -> dict[str, Any]:
        window = getattr(self._editor, "window", None)
        scene_controller = getattr(window, "scene_controller", None)
        scene = getattr(scene_controller, "_loaded_scene_data", None)
        return scene if isinstance(scene, dict) else {}

    def _selected_entity_json(self) -> dict[str, Any] | None:
        getter = getattr(self._editor, "_get_selected_entity_json_for_inspector", None)
        if callable(getter):
            entity = getter()
            if isinstance(entity, dict):
                return entity

        primary_id = getattr(self._editor, "_primary_selected_id", None)
        if not primary_id:
            return None
        entities = self._scene_payload().get("entities", [])
        iterable = entities.values() if isinstance(entities, dict) else entities
        for entity in iterable:
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("id") or entity.get("mesh_name") or entity.get("name")
            if entity_id == primary_id:
                return entity
        return None
