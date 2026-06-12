from __future__ import annotations

import logging
from typing import Any, List

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.common import draw_panel_bg


class EditorHierarchyController:
    """Encapsulates hierarchy panel open/close behavior."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def toggle_hierarchy(self) -> None:
        editor = self._editor
        if not getattr(editor, "active", False):
            return

        editor.hierarchy_active = not editor.hierarchy_active
        logger = logging.getLogger(__name__)
        if editor.hierarchy_active:
            inspector = getattr(editor, "inspector", None)
            if inspector is not None:
                inspector.set_inspector_active(False)
            editor.palette_active = False
            editor.palette_filter_active = False
            refresher = getattr(editor, "_refresh_hierarchy_list", None)
            if callable(refresher):
                refresher()
            if getattr(editor, "selected_entity", None):
                try:
                    editor.hierarchy_selection_index = editor._cached_hierarchy_list.index(
                        editor.selected_entity,
                    )
                except ValueError:
                    editor.hierarchy_selection_index = (
                        0 if editor._cached_hierarchy_list else -1
                    )
            elif not editor._cached_hierarchy_list:
                editor.hierarchy_selection_index = -1
            logger.info("[Editor] Hierarchy OPEN")
        else:
            editor.hierarchy_filter_active = False
            cancel_rename = getattr(editor, "_cancel_hierarchy_rename", None)
            if callable(cancel_rename):
                cancel_rename()
            logger.info("[Editor] Hierarchy CLOSED")

    def refresh_hierarchy_list(self) -> None:
        editor = self._editor
        previous_selection = getattr(editor, "selected_entity", None)
        editor._cached_hierarchy_list = self.build_hierarchy_list()
        if previous_selection and previous_selection in editor._cached_hierarchy_list:
            editor.hierarchy_selection_index = editor._cached_hierarchy_list.index(previous_selection)
        else:
            count = len(editor._cached_hierarchy_list)
            if count == 0:
                editor.hierarchy_selection_index = -1
            else:
                if editor.hierarchy_selection_index == -1:
                    editor.hierarchy_selection_index = 0
                else:
                    editor.hierarchy_selection_index = max(
                        0,
                        min(editor.hierarchy_selection_index, count - 1),
                    )

    def build_hierarchy_list(self) -> List[optional_arcade.arcade.Sprite]:
        editor = self._editor
        all_sprites = list(editor.window.scene_controller.all_sprites)
        editor._hierarchy_name_cache = {}
        for idx, sprite in enumerate(all_sprites):
            editor._hierarchy_name_cache[id(sprite)] = editor._resolve_display_name(sprite, idx)

        if not editor.hierarchy_filter:
            return all_sprites

        filtered: list[optional_arcade.arcade.Sprite] = []
        search_term = editor.hierarchy_filter.lower()
        is_behaviour_search = search_term.startswith("@")
        if is_behaviour_search:
            search_term = search_term[1:]

        for sprite in all_sprites:
            if is_behaviour_search:
                behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
                if any(search_term in b.__class__.__name__.lower() for b in behaviours):
                    filtered.append(sprite)
            else:
                name = editor._hierarchy_name_cache.get(id(sprite), "").lower()
                tags = [tag.lower() for tag in editor._get_entity_tags(sprite)]
                class_name = getattr(sprite.__class__, "__name__", "").lower()
                haystacks = [name]
                if tags:
                    haystacks.extend(tags)
                if class_name:
                    haystacks.append(class_name)

                if any(search_term in entry for entry in haystacks):
                    filtered.append(sprite)

        return filtered

    def begin_hierarchy_rename(self) -> bool:
        editor = self._editor
        if not (editor.hierarchy_active and editor.selected_entity):
            return False
        if editor.hierarchy_filter_active:
            return False

        current = getattr(editor.selected_entity, "mesh_name", "")
        if not (isinstance(current, str) and current.strip()):
            current = editor._get_display_name_for_sprite(editor.selected_entity)

        editor.hierarchy_rename_active = True
        editor.hierarchy_filter_active = False
        editor.hierarchy_rename_buffer = current
        return True

    def cancel_hierarchy_rename(self) -> None:
        editor = self._editor
        editor.hierarchy_rename_active = False
        editor.hierarchy_rename_buffer = ""

    def commit_hierarchy_rename(self) -> bool:
        editor = self._editor
        if not (editor.hierarchy_rename_active and editor.selected_entity):
            return False

        new_name = editor.hierarchy_rename_buffer.strip()
        if not new_name:
            fallback_index = editor._get_sprite_index(editor.selected_entity)
            new_name = f"Entity#{(fallback_index or 0) + 1}"

        old_name = getattr(editor.selected_entity, "mesh_name", "") or ""
        if new_name == old_name:
            self.cancel_hierarchy_rename()
            return False

        editor._apply_entity_rename(editor.selected_entity, new_name)
        editor._push_command(
            {
                "type": "RenameEntity",
                "before": old_name,
                "after": new_name,
                "current_name": new_name,
            }
        )

        self.cancel_hierarchy_rename()
        self.refresh_hierarchy_list()
        editor._refresh_inspector_items()
        logging.getLogger(__name__).info("[Editor] Renamed entity to '%s'", new_name)
        return True

    def select_hierarchy_item(self, index: int) -> None:
        editor = self._editor
        if 0 <= index < len(editor._cached_hierarchy_list):
            editor.selected_entity = editor._cached_hierarchy_list[index]
            editor.shape.reset_zone_selection_state()
            editor.shape.sync_zone_selection_state(editor.selected_entity)
            self.cancel_hierarchy_rename()
            name = editor._get_display_name_for_sprite(editor.selected_entity)
            logging.getLogger(__name__).info("[Editor] Selected from hierarchy: %s", name)
            editor._refresh_inspector_items()

    def handle_hierarchy_input(self, key: int, modifiers: int) -> bool:
        editor = self._editor
        if editor.hierarchy_rename_active:
            if key == optional_arcade.arcade.key.ENTER:
                return self.commit_hierarchy_rename()
            if key == optional_arcade.arcade.key.ESCAPE:
                self.cancel_hierarchy_rename()
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                editor.hierarchy_rename_buffer = editor.hierarchy_rename_buffer[:-1]
                return True
            return False

        if editor.hierarchy_filter_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.ESCAPE):
                editor.hierarchy_filter_active = False
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                editor.hierarchy_filter = editor.hierarchy_filter[:-1]
                self.refresh_hierarchy_list()
                return True
            return False

        if key == optional_arcade.arcade.key.UP:
            editor.hierarchy_selection_index = max(0, editor.hierarchy_selection_index - 1)
            self.select_hierarchy_item(editor.hierarchy_selection_index)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            count = len(editor._cached_hierarchy_list)
            if count > 0:
                editor.hierarchy_selection_index = min(count - 1, editor.hierarchy_selection_index + 1)
                self.select_hierarchy_item(editor.hierarchy_selection_index)
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            return True
        if key == optional_arcade.arcade.key.SLASH or (
            key == optional_arcade.arcade.key.F
            and (modifiers & optional_arcade.arcade.key.MOD_CTRL)
        ):
            editor.hierarchy_filter_active = True
            return True

        return False

    def draw_hierarchy_panel(self) -> None:
        editor = self._editor
        if not editor.hierarchy_active:
            return

        lines = ["HIERARCHY (H)", "-------------"]
        lines.append("UP/DOWN: Navigate")
        lines.append("ENTER/SPACE: Select")
        lines.append("SHIFT+R: Rename selection")
        lines.append("/ or CTRL+F: Filter")
        lines.append("-------------")

        filter_status = f"Filter: {editor.hierarchy_filter}"
        if editor.hierarchy_filter_active:
            filter_status += "_"
        lines.append(filter_status)

        if editor.hierarchy_rename_active:
            rename_status = f"Rename: {editor.hierarchy_rename_buffer}_"
        else:
            rename_status = "Rename: (SHIFT+R)"
        lines.append(rename_status)
        lines.append("-------------")

        items = editor._cached_hierarchy_list
        max_visible = 25
        start_idx = 0
        if editor.hierarchy_selection_index > max_visible / 2:
            start_idx = max(0, int(editor.hierarchy_selection_index - max_visible / 2))
        end_idx = min(len(items), start_idx + max_visible)

        for i in range(start_idx, end_idx):
            sprite = items[i]
            is_selected = (i == editor.hierarchy_selection_index)
            prefix = "> " if is_selected else "  "
            name = editor._get_display_name_for_sprite(sprite)
            layer = getattr(sprite, "layer", "?")
            tags = editor._get_entity_tags(sprite)
            tag_suffix = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"{prefix}{name} ({layer}){tag_suffix}")

        if len(items) == 0:
            lines.append("  (No entities found)")

        h_start_x = editor.window.width - 300
        h_start_y = editor.window.height - 100

        draw_panel_bg(
            h_start_x - 10,
            editor.window.width,
            h_start_y - len(lines) * 20 - 10,
            h_start_y + 20,
        )

        for i, line in enumerate(lines):
            color = (
                optional_arcade.arcade.color.CYAN
                if line.startswith(">") or "Filter:" in line
                else optional_arcade.arcade.color.WHITE
            )
            optional_arcade.arcade.draw_text(
                line,
                h_start_x,
                h_start_y - i * 20,
                color,
                12,
                font_name="Consolas",
            )
