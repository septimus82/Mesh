"""Shared editor panel layout primitives.

These primitives are intentionally unused until the Tier 1c panel migrations.
They provide a small, deterministic composition layer over the shared UI
layout data classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from engine.text_draw import TextCache, draw_text_cached, get_text_scale
from engine.ui.widgets import DrawInstruction, LayoutResult, Rect
from engine.ui_overlays.common import _draw_tb_rectangle_outline, _safe_truncate, draw_panel_bg

Color = tuple[int, int, int, int]

# Locked values from docs/editor_design_system.md sections 2-4 and cited sources:
# - 24px list rows: engine/ui_overlays/asset_browser_overlay.py:43,
#   engine/ui_overlays/keybinds_overlay.py:52
# - 20px header row: engine/ui_overlays/settings_overlay.py:64
# - 8px padding: engine/ui_overlays/settings_overlay.py:73,89,94
# - panel bg/border: engine/ui_overlays/problems_panel_overlay.py:79-93
# - selected tint: engine/ui_overlays/problems_panel_overlay.py:17
# - label/value/title sizes: engine/ui_overlays/problems_panel_overlay.py:101,113,
#   engine/ui_overlays/settings_overlay.py:64, engine/ui_overlays/keybinds_overlay.py:49
DEFAULT_ROW_HEIGHT = 24.0
DEFAULT_HEADER_HEIGHT = 20.0
DEFAULT_PADDING = 8.0
DEFAULT_ITEM_SPACING = 4.0
DEFAULT_PANEL_BG: Color = (18, 18, 22, 220)
DEFAULT_PANEL_BORDER: Color = (100, 100, 110, 255)
DEFAULT_SELECTED_BG: Color = (90, 140, 200, 140)
# Hover is a local half-alpha placeholder until design-system TBD #1 is locked.
DEFAULT_HOVER_BG: Color = (90, 140, 200, 70)
DEFAULT_TEXT_COLOR: Color = (220, 220, 230, 255)
DEFAULT_DIM_TEXT_COLOR: Color = (150, 150, 160, 255)
DEFAULT_LABEL_FONT_SIZE = 11
DEFAULT_VALUE_FONT_SIZE = 10
DEFAULT_TITLE_FONT_SIZE = 12


@dataclass
class PanelField:
    """Label/value content for one editor panel row."""

    label: str
    value: str | None = None
    on_click: Callable[[], None] | None = None
    label_font_size: int = DEFAULT_LABEL_FONT_SIZE
    value_font_size: int = DEFAULT_VALUE_FONT_SIZE
    label_color: Color = DEFAULT_TEXT_COLOR
    value_color: Color = DEFAULT_DIM_TEXT_COLOR

    def layout(self, bounds: Rect, *, padding_x: float = DEFAULT_PADDING) -> LayoutResult:
        scale = get_text_scale()
        label_char_w = max(1.0, self.label_font_size * 0.6 * scale)
        available_px = bounds.width - 2.0 * padding_x

        if self.value is None:
            # Label-only row: full available width
            label_chars = max(4, int(available_px / label_char_w))
            label_text = _safe_truncate(str(self.label), label_chars)
            instructions = [
                DrawInstruction(
                    kind="panel_field_label",
                    payload={
                        "text": label_text,
                        "x": float(bounds.left + padding_x),
                        "y": float(bounds.center_y),
                        "font_size": int(self.label_font_size),
                        "color": self.label_color,
                        "anchor_x": "left",
                        "anchor_y": "center",
                    },
                )
            ]
            return LayoutResult(rect=bounds, instructions=instructions)

        # Label + value row: fit-first, then cap
        value_char_w = max(1.0, self.value_font_size * 0.6 * scale)
        gap = DEFAULT_PADDING
        label_natural_px = len(str(self.label)) * label_char_w
        value_natural_px = len(str(self.value)) * value_char_w

        if label_natural_px + gap + value_natural_px <= available_px:
            # Both fit without truncation
            label_text = str(self.label)
            value_text = str(self.value)
        else:
            # Overflow: cap value to ≤40%, label gets the remainder
            value_cap_px = (available_px - gap) * 0.40
            value_chars = max(4, int(min(value_natural_px, value_cap_px) / value_char_w))
            value_text = _safe_truncate(str(self.value), value_chars)
            value_actual_px = len(value_text) * value_char_w
            label_chars = max(4, int((available_px - value_actual_px - gap) / label_char_w))
            label_text = _safe_truncate(str(self.label), label_chars)

        instructions = [
            DrawInstruction(
                kind="panel_field_label",
                payload={
                    "text": label_text,
                    "x": float(bounds.left + padding_x),
                    "y": float(bounds.center_y),
                    "font_size": int(self.label_font_size),
                    "color": self.label_color,
                    "anchor_x": "left",
                    "anchor_y": "center",
                },
            ),
            DrawInstruction(
                kind="panel_field_value",
                payload={
                    "text": value_text,
                    "x": float(bounds.right - padding_x),
                    "y": float(bounds.center_y),
                    "font_size": int(self.value_font_size),
                    "color": self.value_color,
                    "anchor_x": "right",
                    "anchor_y": "center",
                },
            ),
        ]
        return LayoutResult(rect=bounds, instructions=instructions)

    def click(self) -> bool:
        if self.on_click is None:
            return False
        self.on_click()
        return True


@dataclass
class PanelHeader:
    """Decorative section header for an editor panel."""

    title: str
    subtitle: str | None = None
    title_font_size: int = DEFAULT_TITLE_FONT_SIZE
    subtitle_font_size: int = DEFAULT_VALUE_FONT_SIZE
    height: float = DEFAULT_HEADER_HEIGHT
    title_color: Color = DEFAULT_TEXT_COLOR
    subtitle_color: Color = DEFAULT_DIM_TEXT_COLOR

    def preferred_height(self) -> float:
        return float(self.height)

    def layout(self, bounds: Rect, *, padding_x: float = DEFAULT_PADDING) -> LayoutResult:
        instructions = [
            DrawInstruction(
                kind="panel_header_title",
                payload={
                    "text": str(self.title),
                    "x": float(bounds.left + padding_x),
                    "y": float(bounds.center_y if self.subtitle is None else bounds.center_y + 4.0),
                    "font_size": int(self.title_font_size),
                    "color": self.title_color,
                    "anchor_x": "left",
                    "anchor_y": "center",
                    "bold": True,
                },
            )
        ]
        if self.subtitle is not None:
            instructions.append(
                DrawInstruction(
                    kind="panel_header_subtitle",
                    payload={
                        "text": str(self.subtitle),
                        "x": float(bounds.left + padding_x),
                        "y": float(bounds.center_y - 7.0),
                        "font_size": int(self.subtitle_font_size),
                        "color": self.subtitle_color,
                        "anchor_x": "left",
                        "anchor_y": "center",
                    },
                )
            )
        return LayoutResult(rect=bounds, instructions=instructions)


@dataclass
class PanelRow:
    """Single interactive row inside an editor panel."""

    content: PanelField | PanelHeader
    height: float = DEFAULT_ROW_HEIGHT
    padding_x: float = DEFAULT_PADDING
    hover_bg: Color = DEFAULT_HOVER_BG
    selected_bg: Color = DEFAULT_SELECTED_BG
    is_hovered: bool = False
    is_selected: bool = False
    _last_rect: Rect | None = field(default=None, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(self.height)

    @property
    def last_rect(self) -> Rect | None:
        return self._last_rect

    def set_hovered(self, hovered: bool) -> None:
        self.is_hovered = bool(hovered)

    def set_selected(self, selected: bool) -> None:
        self.is_selected = bool(selected)

    def hit_test(self, x: float, y: float) -> bool:
        rect = self._last_rect
        return bool(rect is not None and rect.contains(float(x), float(y)))

    def background_color(self) -> Color | None:
        if self.is_selected:
            return self.selected_bg
        if self.is_hovered:
            return self.hover_bg
        return None

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_rect = bounds
        instructions: list[DrawInstruction] = []
        bg = self.background_color()
        if bg is not None:
            instructions.append(
                DrawInstruction(
                    kind="panel_row_bg",
                    payload={
                        "rect": bounds,
                        "color": bg,
                        "selected": bool(self.is_selected),
                        "hovered": bool(self.is_hovered),
                    },
                )
            )
        content_layout = self.content.layout(bounds, padding_x=self.padding_x)
        instructions.extend(content_layout.instructions)
        return LayoutResult(rect=bounds, instructions=instructions, children=[content_layout])

    def click(self) -> bool:
        if isinstance(self.content, PanelField):
            return self.content.click()
        return False


@dataclass
class EditorPanelBase:
    """Base composition primitive for editor panels."""

    rect: Rect
    title: str | None = None
    panel_bg: Color = DEFAULT_PANEL_BG
    panel_border: Color = DEFAULT_PANEL_BORDER
    item_spacing: float = DEFAULT_ITEM_SPACING
    inner_padding_x: float = DEFAULT_PADDING
    inner_padding_y: float = DEFAULT_PADDING
    _items: list[PanelRow | PanelHeader] = field(default_factory=list, init=False, repr=False)
    _last_layout: LayoutResult | None = field(default=None, init=False, repr=False)
    _text_cache: TextCache = field(default_factory=TextCache, init=False, repr=False)

    @property
    def items(self) -> Sequence[PanelRow | PanelHeader]:
        return tuple(self._items)

    @property
    def last_layout(self) -> LayoutResult | None:
        return self._last_layout

    def add_row(self, row: PanelRow) -> PanelRow:
        self._items.append(row)
        return row

    def add_header(self, header: PanelHeader) -> PanelHeader:
        self._items.append(header)
        return header

    def update(self, dt: float) -> None:  # noqa: ARG002
        return

    def _title_height(self) -> float:
        return DEFAULT_HEADER_HEIGHT if self.title else 0.0

    def layout(self) -> LayoutResult:
        instructions = [
            DrawInstruction("editor_panel_bg", {"rect": self.rect, "color": self.panel_bg}),
            DrawInstruction("editor_panel_border", {"rect": self.rect, "color": self.panel_border}),
        ]
        children: list[LayoutResult] = []
        cursor_top = self.rect.top - float(self.inner_padding_y)
        if self.title:
            title_rect = Rect(
                x=self.rect.left + float(self.inner_padding_x),
                y=cursor_top - self._title_height(),
                width=max(0.0, self.rect.width - (float(self.inner_padding_x) * 2.0)),
                height=self._title_height(),
            )
            title_header = PanelHeader(str(self.title), height=self._title_height())
            title_layout = title_header.layout(title_rect, padding_x=0.0)
            instructions.extend(title_layout.instructions)
            children.append(title_layout)
            cursor_top = title_rect.bottom - float(self.item_spacing)

        content_left = self.rect.left + float(self.inner_padding_x)
        content_width = max(0.0, self.rect.width - (float(self.inner_padding_x) * 2.0))
        for index, item in enumerate(self._items):
            height = float(item.preferred_height())
            item_rect = Rect(x=content_left, y=cursor_top - height, width=content_width, height=height)
            if isinstance(item, PanelRow):
                item_layout = item.layout(item_rect)
            else:
                item_layout = item.layout(item_rect, padding_x=0.0)
            children.append(item_layout)
            instructions.extend(item_layout.instructions)
            cursor_top = item_rect.bottom
            if index < len(self._items) - 1:
                cursor_top -= float(self.item_spacing)

        self._last_layout = LayoutResult(rect=self.rect, instructions=instructions, children=children)
        return self._last_layout

    def handle_hover(self, mouse_x: float, mouse_y: float) -> None:
        for item in self._items:
            if isinstance(item, PanelRow):
                item.set_hovered(item.hit_test(float(mouse_x), float(mouse_y)))

    def draw(self) -> None:
        layout = self.layout()
        for instruction in layout.instructions:
            payload = instruction.payload
            rect = payload.get("rect")
            if instruction.kind == "editor_panel_bg" and isinstance(rect, Rect):
                draw_panel_bg(rect.left, rect.right, rect.bottom, rect.top, color=payload.get("color", self.panel_bg))
            elif instruction.kind == "editor_panel_border" and isinstance(rect, Rect):
                _draw_tb_rectangle_outline(
                    rect.left,
                    rect.right,
                    rect.top,
                    rect.bottom,
                    payload.get("color", self.panel_border),
                    1,
                )
            elif instruction.kind == "panel_row_bg" and isinstance(rect, Rect):
                draw_panel_bg(rect.left, rect.right, rect.bottom, rect.top, color=payload.get("color"))
            elif instruction.kind in {"panel_field_label", "panel_field_value", "panel_header_title", "panel_header_subtitle"}:
                draw_text_cached(
                    str(payload.get("text", "")),
                    float(payload.get("x", 0.0)),
                    float(payload.get("y", 0.0)),
                    color=payload.get("color", DEFAULT_TEXT_COLOR),
                    font_size=int(payload.get("font_size", DEFAULT_LABEL_FONT_SIZE)),
                    anchor_x=str(payload.get("anchor_x", "left")),
                    anchor_y=str(payload.get("anchor_y", "center")),
                    bold=bool(payload.get("bold", False)),
                    cache=self._text_cache,
                )
