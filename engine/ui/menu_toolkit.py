"""Small runtime menu stack built from shared widget primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import engine.optional_arcade as optional_arcade
from engine.text_draw import TextCache, draw_text_cached
from engine.ui.widgets import DrawInstruction, Label, Padding, Panel, Rect, ScrollList, VStack
from engine.ui_overlays.common import UIElement, _draw_tb_rectangle_filled, _draw_tb_rectangle_outline


@dataclass(frozen=True, slots=True)
class SelectableItem:
    id: str
    label: str
    detail_lines: tuple[str, ...] = ()


class MenuScreen(Protocol):
    title: str

    def draw(self, renderer: "MenuRenderer", bounds: Rect, *, active: bool) -> None:
        ...

    def on_key_press(self, key: int, modifiers: int, stack: "MenuStackOverlay") -> bool:
        ...


class MenuStackOverlay(UIElement):
    """A blocking stack of runtime menu screens; only the top screen receives input."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.screens: list[MenuScreen] = []
        self.renderer = MenuRenderer()

    @property
    def blocks_input(self) -> bool:
        return bool(self.screens)

    @property
    def visible(self) -> bool:
        return bool(self.screens)

    def push(self, screen: MenuScreen) -> None:
        self.screens.append(screen)

    def pop(self) -> MenuScreen | None:
        if not self.screens:
            return None
        return self.screens.pop()

    def clear(self) -> None:
        self.screens.clear()

    def draw(self) -> None:
        if not self.screens:
            return
        width = float(getattr(self.window, "width", 1280) or 1280)
        height = float(getattr(self.window, "height", 720) or 720)
        bounds = Rect(width * 0.14, height * 0.14, width * 0.72, height * 0.72)
        for index, screen in enumerate(self.screens):
            active = index == len(self.screens) - 1
            screen.draw(self.renderer, bounds, active=active)
            if not active:
                self.renderer.draw_scrim(bounds, alpha=120)

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:
        if not self.screens:
            return False
        return bool(self.screens[-1].on_key_press(int(key), int(modifiers), self))


class SelectableListScreen:
    """Vertical selectable list with an optional detail panel."""

    def __init__(
        self,
        *,
        title: str,
        items: list[SelectableItem],
        on_activate: Callable[[SelectableItem], None] | None = None,
        empty_detail: str = "No items.",
    ) -> None:
        self.title = str(title)
        self.items = list(items)
        self.on_activate = on_activate
        self.empty_detail = str(empty_detail)
        self.list_widget = ScrollList([item.label for item in self.items], row_height=34, selected_index=0)
        self.activated_item_id: str | None = None

    @property
    def selected_index(self) -> int:
        return int(self.list_widget.selected_index)

    @property
    def focused_item(self) -> SelectableItem | None:
        if not self.items:
            return None
        index = max(0, min(self.selected_index, len(self.items) - 1))
        return self.items[index]

    def draw(self, renderer: "MenuRenderer", bounds: Rect, *, active: bool) -> None:
        renderer.draw_selectable_list_screen(self, bounds, active=active)

    def on_key_press(self, key: int, modifiers: int, stack: MenuStackOverlay) -> bool:  # noqa: ARG002
        arcade_key = optional_arcade.arcade.key
        if key in (arcade_key.UP, arcade_key.W):
            self._move_focus(-1)
            return True
        if key in (arcade_key.DOWN, arcade_key.S):
            self._move_focus(1)
            return True
        if key in (arcade_key.ENTER, arcade_key.RETURN, arcade_key.SPACE):
            item = self.focused_item
            if item is not None:
                self.activated_item_id = item.id
                if self.on_activate is not None:
                    self.on_activate(item)
            return True
        if key == arcade_key.ESCAPE:
            stack.pop()
            return True
        return True

    def _move_focus(self, delta: int) -> None:
        if self.list_widget.ensure_visible(self.selected_index + int(delta)):
            return
        if not self.items:
            self.list_widget.selected_index = -1
            return
        self.list_widget.selected_index = max(0, min(self.selected_index + int(delta), len(self.items) - 1))


class ConfirmModalScreen:
    """Two-choice modal that blocks the menu below it."""

    def __init__(
        self,
        *,
        title: str,
        message: str,
        on_confirm: Callable[[bool], None] | None = None,
    ) -> None:
        self.title = str(title)
        self.message = str(message)
        self.on_confirm = on_confirm
        self.list_widget = ScrollList(["Yes", "No"], row_height=34, selected_index=0)

    @property
    def selected_index(self) -> int:
        return int(self.list_widget.selected_index)

    def draw(self, renderer: "MenuRenderer", bounds: Rect, *, active: bool) -> None:
        renderer.draw_confirm_modal(self, bounds, active=active)

    def on_key_press(self, key: int, modifiers: int, stack: MenuStackOverlay) -> bool:  # noqa: ARG002
        arcade_key = optional_arcade.arcade.key
        if key in (arcade_key.UP, arcade_key.W, arcade_key.DOWN, arcade_key.S):
            self._toggle_focus()
            return True
        if key in (arcade_key.ENTER, arcade_key.RETURN, arcade_key.SPACE):
            confirmed = self.selected_index == 0
            if self.on_confirm is not None:
                self.on_confirm(confirmed)
            stack.pop()
            return True
        if key == arcade_key.ESCAPE:
            stack.pop()
            return True
        return True

    def _toggle_focus(self) -> None:
        next_index = 1 - max(0, min(self.selected_index, 1))
        if not self.list_widget.ensure_visible(next_index):
            self.list_widget.selected_index = next_index


class MenuRenderer:
    def __init__(self) -> None:
        self.text_cache = TextCache(max_size=512)

    def draw_selectable_list_screen(self, screen: SelectableListScreen, bounds: Rect, *, active: bool) -> None:
        title = Label(screen.title, font_size=22, height=34.0, anchor_x="left")
        panel = Panel([VStack([title], spacing=0.0, align="stretch")], padding=Padding.uniform(16.0))
        self.render_instructions(panel.layout(bounds).instructions)
        list_bounds = Rect(bounds.left + 24, bounds.bottom + 36, bounds.width * 0.44, bounds.height - 92)
        detail_bounds = Rect(list_bounds.right + 24, list_bounds.bottom, bounds.right - list_bounds.right - 48, list_bounds.height)
        self.render_instructions(screen.list_widget.layout(list_bounds).instructions)
        self.draw_detail_panel(detail_bounds, screen.focused_item, empty_detail=screen.empty_detail, active=active)

    def draw_confirm_modal(self, screen: ConfirmModalScreen, bounds: Rect, *, active: bool) -> None:
        modal = Rect(bounds.center_x - 180, bounds.center_y - 100, 360, 200)
        self.draw_scrim(bounds, alpha=130)
        panel = Panel([Label(screen.title, font_size=20, height=32.0)], padding=Padding.uniform(14.0))
        self.render_instructions(panel.layout(modal).instructions)
        draw_text_cached(screen.message, modal.left + 18, modal.top - 72, color=(245, 245, 245, 255), font_size=14, cache=self.text_cache)
        choices = Rect(modal.left + 56, modal.bottom + 28, modal.width - 112, 74)
        self.render_instructions(screen.list_widget.layout(choices).instructions)
        if not active:
            self.draw_scrim(modal, alpha=100)

    def draw_detail_panel(self, bounds: Rect, item: SelectableItem | None, *, empty_detail: str, active: bool) -> None:
        _draw_tb_rectangle_filled(bounds.left, bounds.right, bounds.top, bounds.bottom, (24, 26, 36, 245))
        _draw_tb_rectangle_outline(bounds.left, bounds.right, bounds.top, bounds.bottom, (210, 210, 230, 255), 1)
        lines = list(item.detail_lines if item is not None else (empty_detail,))
        if item is not None:
            lines.insert(0, item.label)
        y = bounds.top - 28
        for line in lines:
            draw_text_cached(str(line), bounds.left + 16, y, color=(245, 245, 245, 255), font_size=13, cache=self.text_cache)
            y -= 24
        if not active:
            self.draw_scrim(bounds, alpha=100)

    def draw_scrim(self, bounds: Rect, *, alpha: int) -> None:
        _draw_tb_rectangle_filled(bounds.left, bounds.right, bounds.top, bounds.bottom, (0, 0, 0, max(0, min(255, int(alpha)))))

    def render_instructions(self, instructions: list[DrawInstruction]) -> None:
        for instruction in instructions:
            payload = instruction.payload
            rect = payload.get("rect")
            if instruction.kind in {"panel_bg", "button_bg"} and isinstance(rect, Rect):
                _draw_tb_rectangle_filled(rect.left, rect.right, rect.top, rect.bottom, (28, 30, 40, 245))
                _draw_tb_rectangle_outline(rect.left, rect.right, rect.top, rect.bottom, (210, 210, 230, 255), 1)
            elif instruction.kind == "scroll_row_bg" and isinstance(rect, Rect):
                color = (72, 76, 96, 245) if payload.get("selected") else (34, 36, 46, 230)
                _draw_tb_rectangle_filled(rect.left, rect.right, rect.top, rect.bottom, color)
            elif instruction.kind == "scroll_row_text" and isinstance(rect, Rect):
                color = (255, 245, 170, 255) if payload.get("selected") else (230, 230, 240, 255)
                draw_text_cached(str(payload.get("text", "")), rect.left + 10, rect.center_y, color=color, font_size=13, cache=self.text_cache)
            elif instruction.kind in {"text", "button_text"}:
                draw_text_cached(
                    str(payload.get("text", "")),
                    float(payload.get("x", 0.0)),
                    float(payload.get("y", 0.0)),
                    color=(245, 245, 245, 255),
                    font_size=int(payload.get("font_size", 14)),
                    anchor_x=str(payload.get("anchor_x", "left")),
                    anchor_y=str(payload.get("anchor_y", "center")),
                    cache=self.text_cache,
                )
