from __future__ import annotations

from typing import Any, Dict, List, Optional, cast
import logging

import engine.optional_arcade as optional_arcade

from engine.editor_entity_ops import EntitySummary, list_entities, update_entity_field
from engine.editor.entity_panels import (
    build_inspector_lines,
    build_outliner_lines,
    clamp_entity_panels_index,
    filter_entity_panels_items,
    format_entity_field_value,
    get_entity_numeric_value,
    resolve_entity_panels_id,
)
from engine.editor.prefab_palette_panel import (
    apply_entity_panel_tag_delta,
    normalize_entity_panel_tags,
)
from engine.editor.state import ENTITY_PANEL_FIELDS, ENTITY_PANEL_FOCUS_INSPECTOR, ENTITY_PANEL_FOCUS_OUTLINER


class EditorEntityPanelsController:
    """Encapsulates entity panels (outliner/inspector) behavior."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def toggle_entity_panels(self) -> bool:
        editor = self._editor
        if not getattr(editor, "active", False):
            return False
        editor.entity_panels_active = not editor.entity_panels_active
        if editor.entity_panels_active:
            editor.entity_panels_focus = ENTITY_PANEL_FOCUS_OUTLINER
            editor.entity_panels_filter_active = False
            editor.entity_panels_text_edit_active = False
            editor.entity_panels_text_field = None
            editor.entity_panels_text_buffer = ""
            editor._entity_panels_selected_id = self.entity_panels_selected_id_value()
            self.refresh_entity_panels_list(sync_selected=True)
            logging.getLogger(__name__).info("[Editor] Entity panels OPEN")
        else:
            editor.entity_panels_filter_active = False
            editor.entity_panels_text_edit_active = False
            editor.entity_panels_text_field = None
            editor.entity_panels_text_buffer = ""
            search = getattr(editor, "search", None)
            if search is not None and search.is_panel_search_focused("outliner"):
                search.clear_search_focus()
            logging.getLogger(__name__).info("[Editor] Entity panels CLOSED")
        autosave = getattr(editor, "_autosave_workspace", None)
        if callable(autosave):
            autosave()
        return bool(editor.entity_panels_active)

    def entity_panels_scene_data(self) -> Dict[str, Any]:
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        return scene

    def resolve_entity_panels_id(self, entity: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
        return resolve_entity_panels_id(entity, fallback_index)

    def entity_panels_selected_id_value(self) -> str | None:
        sprite = self._editor.selected_entity
        if sprite is None:
            return None
        entity_data = getattr(sprite, "mesh_entity_data", None)
        fallback_index = self.get_sprite_index(sprite)
        if isinstance(entity_data, dict):
            return self.resolve_entity_panels_id(entity_data, fallback_index)
        mesh_name = getattr(sprite, "mesh_name", None)
        if isinstance(mesh_name, str) and mesh_name.strip():
            return mesh_name.strip()
        if fallback_index is not None:
            return f"idx:{int(fallback_index)}"
        return None

    def filter_entity_panels_items(self, items: list[EntitySummary]) -> list[EntitySummary]:
        filter_text = str(self._editor.search.get_outliner_search() or "")
        return filter_entity_panels_items(items, filter_text)

    def refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:
        items = list_entities(self.entity_panels_scene_data())
        items = self.filter_entity_panels_items(items)
        self._editor._cached_entity_panels_list = items
        count = len(items)
        if count == 0:
            self._editor.entity_panels_selection_index = -1
            self._editor._entity_panels_selected_id = self.entity_panels_selected_id_value()
            return

        if self._editor.entity_panels_selection_index < 0:
            self._editor.entity_panels_selection_index = 0
        self._editor.entity_panels_selection_index = clamp_entity_panels_index(
            self._editor.entity_panels_selection_index, count
        )

        current_selected_id = self.entity_panels_selected_id_value()
        if sync_selected or current_selected_id != self._editor._entity_panels_selected_id:
            if current_selected_id:
                for i, summary in enumerate(items):
                    if summary.id == current_selected_id:
                        self._editor.entity_panels_selection_index = i
                        break
            self._editor._entity_panels_selected_id = current_selected_id

    def get_entity_panels_list(self) -> list[EntitySummary]:
        if not self._editor._cached_entity_panels_list:
            self.refresh_entity_panels_list()
        return cast(list[EntitySummary], self._editor._cached_entity_panels_list)

    def resolve_display_name(self, sprite: optional_arcade.arcade.Sprite, fallback_index: Optional[int] = None) -> str:
        def _normalize(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                value = str(value)
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    return candidate
            return None

        entity_data = getattr(sprite, "mesh_entity_data", None)
        candidates: List[Any] = []
        if isinstance(entity_data, dict):
            candidates.extend(
                [
                    entity_data.get("name"),
                    entity_data.get("display_name"),
                    entity_data.get("id"),
                    entity_data.get("tag"),
                ]
            )

        candidates.extend(
            [
                getattr(sprite, "mesh_name", None),
                getattr(sprite, "name", None),
                getattr(sprite, "mesh_tag", None),
            ]
        )

        for entry in candidates:
            normalized = _normalize(entry)
            if normalized:
                return normalized

        if fallback_index is None:
            fallback_index = self.get_sprite_index(sprite)

        index_value = (fallback_index or 0) + 1
        tag_hint = None
        if isinstance(entity_data, dict):
            tag_hint = _normalize(entity_data.get("tag"))
        if not tag_hint:
            tag_hint = _normalize(getattr(sprite, "mesh_tag", None))

        base_label = tag_hint or "Entity"
        return f"{base_label}#{index_value}"

    def get_sprite_index(self, sprite: optional_arcade.arcade.Sprite) -> Optional[int]:
        try:
            return list(self._editor.window.scene_controller.all_sprites).index(sprite)
        except ValueError:
            return None

    def get_display_name_for_sprite(self, sprite: optional_arcade.arcade.Sprite) -> str:
        return self._editor._hierarchy_name_cache.get(id(sprite)) or self.resolve_display_name(sprite)

    def entity_panels_outliner_lines(self) -> list[str]:
        if not self._editor.entity_panels_active:
            return []

        self.refresh_entity_panels_list()
        return build_outliner_lines(
            active=self._editor.entity_panels_active,
            focus=self._editor.entity_panels_focus,
            search_text=self._editor.search.get_outliner_search(),
            search_focused=self._editor.search.is_panel_search_focused("outliner"),
            items=self._editor._cached_entity_panels_list,
            cursor_index=self._editor.entity_panels_selection_index,
            selected_id=self.entity_panels_selected_id_value(),
        )

    def entity_panels_inspector_lines(self) -> list[str]:
        if not self._editor.entity_panels_active:
            return []

        sprite = self._editor.selected_entity
        sprite_name = self.get_display_name_for_sprite(sprite) if sprite else None
        entity_data = (
            self._editor.window.scene_controller._ensure_entity_data_dict(sprite)
            if sprite
            else {}
        )
        prefab_label = self._editor._prefab_variant_label(entity_data) if sprite else None
        override_rows = self._editor._prefab_variant_override_rows(entity_data) if sprite else []
        total_rows = len(ENTITY_PANEL_FIELDS) + len(override_rows)
        if total_rows:
            self._editor.entity_panels_inspector_index = max(
                0,
                min(self._editor.entity_panels_inspector_index, total_rows - 1),
            )
        return build_inspector_lines(
            active=self._editor.entity_panels_active,
            focus=self._editor.entity_panels_focus,
            text_edit_active=self._editor.entity_panels_text_edit_active,
            sprite_name=sprite_name,
            entity_data=entity_data,
            inspector_index=self._editor.entity_panels_inspector_index,
            text_field=self._editor.entity_panels_text_field,
            text_buffer=self._editor.entity_panels_text_buffer,
            sprite=sprite,
            prefab_label=prefab_label,
            override_rows=override_rows,
        )

    def entity_panels_format_field_value(
        self,
        entity_data: Dict[str, Any],
        sprite: optional_arcade.arcade.Sprite,
        key: str,
        kind: str,
    ) -> str:
        return format_entity_field_value(entity_data, sprite, key, kind)

    def entity_panels_numeric_value(
        self,
        entity_data: Dict[str, Any],
        sprite: optional_arcade.arcade.Sprite,
        key: str,
    ) -> float:
        return get_entity_numeric_value(entity_data, sprite, key)

    def entity_panels_select_current(self) -> bool:
        items = self._editor._cached_entity_panels_list
        if not items:
            return False
        idx = clamp_entity_panels_index(self._editor.entity_panels_selection_index, len(items))
        summary = items[idx]
        target = self.entity_panels_find_sprite(summary)
        if target is None:
            return False
        from engine.editor_runtime.state import apply_selection  # noqa: PLC0415

        apply_selection(self._editor, target)
        self._editor._entity_panels_selected_id = self.entity_panels_selected_id_value()
        self.refresh_entity_panels_list(sync_selected=True)
        return True

    def entity_panels_find_sprite(
        self, summary: EntitySummary
    ) -> Optional[optional_arcade.arcade.Sprite]:
        sprite = self._editor._find_entity_by_id(summary.id)
        if sprite is not None:
            return sprite
        sprite = self._editor._find_entity_by_name(summary.id)
        if sprite is not None:
            return sprite
        if summary.id.startswith("idx:"):
            try:
                idx = int(summary.id.split(":", 1)[1])
            except Exception:  # noqa: BLE001
                idx = -1
            if idx >= 0:
                try:
                    all_sprites = list(self._editor.window.scene_controller.all_sprites)
                    if idx < len(all_sprites):
                        return all_sprites[idx]
                except Exception:  # noqa: BLE001
                    pass
            scene = self.entity_panels_scene_data()
            entities = scene.get("entities")
            if isinstance(entities, list) and 0 <= idx < len(entities):
                entity = entities[idx]
                if isinstance(entity, dict):
                    alt_id = self.resolve_entity_panels_id(entity, idx)
                    sprite = self._editor._find_entity_by_id(alt_id) or self._editor._find_entity_by_name(alt_id)
                    if sprite is not None:
                        return sprite
        return None

    def entity_panels_begin_text_edit(self, field: str, initial: str) -> None:
        self._editor.entity_panels_text_edit_active = True
        self._editor.entity_panels_text_field = field
        self._editor.entity_panels_text_buffer = initial

    def entity_panels_cancel_text_edit(self) -> None:
        self._editor.entity_panels_text_edit_active = False
        self._editor.entity_panels_text_field = None
        self._editor.entity_panels_text_buffer = ""

    def entity_panels_commit_text_edit(self) -> bool:
        if not self._editor.entity_panels_text_edit_active or not self._editor.entity_panels_text_field:
            return False
        field = self._editor.entity_panels_text_field
        value = self._editor.entity_panels_text_buffer
        if field.startswith("prefab_override:"):
            key = field.split("prefab_override:", 1)[1]
            applied = bool(self._editor._entity_panels_apply_prefab_override(key, value))
        else:
            applied = bool(self.entity_panels_apply_field_update(field, value))
        self.entity_panels_cancel_text_edit()
        return bool(applied)

    def entity_panels_apply_field_update(self, field: str, value: Any) -> bool:
        if not self._editor.selected_entity:
            return False
        entity_id = self.entity_panels_selected_id_value()
        if not entity_id:
            return False
        update_entity_field(self.entity_panels_scene_data(), entity_id, field, value)

        sprite = self._editor.selected_entity
        entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(sprite)
        key = str(field or "").strip().lower()

        if key in {"x", "y"}:
            try:
                numeric = float(value)
            except Exception:  # noqa: BLE001
                return False
            if key == "x":
                self._editor.window.scene_controller._apply_entity_mutation(sprite, x=numeric)
            else:
                self._editor.window.scene_controller._apply_entity_mutation(sprite, y=numeric)
        elif key == "mesh_name":
            new_name = str(value or "")
            entity_data["mesh_name"] = new_name
            setattr(sprite, "mesh_name", new_name)
            if id(sprite) in self._editor._hierarchy_name_cache:
                self._editor._hierarchy_name_cache[id(sprite)] = new_name
        elif key == "interact_label":
            entity_data["interact_label"] = str(value or "")
        elif key in {"rotation_deg", "rotation"}:
            try:
                rotation = float(value) % 360.0
            except Exception:  # noqa: BLE001
                return False
            entity_data["rotation"] = rotation
            sprite.angle = rotation
        elif key in {"tags", "tags_add", "tags_remove"}:
            tags = normalize_entity_panel_tags(entity_data.get("tags"))
            if key == "tags_add":
                tags = apply_entity_panel_tag_delta(tags, add=normalize_entity_panel_tags(value))
            elif key == "tags_remove":
                tags = apply_entity_panel_tag_delta(tags, remove=normalize_entity_panel_tags(value))
            elif isinstance(value, dict):
                add = normalize_entity_panel_tags(value.get("add"))
                remove = normalize_entity_panel_tags(value.get("remove"))
                tags = apply_entity_panel_tag_delta(tags, add=add, remove=remove)
            else:
                tags = normalize_entity_panel_tags(value)
            entity_data["tags"] = tags
        else:
            return False

        self._editor._mark_dirty()
        self.refresh_entity_panels_list(sync_selected=True)
        return True

    def handle_entity_panels_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.entity_panels_active:
            return False

        if self._editor.entity_panels_text_edit_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return self.entity_panels_commit_text_edit()
            if key == optional_arcade.arcade.key.ESCAPE:
                self.entity_panels_cancel_text_edit()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.entity_panels_text_buffer = self._editor.entity_panels_text_buffer[:-1]
                return True
            return True

        if (
            self._editor.search.is_panel_search_focused("outliner")
            and self._editor.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER
        ):
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                return bool(self._editor.search.backspace_search_text())
            return True

        if key == optional_arcade.arcade.key.TAB:
            if self._editor.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER:
                self._editor.entity_panels_focus = ENTITY_PANEL_FOCUS_INSPECTOR
            else:
                self._editor.entity_panels_focus = ENTITY_PANEL_FOCUS_OUTLINER
            return True

        if self._editor.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER:
            if key == optional_arcade.arcade.key.UP:
                self._editor.entity_panels_selection_index = max(
                    0, self._editor.entity_panels_selection_index - 1
                )
                return True
            if key == optional_arcade.arcade.key.DOWN:
                count = len(self._editor._cached_entity_panels_list)
                if count:
                    self._editor.entity_panels_selection_index = min(
                        count - 1, self._editor.entity_panels_selection_index + 1
                    )
                return True
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                if self._editor.search.is_panel_search_focused("outliner"):
                    return True
                return self.entity_panels_select_current()
            if key == optional_arcade.arcade.key.SLASH or (
                key == optional_arcade.arcade.key.F
                and (modifiers & optional_arcade.arcade.key.MOD_CTRL)
            ):
                return bool(self._editor.search.focus_search_for_active_panel())
            return False

        if self._editor.entity_panels_focus == ENTITY_PANEL_FOCUS_INSPECTOR:
            if not self._editor.selected_entity:
                return False
            override_rows = self._editor._entity_panels_prefab_override_rows()
            field_count = len(ENTITY_PANEL_FIELDS)
            total_count = field_count + len(override_rows)
            if total_count <= 0:
                return False
            if key == optional_arcade.arcade.key.UP:
                self._editor.entity_panels_inspector_index = max(
                    0, self._editor.entity_panels_inspector_index - 1
                )
                return True
            if key == optional_arcade.arcade.key.DOWN:
                if total_count:
                    self._editor.entity_panels_inspector_index = min(
                        total_count - 1, self._editor.entity_panels_inspector_index + 1
                    )
                return True
            if key == optional_arcade.arcade.key.R and (modifiers & optional_arcade.arcade.key.MOD_SHIFT):
                return bool(self._editor._entity_panels_clear_prefab_overrides())
            if key == optional_arcade.arcade.key.R:
                if self._editor.entity_panels_inspector_index >= field_count and override_rows:
                    idx = self._editor.entity_panels_inspector_index - field_count
                    if 0 <= idx < len(override_rows):
                        return bool(self._editor._entity_panels_revert_prefab_override(override_rows[idx]))
                return False
            if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
                if self._editor.entity_panels_inspector_index < field_count:
                    field = ENTITY_PANEL_FIELDS[self._editor.entity_panels_inspector_index]
                    if field["kind"] != "float":
                        return False
                    entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(
                        self._editor.selected_entity
                    )
                    current = self.entity_panels_numeric_value(
                        entity_data, self._editor.selected_entity, field["key"]
                    )
                    delta = -1.0 if key == optional_arcade.arcade.key.LEFT else 1.0
                    if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                        delta *= 10.0
                    return self.entity_panels_apply_field_update(field["key"], current + delta)
                if override_rows:
                    idx = self._editor.entity_panels_inspector_index - field_count
                    if 0 <= idx < len(override_rows):
                        current_value = override_rows[idx].override_value
                        if isinstance(current_value, bool):
                            return False
                        if not isinstance(current_value, (int, float)):
                            return False
                        delta = -1 if key == optional_arcade.arcade.key.LEFT else 1
                        if isinstance(current_value, float):
                            delta = float(delta) * 0.1
                        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                            delta *= 10
                        return bool(self._editor._entity_panels_apply_prefab_override(
                            override_rows[idx].key,
                            current_value + delta,
                        ))
                return False
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
                if self._editor.entity_panels_inspector_index < field_count:
                    field = ENTITY_PANEL_FIELDS[self._editor.entity_panels_inspector_index]
                    if field["kind"] not in ("string", "tags"):
                        return False
                    entity_data = self._editor.window.scene_controller._ensure_entity_data_dict(
                        self._editor.selected_entity
                    )
                    if field["kind"] == "tags":
                        initial = ", ".join(normalize_entity_panel_tags(entity_data.get("tags")))
                    else:
                        initial = str(entity_data.get(field["key"], "") or "")
                    self.entity_panels_begin_text_edit(field["key"], initial)
                    return True
                if override_rows:
                    idx = self._editor.entity_panels_inspector_index - field_count
                    if 0 <= idx < len(override_rows):
                        current_value = override_rows[idx].override_value
                        if isinstance(current_value, (int, float, bool)):
                            return False
                        initial = "" if current_value is None else str(current_value)
                        self.entity_panels_begin_text_edit(
                            f"prefab_override:{override_rows[idx].key}", initial
                        )
                        return True
                return False
            return False

        return False

    def handle_entity_panels_text_input(self, text: str) -> bool:
        if not self._editor.entity_panels_active:
            return False
        if self._editor.entity_panels_text_edit_active:
            if text and text.isprintable():
                self._editor.entity_panels_text_buffer += text
                return True
            return False
        if (
            self._editor.search.is_panel_search_focused("outliner")
            and self._editor.entity_panels_focus == ENTITY_PANEL_FOCUS_OUTLINER
        ):
            return bool(self._editor.search.append_search_text(text))
        return False
