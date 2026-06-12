"""Character panel overlay showing player stats, XP, and equipment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from ..text_draw import TextCache, draw_text_cached
from .common import (
    UIElement,
    _draw_rectangle_filled,
    _draw_tb_rectangle_outline,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class CharacterPanel(UIElement):
    """Overlay showing player level, XP, and derived stats."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._text_cache = TextCache()
        self._title = optional_arcade.arcade.Text(
            text="Character",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_y="top",
        )
        self._hint = optional_arcade.arcade.Text(
            text="Press ESC or C to close",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=11,
            anchor_y="top",
        )

    def toggle(self) -> bool:
        self.visible = not self.visible
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    def close(self) -> None:
        self.visible = False

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        return

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.C):
            self.set_visible(False)
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_close.wav")
            return True
        return True

    def _collect_stats(self) -> dict[str, Any]:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return {}
        stats = dict(gs.get_player_stats())
        xp = float(stats.get("xp", 0) or 0)
        xp_to_next = float(stats.get("xp_to_next", 0) or 0)
        xp_needed = max(1.0, xp + max(0.0, xp_to_next))
        stats["xp_needed"] = xp_needed
        try:
            stats["gold"] = getattr(self.window, "get_counter", lambda *a, **k: 0)("gold", 0)
        except Exception:
            _log_swallow("ui_stats_gold", "Failed to get gold counter")
            stats["gold"] = 0
        equipment = stats.get("equipment", {}) or {}
        stats["equipment_labels"] = self._resolve_equipment_labels(equipment)
        return stats

    def _resolve_equipment_labels(self, equipment: dict[str, Any]) -> dict[str, str]:
        labels: dict[str, str] = {}
        try:
            from ..inventory import load_item_database

            db = load_item_database()
        except Exception:
            _log_swallow("ui_inventory_db", "Failed to load item database")
            db = None
        for slot in ("weapon", "armor", "accessory"):
            item_id = equipment.get(slot) if isinstance(equipment, dict) else None
            if not item_id:
                labels[slot] = "<empty>"
                continue
            if db is not None:
                item_def = db.get(item_id)
                labels[slot] = item_def.name if item_def else str(item_id)
            else:
                labels[slot] = str(item_id)
        return labels

    def draw(self) -> None:
        if not self.visible:
            return

        stats = self._collect_stats()
        if not stats:
            return

        width = min(420.0, max(280.0, self.window.width * 0.35))
        height = 240.0
        left = self.window.width - width - 24.0
        right = left + width
        bottom = 72.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(8, 12, 22, 220),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        padding = 20.0
        self._title.x = left + padding
        self._title.y = top - 16.0
        self._title.draw()
        self._hint.x = left + padding
        self._hint.y = bottom + 14.0
        self._hint.draw()

        content_y = top - 50.0
        line_height = 20.0
        xp = stats.get("xp", 0)
        xp_needed = stats.get("xp_needed", 1)
        draw_text_cached(
            f"Level: {int(stats.get('level', 1))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"XP: {int(xp)} / {int(xp_needed)}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"HP: {int(stats.get('max_hp', 0))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Attack: {int(stats.get('attack', 0))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Defense: {int(stats.get('defense', 0))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Speed: {stats.get('speed', 0):.2f}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Gold: {int(stats.get('gold', 0) or 0)}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.GOLD,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height * 1.5
        draw_text_cached(
            "Equipment:",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.SKY_BLUE,
            font_size=14,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        labels = stats.get("equipment_labels", {}) or {}
        for slot in ("weapon", "armor", "accessory"):
            label = labels.get(slot, "<empty>")
            draw_text_cached(
                f"{slot.title()}: {label}",
                left + padding + 8.0,
                content_y,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=12,
                anchor_y="top",
                cache=self._text_cache,
            )
            content_y -= line_height
