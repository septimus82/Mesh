from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Sequence


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return float(self.x)

    @property
    def right(self) -> float:
        return float(self.x + self.width)

    @property
    def bottom(self) -> float:
        return float(self.y)

    @property
    def top(self) -> float:
        return float(self.y + self.height)

    @property
    def center_x(self) -> float:
        return float(self.x + (self.width / 2.0))

    @property
    def center_y(self) -> float:
        return float(self.y + (self.height / 2.0))

    def inset(self, padding: "Padding") -> "Rect":
        return Rect(
            x=self.x + float(padding.left),
            y=self.y + float(padding.bottom),
            width=max(0.0, self.width - float(padding.left) - float(padding.right)),
            height=max(0.0, self.height - float(padding.top) - float(padding.bottom)),
        )

    def contains(self, x: float, y: float) -> bool:
        px = float(x)
        py = float(y)
        return self.left <= px <= self.right and self.bottom <= py <= self.top


@dataclass(frozen=True)
class Padding:
    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    @classmethod
    def uniform(cls, value: float) -> "Padding":
        v = float(value)
        return cls(left=v, right=v, top=v, bottom=v)


@dataclass(frozen=True)
class DrawInstruction:
    kind: str
    payload: dict[str, Any]


@dataclass
class LayoutResult:
    rect: Rect
    instructions: list[DrawInstruction] = field(default_factory=list)
    children: list["LayoutResult"] = field(default_factory=list)


class Widget(Protocol):
    def preferred_height(self) -> float:
        ...

    def layout(self, bounds: Rect) -> LayoutResult:
        ...


@dataclass
class Label:
    text: str
    font_size: int = 20
    color_token: str = "white"
    height: float = 36.0
    anchor_x: str = "center"
    anchor_y: str = "center"
    _last_rect: Rect | None = field(default=None, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(self.height)

    @property
    def last_rect(self) -> Rect | None:
        return self._last_rect

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_rect = bounds
        return LayoutResult(
            rect=bounds,
            instructions=[
                DrawInstruction(
                    kind="text",
                    payload={
                        "text": str(self.text),
                        "x": bounds.center_x,
                        "y": bounds.center_y,
                        "font_size": int(self.font_size),
                        "color_token": str(self.color_token),
                        "anchor_x": str(self.anchor_x),
                        "anchor_y": str(self.anchor_y),
                    },
                )
            ],
        )


@dataclass
class Button:
    text: str
    action_id: str
    font_size: int = 20
    height: float = 36.0
    text_color_token: str = "gray"
    bg_style_token: str | None = None
    _last_rect: Rect | None = field(default=None, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(self.height)

    @property
    def last_rect(self) -> Rect | None:
        return self._last_rect

    def hit_test(self, x: float, y: float) -> bool:
        rect = self._last_rect
        if rect is None:
            return False
        return rect.contains(x, y)

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_rect = bounds
        instructions: list[DrawInstruction] = []
        if isinstance(self.bg_style_token, str) and self.bg_style_token.strip():
            instructions.append(
                DrawInstruction(
                    kind="button_bg",
                    payload={
                        "rect": bounds,
                        "style_token": str(self.bg_style_token),
                    },
                )
            )
        instructions.append(
            DrawInstruction(
                kind="button_text",
                payload={
                    "text": str(self.text),
                    "x": bounds.center_x,
                    "y": bounds.center_y,
                    "font_size": int(self.font_size),
                    "color_token": str(self.text_color_token),
                    "anchor_x": "center",
                    "anchor_y": "center",
                    "action_id": str(self.action_id),
                },
            )
        )
        return LayoutResult(rect=bounds, instructions=instructions)


@dataclass
class VStack:
    children: Sequence[Widget]
    spacing: float = 8.0
    align: Literal["left", "center", "stretch"] = "center"

    def preferred_height(self) -> float:
        items = list(self.children)
        if not items:
            return 0.0
        total = 0.0
        for item in items:
            total += float(item.preferred_height())
        total += float(self.spacing) * float(max(0, len(items) - 1))
        return total

    def layout(self, bounds: Rect) -> LayoutResult:
        instructions: list[DrawInstruction] = []
        children_layouts: list[LayoutResult] = []
        cursor_top = bounds.top
        for index, child in enumerate(self.children):
            height = max(0.0, float(child.preferred_height()))
            width = bounds.width
            if self.align == "left":
                child_x = bounds.left
            elif self.align == "center":
                child_x = bounds.center_x - (width / 2.0)
            else:
                child_x = bounds.left
            child_rect = Rect(
                x=child_x,
                y=cursor_top - height,
                width=width,
                height=height,
            )
            child_layout = child.layout(child_rect)
            children_layouts.append(child_layout)
            instructions.extend(child_layout.instructions)
            if child_layout.children:
                for nested in child_layout.children:
                    instructions.extend(nested.instructions)
            cursor_top -= height
            if index < len(self.children) - 1:
                cursor_top -= float(self.spacing)
        return LayoutResult(rect=bounds, instructions=instructions, children=children_layouts)


@dataclass
class Panel:
    children: Sequence[Widget]
    padding: Padding = field(default_factory=Padding)
    bg_style_token: str = "panel"

    def preferred_height(self) -> float:
        children = list(self.children)
        if not children:
            return float(self.padding.top + self.padding.bottom)
        max_height = 0.0
        for child in children:
            max_height = max(max_height, float(child.preferred_height()))
        return float(max_height + self.padding.top + self.padding.bottom)

    def layout(self, bounds: Rect) -> LayoutResult:
        instructions: list[DrawInstruction] = [
            DrawInstruction(
                kind="panel_bg",
                payload={
                    "rect": bounds,
                    "style_token": str(self.bg_style_token),
                },
            )
        ]
        children_layouts: list[LayoutResult] = []
        inner_bounds = bounds.inset(self.padding)
        for child in self.children:
            child_layout = child.layout(inner_bounds)
            children_layouts.append(child_layout)
            instructions.extend(child_layout.instructions)
            if child_layout.children:
                for nested in child_layout.children:
                    instructions.extend(nested.instructions)
        return LayoutResult(rect=bounds, instructions=instructions, children=children_layouts)


@dataclass
class TextInput:
    text: str = ""
    placeholder: str = ""
    focused: bool = False
    font_size: int = 14
    height: float = 24.0
    padding_x: float = 6.0
    _last_rect: Rect | None = field(default=None, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(self.height)

    @property
    def last_rect(self) -> Rect | None:
        return self._last_rect

    def _display_text(self) -> str:
        return str(self.text) if str(self.text) else str(self.placeholder)

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_rect = bounds
        display_text = self._display_text()
        instructions: list[DrawInstruction] = [
            DrawInstruction(
                kind="text_input_bg",
                payload={
                    "rect": bounds,
                    "focused": bool(self.focused),
                },
            ),
            DrawInstruction(
                kind="text_input_text",
                payload={
                    "text": display_text,
                    "is_placeholder": bool(not str(self.text)),
                    "x": float(bounds.left + self.padding_x),
                    "y": float(bounds.center_y),
                    "font_size": int(self.font_size),
                },
            ),
        ]
        if self.focused:
            instructions.append(
                DrawInstruction(
                    kind="text_input_caret",
                    payload={
                        "text": str(self.text),
                        "x": float(bounds.left + self.padding_x),
                        "y": float(bounds.center_y),
                        "font_size": int(self.font_size),
                    },
                )
            )
        return LayoutResult(rect=bounds, instructions=instructions)

    def render(self) -> list[DrawInstruction]:
        rect = self._last_rect
        if rect is None:
            return []
        return self.layout(rect).instructions

    def on_mouse_press(self, x: float, y: float) -> bool:
        rect = self._last_rect
        if rect is None:
            return False
        focused = bool(rect.contains(float(x), float(y)))
        changed = focused != self.focused
        self.focused = focused
        return changed

    def on_text_input(self, char: str) -> bool:
        if not self.focused:
            return False
        token = str(char or "")
        if not token or not token.isprintable():
            return False
        self.text = f"{self.text}{token}"
        return True

    def on_key_backspace(self) -> bool:
        if not self.focused or not self.text:
            return False
        self.text = self.text[:-1]
        return True

    def on_key_enter(self) -> bool:
        return bool(self.focused)


@dataclass
class Slider:
    label: str
    value: float
    step: float = 0.01
    height: float = 24.0
    _last_rect: Rect | None = field(default=None, init=False, repr=False)
    _dragging: bool = field(default=False, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(self.height)

    @property
    def last_rect(self) -> Rect | None:
        return self._last_rect

    @property
    def dragging(self) -> bool:
        return bool(self._dragging)

    def _clamp01(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _quantize(self, value: float) -> float:
        clamped = self._clamp01(value)
        step = float(self.step)
        if step <= 0.0:
            return clamped
        snapped = round(clamped / step) * step
        return self._clamp01(snapped)

    def _value_from_x(self, x: float) -> float:
        rect = self._last_rect
        if rect is None or rect.width <= 0.0:
            return self._quantize(self.value)
        ratio = (float(x) - rect.left) / rect.width
        return self._quantize(ratio)

    def set_value(self, value: float) -> bool:
        previous = float(self.value)
        next_value = self._quantize(value)
        self.value = next_value
        return next_value != previous

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_rect = bounds
        self.value = self._quantize(self.value)
        track_h = max(4.0, bounds.height * 0.25)
        knob_w = max(6.0, bounds.height * 0.18)
        track_left = float(bounds.left + (knob_w / 2.0))
        track_width = max(0.0, float(bounds.width - knob_w))
        fill_width = track_width * float(self.value)
        knob_center_x = float(track_left + fill_width)
        track_rect = Rect(
            x=track_left,
            y=(bounds.center_y - (track_h / 2.0)),
            width=track_width,
            height=track_h,
        )
        fill_rect = Rect(
            x=track_left,
            y=track_rect.y,
            width=max(0.0, min(track_width, fill_width)),
            height=track_h,
        )
        knob_rect = Rect(
            x=(knob_center_x - (knob_w / 2.0)),
            y=(bounds.center_y - (bounds.height * 0.3)),
            width=knob_w,
            height=max(6.0, bounds.height * 0.6),
        )
        value_percent = int(round(float(self.value) * 100.0))
        instructions = [
            DrawInstruction(
                kind="slider_label_text",
                payload={
                    "text": str(self.label),
                    "x": float(bounds.left),
                    "y": float(bounds.top - 2.0),
                    "anchor_x": "left",
                    "anchor_y": "top",
                },
            ),
            DrawInstruction(
                kind="slider_value_text",
                payload={
                    "text": f"{value_percent}%",
                    "x": float(bounds.right),
                    "y": float(bounds.top - 2.0),
                    "anchor_x": "right",
                    "anchor_y": "top",
                },
            ),
            DrawInstruction(
                kind="slider_track",
                payload={
                    "rect": track_rect,
                },
            ),
            DrawInstruction(
                kind="slider_fill",
                payload={
                    "rect": fill_rect,
                },
            ),
            DrawInstruction(
                kind="slider_knob",
                payload={
                    "rect": knob_rect,
                    "dragging": bool(self._dragging),
                },
            ),
        ]
        return LayoutResult(rect=bounds, instructions=instructions)

    def render(self) -> list[DrawInstruction]:
        rect = self._last_rect
        if rect is None:
            return []
        return self.layout(rect).instructions

    def on_mouse_press(self, x: float, y: float) -> bool:
        rect = self._last_rect
        if rect is None:
            return False
        if not rect.contains(float(x), float(y)):
            return False
        self._dragging = True
        return bool(self.set_value(self._value_from_x(float(x))) or True)

    def on_mouse_drag(self, x: float, y: float) -> bool:  # noqa: ARG002
        if not self._dragging:
            return False
        return self.set_value(self._value_from_x(float(x)))

    def on_mouse_release(self, _x: float, _y: float) -> bool:
        was_dragging = self._dragging
        self._dragging = False
        return bool(was_dragging)


@dataclass
class Toggle:
    label: str
    value: bool = False
    height: float = 24.0
    _last_rect: Rect | None = field(default=None, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(self.height)

    @property
    def last_rect(self) -> Rect | None:
        return self._last_rect

    def hit_test(self, x: float, y: float) -> bool:
        rect = self._last_rect
        if rect is None:
            return False
        return bool(rect.contains(float(x), float(y)))

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_rect = bounds
        marker = "[x]" if bool(self.value) else "[ ]"
        return LayoutResult(
            rect=bounds,
            instructions=[
                DrawInstruction(
                    kind="toggle_text",
                    payload={
                        "text": f"{marker} {self.label}",
                        "x": float(bounds.left),
                        "y": float(bounds.center_y),
                        "anchor_x": "left",
                        "anchor_y": "center",
                    },
                )
            ],
        )

    def render(self) -> list[DrawInstruction]:
        rect = self._last_rect
        if rect is None:
            return []
        return self.layout(rect).instructions

    def on_mouse_press(self, x: float, y: float) -> bool:
        if not self.hit_test(float(x), float(y)):
            return False
        self.value = not bool(self.value)
        return True


@dataclass
class ScrollList:
    items: list[str]
    row_height: int
    selected_index: int = 0
    scroll_offset: float = 0.0
    _last_bounds: Rect | None = field(default=None, init=False, repr=False)
    _visible_rows: list[tuple[int, str, Rect, bool]] = field(default_factory=list, init=False, repr=False)
    _visible_capacity: int = field(default=0, init=False, repr=False)
    _visible_start_index: int = field(default=0, init=False, repr=False)

    def preferred_height(self) -> float:
        return float(max(0, len(self.items)) * max(1, int(self.row_height)))

    @property
    def visible_rows(self) -> list[tuple[int, str, Rect, bool]]:
        return list(self._visible_rows)

    @property
    def visible_capacity(self) -> int:
        return int(self._visible_capacity)

    @property
    def visible_start_index(self) -> int:
        return int(self._visible_start_index)

    @property
    def visible_count(self) -> int:
        return int(len(self._visible_rows))

    def _normalized_row_height(self) -> int:
        return max(1, int(self.row_height))

    def _compute_capacity(self, bounds: Rect) -> int:
        row_h = float(self._normalized_row_height())
        if bounds.height <= 0.0:
            return 0
        capacity = int(bounds.height // row_h)
        if capacity <= 0:
            return 1
        return capacity

    def _max_scroll_offset(self, capacity: int) -> float:
        if capacity <= 0:
            return 0.0
        total = len(self.items)
        if total <= capacity:
            return 0.0
        return float(total - capacity)

    def _clamp_scroll_offset(self, value: float, capacity: int) -> float:
        max_offset = self._max_scroll_offset(capacity)
        if value < 0.0:
            return 0.0
        if value > max_offset:
            return max_offset
        return float(value)

    def _clamp_selected_index(self) -> int:
        count = len(self.items)
        if count <= 0:
            return -1
        if self.selected_index < 0:
            return 0
        if self.selected_index >= count:
            return count - 1
        return int(self.selected_index)

    def render(self) -> list[DrawInstruction]:
        instructions: list[DrawInstruction] = []
        for row_index, row_text, row_rect, is_selected in self._visible_rows:
            instructions.append(
                DrawInstruction(
                    kind="scroll_row_bg",
                    payload={
                        "row_index": int(row_index),
                        "rect": row_rect,
                        "selected": bool(is_selected),
                    },
                )
            )
            instructions.append(
                DrawInstruction(
                    kind="scroll_row_text",
                    payload={
                        "row_index": int(row_index),
                        "text": str(row_text),
                        "rect": row_rect,
                        "selected": bool(is_selected),
                    },
                )
            )
        return instructions

    def layout(self, bounds: Rect) -> LayoutResult:
        self._last_bounds = bounds
        capacity = self._compute_capacity(bounds)
        self._visible_capacity = int(capacity)
        self.selected_index = self._clamp_selected_index()
        self.scroll_offset = self._clamp_scroll_offset(float(self.scroll_offset), capacity)
        start_index = int(self.scroll_offset)
        self._visible_start_index = int(start_index)
        row_h = float(self._normalized_row_height())

        visible_rows: list[tuple[int, str, Rect, bool]] = []
        if capacity > 0:
            max_index = min(len(self.items), start_index + capacity)
            for local_idx, row_index in enumerate(range(start_index, max_index)):
                row_top = bounds.top - (float(local_idx) * row_h)
                row_bottom = row_top - row_h
                row_rect = Rect(
                    x=bounds.left,
                    y=row_bottom,
                    width=bounds.width,
                    height=row_h,
                )
                visible_rows.append(
                    (
                        int(row_index),
                        str(self.items[row_index]),
                        row_rect,
                        bool(row_index == self.selected_index),
                    )
                )
        self._visible_rows = visible_rows
        return LayoutResult(rect=bounds, instructions=self.render())

    def on_mouse_wheel(self, delta_y: float) -> bool:
        bounds = self._last_bounds
        if bounds is None:
            return False
        capacity = self._compute_capacity(bounds)
        if capacity <= 0 or len(self.items) <= capacity:
            return False
        previous = float(self.scroll_offset)
        self.scroll_offset = self._clamp_scroll_offset(previous - float(delta_y), capacity)
        changed = self.scroll_offset != previous
        if changed:
            self.layout(bounds)
        return changed

    def on_mouse_press(self, x: float, y: float) -> bool:
        bounds = self._last_bounds
        if bounds is None:
            return False
        for row_index, _text, row_rect, _selected in self._visible_rows:
            if row_rect.contains(float(x), float(y)):
                if self.selected_index != row_index:
                    self.selected_index = int(row_index)
                self.ensure_visible(self.selected_index)
                return True
        return False

    def ensure_visible(self, selected_index: int) -> bool:
        bounds = self._last_bounds
        if bounds is None:
            return False
        capacity = self._compute_capacity(bounds)
        if capacity <= 0:
            return False
        count = len(self.items)
        if count <= 0:
            if self.selected_index != -1:
                self.selected_index = -1
                self.layout(bounds)
                return True
            return False
        clamped_selected = max(0, min(int(selected_index), count - 1))
        changed = clamped_selected != self.selected_index
        self.selected_index = clamped_selected
        start = int(self.scroll_offset)
        end = start + capacity - 1
        target_offset = float(start)
        if clamped_selected < start:
            target_offset = float(clamped_selected)
        elif clamped_selected > end:
            target_offset = float(clamped_selected - capacity + 1)
        clamped_offset = self._clamp_scroll_offset(target_offset, capacity)
        if clamped_offset != self.scroll_offset:
            self.scroll_offset = clamped_offset
            changed = True
        if changed:
            self.layout(bounds)
        return changed

    def on_key_up(self) -> bool:
        return self.ensure_visible(int(self.selected_index) - 1)

    def on_key_down(self) -> bool:
        return self.ensure_visible(int(self.selected_index) + 1)

    def on_key_page_up(self) -> bool:
        step = max(1, int(self._visible_capacity))
        return self.ensure_visible(int(self.selected_index) - step)

    def on_key_page_down(self) -> bool:
        step = max(1, int(self._visible_capacity))
        return self.ensure_visible(int(self.selected_index) + step)

    def on_key_home(self) -> bool:
        return self.ensure_visible(0)

    def on_key_end(self) -> bool:
        return self.ensure_visible(len(self.items) - 1)
