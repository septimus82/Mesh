"""Shop panel overlay for buying/selling items from vendors."""

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


class ShopPanel(UIElement):
    """Simple shop overlay listing vendor stock and handling purchases."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self.vendor: Any = None
        self._items: list[dict[str, Any]] = []
        self._cursor_index: int = 0
        self._mode: str = "buy"  # or "sell"
        self._text_cache = TextCache()

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def open(self, vendor: Any, items: list[dict[str, Any]], mode: str = "buy") -> None:
        self.vendor = vendor
        self._items = list(items)
        self._cursor_index = 0
        self._mode = "buy" if mode not in {"buy", "sell"} else mode
        self.visible = True
        if self._mode == "sell":
            self._refresh_items()

    def close(self) -> None:
        self.visible = False
        self.vendor = None
        self._items = []
        self._cursor_index = 0
        self._mode = "buy"

    def set_mode(self, mode: str) -> None:
        if mode not in {"buy", "sell"}:
            return
        if self._mode == mode:
            return
        self._mode = mode
        self._cursor_index = 0
        self._refresh_items()

    def toggle_mode(self) -> None:
        self.set_mode("sell" if self._mode == "buy" else "buy")

    def _refresh_items(self) -> None:
        vendor = self.vendor
        if vendor is None:
            self._items = []
            return
        if self._mode == "sell":
            gs = getattr(self.window, "game_state_controller", None)
            values = gs.state.values if gs is not None else {}
            getter = getattr(vendor, "get_sellable_items", None)
            if callable(getter):
                self._items = getter(values)
        else:
            self._items = getattr(vendor, "stock", [])
        if not self._items:
            self._cursor_index = 0

    def move_cursor(self, direction: int) -> None:
        if not self._items:
            return
        self._cursor_index = (self._cursor_index + direction) % len(self._items)

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        """No cached geometry; exists for consistency with UIController."""
        return

    def confirm_purchase(self) -> None:
        if not (self.visible and self.vendor and self._items):
            return
        item = self._items[self._cursor_index]
        if self._mode == "sell":
            handler = getattr(self.vendor, "handle_sell_request", None)
        else:
            handler = getattr(self.vendor, "handle_buy_request", None)
        if callable(handler):
            result = handler(item)
            message = None
            if isinstance(result, dict):
                message = result.get("message")
            elif hasattr(result, "message"):
                message = getattr(result, "message", None)
            if message:
                hud = getattr(self.window, "player_hud", None)
                enqueue = getattr(hud, "enqueue_toast", None)
                if callable(enqueue):
                    enqueue(str(message))
        if self._mode == "sell":
            self._refresh_items()

    def on_key_press(self, key: int, modifiers: int) -> bool:
        if not self.visible:
            return False
        if key == optional_arcade.arcade.key.UP:
            self.move_cursor(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.move_cursor(1)
            return True
        if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.TAB):
            self.toggle_mode()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            self.confirm_purchase()
            return True
        if key == optional_arcade.arcade.key.ESCAPE:
            self.close()
            return True
        return False

    def _currency_amount(self) -> int:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return 0
        try:
            return int(gs.get_counter("gold", 0))
        except Exception:
            _log_swallow("ui_currency_amount", "Error reading currency counter")
            return 0

    def draw(self) -> None:
        if not self.visible:
            return
        width = min(480.0, self.window.width * 0.7)
        height = min(360.0, self.window.height * 0.8)
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(10, 10, 10, 230),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.GOLD, 2)

        currency = self._currency_amount()
        draw_text_cached(
            f"Shop [{self._mode.upper()}]",
            left + 16,
            top - 24,
            color=optional_arcade.arcade.color.WHITE,
            font_size=18,
            anchor_y="top",
            cache=self._text_cache,
        )
        draw_text_cached(
            f"Gold: {currency}",
            right - 16,
            top - 24,
            color=optional_arcade.arcade.color.GOLD,
            font_size=14,
            anchor_y="top",
            anchor_x="right",
            cache=self._text_cache,
        )

        y = top - 56
        line_height = 22
        if not self._items:
            draw_text_cached(
                "No items for sale.",
                left + 16,
                y,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=14,
                anchor_y="top",
                cache=self._text_cache,
            )
            return
        for idx, entry in enumerate(self._items):
            if y < bottom + 32:
                break
            name = entry.get("name") or entry.get("item_id") or "<item>"
            price = entry.get("price", 0)
            if self._mode == "buy" and self.vendor is not None and hasattr(self.vendor, "get_buy_price"):
                try:
                    price = self.vendor.get_buy_price(entry)
                except Exception:
                    _log_swallow("ui_vendor_price", "Vendor get_buy_price failed")
                    price = entry.get("price", 0)
            qty = entry.get("quantity", -1)
            qty_label = "∞" if qty is None or int(qty) < 0 else str(int(qty))
            color = optional_arcade.arcade.color.WHITE if idx != self._cursor_index else optional_arcade.arcade.color.YELLOW
            draw_text_cached(
                f"{'> ' if idx==self._cursor_index else '  '}{name}  ({qty_label})",
                left + 16,
                y,
                color=color,
                font_size=14,
                anchor_y="top",
                cache=self._text_cache,
            )
            draw_text_cached(
                f"{price}g",
                right - 24,
                y,
                color=optional_arcade.arcade.color.GOLD,
                font_size=14,
                anchor_y="top",
                anchor_x="right",
                cache=self._text_cache,
            )
            y -= line_height
