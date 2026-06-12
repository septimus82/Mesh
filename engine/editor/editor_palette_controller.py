from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, cast

import engine.optional_arcade as optional_arcade
from engine.editor.editor_palette_constants import (
    PALETTE_LINE_HEIGHT,
    PALETTE_THUMB_DRAW_SIZE,
    PALETTE_THUMB_SIZE,
)
from engine.editor.prefab_palette_panel import (
    filter_prefab_palette_items as _filter_prefab_palette_items,
)
from engine.editor.prefab_palette_panel import (
    palette_tag_frequencies as _palette_tag_frequencies,
)
from engine.editor.prefab_palette_panel import (
    parse_palette_filter as _parse_palette_filter,
)
from engine.editor_palette_thumbs import request_thumb, tick_thumb_generation
from engine.editor_runtime import ops as editor_ops
from engine.logging_tools import get_logger
from engine.ui_overlays.common import draw_outline_centered, draw_panel_bg

logger = get_logger(__name__)


class EditorPaletteController:
    """Encapsulates prefab palette filtering, selection, and thumb prewarming."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def handle_palette_input(self, key: int, modifiers: int) -> bool:
        if self._editor.palette_filter_active:
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.ESCAPE):
                self._editor.palette_filter_active = False
                return True
            if key == optional_arcade.arcade.key.TAB:
                applied = self.apply_palette_tag_autocomplete()
                if applied:
                    self.refresh_palette_list()
                    self.prewarm_visible_palette_thumbs()
                    return True
                return False
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.palette_filter = self._editor.palette_filter[:-1]
                self.refresh_palette_list()
                self.prewarm_visible_palette_thumbs()
                return True
            return False

        if key == optional_arcade.arcade.key.SLASH or (
            key == optional_arcade.arcade.key.F and (modifiers & optional_arcade.arcade.key.MOD_CTRL)
        ):
            self._editor.palette_filter_active = True
            return True

        if key == optional_arcade.arcade.key.UP:
            self.move_palette_selection(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.move_palette_selection(1)
            return True

        if optional_arcade.arcade.key.KEY_1 <= key <= optional_arcade.arcade.key.KEY_9:
            self.select_palette_index(key - optional_arcade.arcade.key.KEY_1)
            return True

        return False

    def prefab_sprite_path(self, prefab: Dict[str, Any]) -> str | None:
        entity = prefab.get("entity")
        if not isinstance(entity, dict):
            return None
        sprite_path = entity.get("sprite")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            sprite_sheet = entity.get("sprite_sheet")
            if isinstance(sprite_sheet, dict):
                sprite_path = sprite_sheet.get("image")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            return None
        return str(sprite_path)

    def palette_visible_index_range(self, item_count: int) -> tuple[int, int]:
        count = max(0, int(item_count))
        if count == 0:
            return (0, 0)

        header_lines = self.palette_header_line_count()
        p_start_y = float(getattr(self._editor.window, "height", 0) or 0) - 100.0
        available_lines = int(max(0.0, p_start_y) // float(PALETTE_LINE_HEIGHT))
        visible_rows = max(0, available_lines - header_lines)
        end = min(count, visible_rows)
        return (0, max(0, end))

    def palette_header_line_count(self) -> int:
        base = 4
        if self._editor.palette_filter_active and self.palette_tag_suggestions():
            return base + 1
        return base

    def palette_tag_suggestions(self) -> List[str]:
        if not self._editor.palette_filter_active:
            return []
        raw = str(self._editor.palette_filter or "")
        if raw and raw[-1].isspace():
            return []
        tokens = raw.split()
        if not tokens:
            return []
        last = tokens[-1].strip()
        if not last:
            return []
        lower = last.lower()
        partial: str | None = None
        if lower.startswith("#"):
            partial = lower[1:]
        elif lower.startswith("t:"):
            partial = lower[2:]
        if partial is None:
            return []
        partial = partial.strip()

        ranked = list(self._editor._palette_tag_ranked or [])
        if not ranked:
            self._editor._palette_tag_ranked = _palette_tag_frequencies(list(self._editor.prefab_palette))
            ranked = list(self._editor._palette_tag_ranked or [])
            if not ranked:
                return []

        if partial:
            filtered = [t for t in ranked if t.startswith(partial)]
            if not filtered:
                self._editor._palette_tag_ranked = _palette_tag_frequencies(list(self._editor.prefab_palette))
                ranked = list(self._editor._palette_tag_ranked or [])
                filtered = [t for t in ranked if t.startswith(partial)]
            ranked = filtered

        return ranked[:5]

    def apply_palette_tag_autocomplete(self) -> bool:
        suggestions = self.palette_tag_suggestions()
        if not suggestions:
            return False
        raw = str(self._editor.palette_filter or "")
        tokens = raw.split()
        if not tokens:
            return False
        last = tokens[-1].strip()
        if not last:
            return False
        lower = last.lower()
        prefix = ""
        if lower.startswith("#"):
            prefix = "#"
        elif lower.startswith("t:"):
            prefix = "t:"
        else:
            return False
        tokens[-1] = f"{prefix}{suggestions[0]}"
        self._editor.palette_filter = " ".join(tokens)
        return True

    def palette_visible_items(self) -> List[Dict[str, Any]]:
        items = self.get_palette_items()
        start, end = self.palette_visible_index_range(len(items))
        return items[start:end] if end > start else []

    def prewarm_visible_palette_thumbs(self) -> None:
        if not (self._editor.active and self._editor.palette_active):
            return
        for prefab in self.palette_visible_items():
            sprite_path = self.prefab_sprite_path(prefab)
            if sprite_path:
                request_thumb(sprite_path, thumb_size=PALETTE_THUMB_SIZE)

    def build_palette_list(self) -> List[Dict[str, Any]]:
        return _filter_prefab_palette_items(list(self._editor.prefab_palette), self._editor.palette_filter)

    def refresh_palette_list(self) -> None:
        self._editor._cached_palette_list = self.build_palette_list()
        count = len(self._editor._cached_palette_list)
        if count == 0:
            self._editor.palette_index = 0
            return
        self._editor.palette_index = max(0, min(self._editor.palette_index, count - 1))

    def get_palette_items(self) -> List[Dict[str, Any]]:
        return list(cast(List[Dict[str, Any]], self._editor._cached_palette_list))

    def get_palette_thumb_texture(self, prefab: Dict[str, Any]) -> Optional[optional_arcade.arcade.Texture]:
        entity = prefab.get("entity")
        if not isinstance(entity, dict):
            return None
        sprite_path = entity.get("sprite")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            sprite_sheet = entity.get("sprite_sheet")
            if isinstance(sprite_sheet, dict):
                sprite_path = sprite_sheet.get("image")
        if not isinstance(sprite_path, str) or not sprite_path.strip():
            return None
        thumb_path = request_thumb(sprite_path, thumb_size=PALETTE_THUMB_SIZE)
        if thumb_path is None:
            return None
        key = thumb_path.as_posix()
        texture = self._editor._palette_thumb_textures.get(key)
        if texture is None:
            try:
                texture = optional_arcade.arcade.load_texture(str(thumb_path))
            except Exception:
                return None
            self._editor._palette_thumb_textures[key] = texture
        return texture

    def toggle_palette(self) -> None:
        editor_ops.toggle_palette(self._editor)
        if self._editor.palette_active:
            self._editor._palette_tag_ranked = _palette_tag_frequencies(list(self._editor.prefab_palette))
            self.prewarm_visible_palette_thumbs()

    def move_palette_selection(self, delta: int) -> None:
        editor_ops.move_palette_selection(self._editor, delta)

    def select_palette_index(self, index: int) -> None:
        editor_ops.select_palette_index(self._editor, index)

    def palette_selected_prefab(self) -> Optional[str]:
        items = self.get_palette_items()
        if 0 <= self._editor.palette_index < len(items):
            name = items[self._editor.palette_index].get("display_name")
            if isinstance(name, str):
                return name
        return None

    def build_palette_lines(self) -> tuple[list[str], int, List[Dict[str, Any]]]:
        items = self.get_palette_items()
        p_lines = ["PALETTE (P)", "-----------"]
        raw_filter = str(self._editor.palette_filter or "")
        _, tags = _parse_palette_filter(raw_filter)
        if tags:
            shown = tags[:3]
            more = len(tags) - len(shown)
            tail = f" +{more}" if more > 0 else ""
            tag_summary = f" (Tags: {', '.join(shown)}{tail})"
        else:
            tag_summary = " (#tag or t:tag)"

        filter_status = f"Filter: \"{raw_filter}\"{tag_summary}"
        if self._editor.palette_filter_active:
            filter_status += "_"
        p_lines.append(filter_status)

        if self._editor.palette_filter_active:
            suggestions = self.palette_tag_suggestions()
            if suggestions:
                shown = list(suggestions)
                shown[0] = f"[{shown[0]}]"
                p_lines.append("Tags: " + "  ".join(shown))
        p_lines.append("-----------")
        header_lines = len(p_lines)

        if items:
            for i, item in enumerate(items):
                prefix = "> " if i == self._editor.palette_index else f"{i+1} "
                p_lines.append(f"{prefix}{item['display_name']}")
        else:
            p_lines.append("  (No prefabs found)")

        return p_lines, header_lines, items

    def draw_palette(self, text_obj: Any) -> None:
        if not self._editor.palette_active:
            return

        try:
            max_per_frame = int(os.environ.get("MESH_EDITOR_THUMBS_PER_FRAME", "2"))
        except Exception:
            max_per_frame = 2
        if max_per_frame > 0:
            tick_thumb_generation(max_per_frame=max_per_frame)

        lines, header_lines, items = self.build_palette_lines()
        panel_width = 240
        panel_left = self._editor.window.width - panel_width
        p_start_y = self._editor.window.height - 100
        text_indent = PALETTE_THUMB_DRAW_SIZE + 10
        p_start_x = panel_left + text_indent

        draw_panel_bg(
            panel_left - 10,
            self._editor.window.width,
            p_start_y - len(lines) * PALETTE_LINE_HEIGHT - 10,
            p_start_y + 20,
        )

        text_obj.text = "\n".join(lines)
        text_obj.x = p_start_x
        text_obj.y = p_start_y
        text_obj.width = panel_width - text_indent - 10
        text_obj.draw()

        thumb_x = panel_left + (PALETTE_THUMB_DRAW_SIZE / 2) + 4
        start_i, end_i = self.palette_visible_index_range(len(items))
        for i in range(start_i, end_i):
            item = items[i]
            texture = self.get_palette_thumb_texture(item)
            line_index = header_lines + i
            thumb_y = p_start_y - (line_index * PALETTE_LINE_HEIGHT) - (PALETTE_LINE_HEIGHT / 2)
            if texture is None:
                draw_panel_bg(
                    thumb_x - (PALETTE_THUMB_DRAW_SIZE / 2),
                    thumb_x + (PALETTE_THUMB_DRAW_SIZE / 2),
                    thumb_y - (PALETTE_THUMB_DRAW_SIZE / 2),
                    thumb_y + (PALETTE_THUMB_DRAW_SIZE / 2),
                    color=(0, 0, 0, 60),
                )
                draw_outline_centered(
                    thumb_x,
                    thumb_y,
                    PALETTE_THUMB_DRAW_SIZE,
                    PALETTE_THUMB_DRAW_SIZE,
                    color=(255, 255, 255, 80),
                    border=1,
                )
            else:
                optional_arcade.arcade.draw_texture_rectangle(
                    thumb_x,
                    thumb_y,
                    PALETTE_THUMB_DRAW_SIZE,
                    PALETTE_THUMB_DRAW_SIZE,
                    texture,
                )

    def draw_palette_preview(self) -> None:
        editor = self._editor
        if not (editor.palette_active and editor.palette_selected_prefab):
            return
        mx = editor.window._mouse_x
        my = editor.window._mouse_y
        wx, wy = editor.window.screen_to_world(mx, my)

        grid = editor.grid_size
        wx = round(wx / grid) * grid
        wy = round(wy / grid) * grid

        draw_outline_centered(wx, wy, 32, 32, optional_arcade.arcade.color.GREEN, 2)
        optional_arcade.arcade.draw_text(
            editor.palette_selected_prefab,
            wx,
            wy + 20,
            optional_arcade.arcade.color.WHITE,
            10,
            anchor_x="center",
        )
