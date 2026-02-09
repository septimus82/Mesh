from __future__ import annotations

from typing import Any, List, cast

import engine.optional_arcade as optional_arcade

from engine.logging_tools import get_logger
from engine.ui_overlays.common import draw_panel_bg

logger = get_logger(__name__)


class EditorTileController:
    """Encapsulates tile painting panel state and edits."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def tilemap_available(self) -> bool:
        return getattr(self._editor.window.scene_controller, "tilemap_instance", None) is not None

    def set_tile_panel_active(self, value: bool) -> None:
        self._editor.tile_panel_active = bool(value)
        self._editor.session.set_tile_paint_active(self._editor.tile_panel_active)

    def toggle_tile_panel(self) -> None:
        if not self.tilemap_available():
            logger.info("[Editor] Tile panel unavailable: no tilemap loaded")
            return
        self.set_tile_panel_active(not self._editor.tile_panel_active)
        if self._editor.tile_panel_active:
            inspector = getattr(self._editor, "inspector", None)
            if inspector is not None:
                inspector.set_inspector_active(False)
            self._editor.palette_active = False
            self._editor.palette_filter_active = False
            self._editor.hierarchy_active = False
            self._editor.dialogue_panel_active = False
            self._editor.animation_active = False
            self.refresh_tile_palette()
            logger.info("[Editor] Tile panel OPEN")
        else:
            self.close_tile_panel()

    def close_tile_panel(self) -> None:
        self.set_tile_panel_active(False)

    def refresh_tile_palette(self) -> None:
        instance = getattr(self._editor.window.scene_controller, "tilemap_instance", None)
        if instance is None:
            self._editor.tile_palette = []
            self._editor.tile_layers = []
            return
        self._editor.tile_layers = list(instance.layer_data.keys())
        if self._editor.tile_layer_index >= len(self._editor.tile_layers):
            self._editor.tile_layer_index = 0
        gids: List[int] = []
        for tileset in getattr(instance, "tilesets", []):
            for i in range(min(8, tileset.tile_count)):
                gids.append(tileset.first_gid + i)
            if gids:
                break
        if not gids:
            gids = [1]
        self._editor.tile_palette = gids
        self._editor.tile_palette_index = min(
            self._editor.tile_palette_index,
            max(0, len(self._editor.tile_palette) - 1),
        )

    def current_tile_gid(self) -> int:
        if not self._editor.tile_palette:
            return 0
        if (
            self._editor.tile_palette_index < 0
            or self._editor.tile_palette_index >= len(self._editor.tile_palette)
        ):
            self._editor.tile_palette_index = 0
        return int(self._editor.tile_palette[self._editor.tile_palette_index])

    def paint_tile_at(self, world_x: float, world_y: float, gid: int) -> None:
        instance = getattr(self._editor.window.scene_controller, "tilemap_instance", None)
        if instance is None:
            return
        tile_w, tile_h = instance.tile_size
        width, height = instance.layer_dimensions or (0, 0)
        if tile_w <= 0 or tile_h <= 0 or width <= 0 or height <= 0:
            return
        col = int(world_x // tile_w)
        map_pixel_height = height * tile_h
        row = int((map_pixel_height - world_y) // tile_h)
        if not (0 <= col < width and 0 <= row < height):
            return
        layer_name = self.current_tile_layer()
        result = self._editor.window.scene_controller.set_tile(layer_name, col, row, gid)
        if result is None:
            return
        before, after = result
        if before == after:
            return
        self._editor._push_command({
            "type": "PaintTile",
            "layer": layer_name,
            "col": col,
            "row": row,
            "before": before,
            "after": after,
        })

    def current_tile_layer(self) -> str:
        if not self._editor.tile_layers:
            self.refresh_tile_palette()
        if not self._editor.tile_layers:
            return "background"
        self._editor.tile_layer_index = max(
            0,
            min(self._editor.tile_layer_index, len(self._editor.tile_layers) - 1),
        )
        return cast(str, self._editor.tile_layers[self._editor.tile_layer_index])

    def handle_tile_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.tile_panel_active:
            return False
        if key == optional_arcade.arcade.key.ESCAPE:
            self.close_tile_panel()
            return True
        if key == optional_arcade.arcade.key.UP:
            self._editor.tile_palette_index = max(0, self._editor.tile_palette_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self._editor.tile_palette_index = min(
                len(self._editor.tile_palette) - 1,
                self._editor.tile_palette_index + 1,
            )
            return True
        if key == optional_arcade.arcade.key.LEFT_BRACKET:
            if self._editor.tile_layers:
                self._editor.tile_layer_index = (self._editor.tile_layer_index - 1) % len(self._editor.tile_layers)
            return True
        if key == optional_arcade.arcade.key.RIGHT_BRACKET:
            if self._editor.tile_layers:
                self._editor.tile_layer_index = (self._editor.tile_layer_index + 1) % len(self._editor.tile_layers)
            return True
        return False

    def draw_tile_panel(self) -> None:
        lines: List[str] = ["TILES (G)", "--------------"]
        if not self.tilemap_available():
            lines.append("No tilemap loaded")
        else:
            lines.append(f"Layer: {self.current_tile_layer()} ([ / ] to change)")
            if not self._editor.tile_palette:
                lines.append("No tiles available")
            else:
                for idx, gid in enumerate(self._editor.tile_palette):
                    prefix = "> " if idx == self._editor.tile_palette_index else "  "
                    lines.append(f"{prefix}Tile GID {gid}")
            lines.append("Left Click: paint | Right Click: erase")
            lines.append("Ctrl+Z / Ctrl+Y: undo/redo")
        start_x = 10
        start_y = self._editor.window.height - 120
        panel_width = 240
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = (
                optional_arcade.arcade.color.CYAN if line.startswith(">") else optional_arcade.arcade.color.WHITE
            )
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def draw_tile_panel_if_active(self) -> None:
        if self._editor.tile_panel_active:
            self.draw_tile_panel()
