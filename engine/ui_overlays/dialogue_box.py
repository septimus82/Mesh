"""Dialogue box overlay for speaker-tagged dialogue lines with choices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .ai_chat_overlay import _truncate, wrap_transcript_text
from .common import (
    UIElement,
    _draw_rectangle_filled,
    _draw_tb_rectangle_outline,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

DIALOGUE_PADDING = 24.0
BODY_FONT_SIZE = 14.0
SPEAKER_FONT_SIZE = 16.0
CHOICE_FONT_SIZE = 13.0
BODY_LINE_HEIGHT = 18.0
CHOICE_LINE_HEIGHT = 20.0
MIN_DIALOGUE_HEIGHT = 150.0
MAX_DIALOGUE_HEIGHT = 360.0
MAX_DIALOGUE_HEIGHT_RATIO = 0.42
CHOICE_PREFIX_COLUMNS = 2


@dataclass(frozen=True, slots=True)
class DialogueLayout:
    box_width: float
    box_height: float
    left: float
    right: float
    bottom: float
    top: float
    inner_width: float
    inner_columns: int
    visible_body_lines: tuple[str, ...]
    body_page: int
    body_page_count: int
    speaker_y: float
    body_y: float
    choice_y_start: float
    choice_label_columns: int


def dialogue_inner_columns(inner_width_px: float, *, font_size: float = BODY_FONT_SIZE) -> int:
    """Approximate wrapped column count for a proportional font at a pixel width."""

    return max(1, int(float(inner_width_px) / max(6.0, float(font_size) * 0.58)))


def wrap_dialogue_body(text: str, inner_width_px: float, *, font_size: float = BODY_FONT_SIZE) -> list[str]:
    return wrap_transcript_text(text, dialogue_inner_columns(inner_width_px, font_size=font_size))


def format_choice_label(text: str, *, max_columns: int) -> str:
    usable = max(1, int(max_columns) - CHOICE_PREFIX_COLUMNS)
    return _truncate(str(text or ""), usable)


def compute_dialogue_layout(
    *,
    window_width: float,
    window_height: float,
    speaker: str,
    wrapped_lines: Sequence[str],
    body_page: int,
    choice_labels: Sequence[str],
) -> DialogueLayout:
    box_width = max(320.0, float(window_width) - 48.0)
    inner_width = box_width - (DIALOGUE_PADDING * 2.0)
    inner_columns = dialogue_inner_columns(inner_width)
    max_box_height = min(
        max(MIN_DIALOGUE_HEIGHT, float(window_height) * MAX_DIALOGUE_HEIGHT_RATIO),
        MAX_DIALOGUE_HEIGHT,
    )

    has_speaker = bool(str(speaker or "").strip())
    speaker_block = 22.0 if has_speaker else 0.0
    choice_count = len(tuple(choice_labels))
    choice_block = CHOICE_LINE_HEIGHT * choice_count if choice_count > 0 else 0.0
    vertical_chrome = (DIALOGUE_PADDING * 2.0) + speaker_block + choice_block + 8.0

    lines_per_page = max(1, int((max_box_height - vertical_chrome) // BODY_LINE_HEIGHT))
    source_lines = list(wrapped_lines) or [""]
    pages: list[tuple[str, ...]] = [
        tuple(source_lines[start : start + lines_per_page])
        for start in range(0, len(source_lines), lines_per_page)
    ]
    if not pages:
        pages = [("",)]

    page_index = max(0, min(int(body_page), len(pages) - 1))
    visible_lines = pages[page_index]
    body_height = len(visible_lines) * BODY_LINE_HEIGHT
    box_height = min(max_box_height, max(MIN_DIALOGUE_HEIGHT, vertical_chrome + body_height))

    left = (float(window_width) - box_width) / 2.0
    right = left + box_width
    bottom = 24.0
    top = bottom + box_height

    speaker_y = top - (DIALOGUE_PADDING / 2.0)
    body_y = top - DIALOGUE_PADDING - speaker_block
    choice_y_start = bottom + DIALOGUE_PADDING + 8.0
    choice_label_columns = dialogue_inner_columns(inner_width - 8.0, font_size=CHOICE_FONT_SIZE)

    return DialogueLayout(
        box_width=box_width,
        box_height=box_height,
        left=left,
        right=right,
        bottom=bottom,
        top=top,
        inner_width=inner_width,
        inner_columns=inner_columns,
        visible_body_lines=visible_lines,
        body_page=page_index,
        body_page_count=len(pages),
        speaker_y=speaker_y,
        body_y=body_y,
        choice_y_start=choice_y_start,
        choice_label_columns=choice_label_columns,
    )


class DialogueBox(UIElement):
    """Simple bottom overlay that shows speaker-tagged dialogue lines."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._queue: list[dict[str, Any]] = []
        self._visible: bool = False
        self._owner: str | None = None
        self._current_entry: dict[str, Any] | None = None
        self._choices: list[dict[str, Any]] = []
        self._choice_index: int = -1
        self._choice_locked: bool = False
        self._wrapped_body_lines: list[str] = []
        self._body_page: int = 0
        self._wrap_inner_width: float = 0.0
        self._text_cache = TextCache()
        speaker_color = getattr(optional_arcade.arcade.color, "ALPINE", optional_arcade.arcade.color.WHITE)
        self._speaker_text = optional_arcade.arcade.Text(
            text="",
            x=0,
            y=0,
            color=speaker_color,
            font_size=SPEAKER_FONT_SIZE,
            anchor_y="top",
            bold=True,
        )
        self._body_text = optional_arcade.arcade.Text(
            text="",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=BODY_FONT_SIZE,
            width=10,
            align="left",
            multiline=True,
            anchor_y="top",
        )

    def is_active(self) -> bool:
        return self._visible

    @property
    def blocks_input(self) -> bool:
        return self._visible

    def is_active_for(self, owner: str) -> bool:
        return self._visible and self._owner == owner

    def get_current_entry(self) -> dict[str, Any] | None:
        if not self._visible or self._current_entry is None:
            return None
        entry = dict(self._current_entry)
        if "choices" in self._current_entry:
            entry["choices"] = [dict(choice) for choice in self._current_entry["choices"]]
        return entry

    def play(self, entries: Sequence[dict[str, Any]], *, owner: str) -> bool:
        normalized = [entry for entry in (self._coerce_entry(value) for value in entries) if entry]
        if not normalized:
            self.clear(owner=owner)
            return False
        self._queue = normalized[1:]
        self._owner = owner
        self._visible = True
        self._apply_entry(normalized[0])

        if hasattr(self.window, "audio"):
            self.window.audio.play_sound("assets/sounds/ui_open.wav")

        return True

    def advance(self, *, owner: str | None = None) -> bool:
        if owner is not None and owner != self._owner:
            return False
        if not self._visible:
            return False
        if self._choices:
            return False
        layout = self._current_layout()
        if layout.body_page + 1 < layout.body_page_count:
            self._body_page = layout.body_page + 1
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_click.wav")
            return True
        if self._queue:
            self._apply_entry(self._queue.pop(0))
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_click.wav")
            return True
        self.clear(owner=owner)
        return False

    def clear(self, *, owner: str | None = None) -> None:
        if owner is not None and owner != self._owner:
            return
        self._queue.clear()
        self._visible = False
        self._owner = None
        self._current_entry = None
        self._choices = []
        self._choice_index = -1
        self._choice_locked = False
        self._wrapped_body_lines = []
        self._body_page = 0
        self._wrap_inner_width = 0.0
        self._speaker_text.text = ""
        self._body_text.text = ""

    def close(self) -> None:
        self.clear()

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        return

    def has_choices(self) -> bool:
        if not self._visible or not self._choices:
            return False
        if self._choice_locked:
            return False
        return any(not choice.get("disabled") for choice in self._choices)

    def move_choice_cursor(self, delta: int, *, owner: str | None = None) -> int | None:
        if not self._can_control_choices(owner):
            return None
        if delta == 0 or not self._choices:
            return self._choice_index if self._choice_index >= 0 else None
        count = len(self._choices)
        next_index = self._choice_index if self._choice_index >= 0 else 0
        attempts = 0
        while attempts < count:
            next_index = (next_index + delta) % count
            attempts += 1
            if not bool(self._choices[next_index].get("disabled")):
                if next_index != self._choice_index:
                    self._choice_index = next_index
                    if hasattr(self.window, "audio"):
                        self.window.audio.play_sound("assets/sounds/ui_hover.wav")
                return next_index
        return self._choice_index

    def get_choice_cursor(self, *, owner: str | None = None) -> int | None:
        if not self._can_control_choices(owner):
            return None
        return self._choice_index if self._choice_index >= 0 else None

    def submit_choice(self, *, owner: str | None = None) -> dict[str, Any] | None:
        if not self._can_control_choices(owner):
            return None
        if self._choice_index < 0 or self._choice_index >= len(self._choices):
            return None
        current = self._choices[self._choice_index]
        if bool(current.get("disabled")):
            return None
        self._choice_locked = True
        if hasattr(self.window, "audio"):
            self.window.audio.play_sound("assets/sounds/ui_click.wav")
        return dict(current)

    def get_choices(self) -> list[dict[str, Any]]:
        return [dict(choice) for choice in self._choices]

    def _can_control_choices(self, owner: str | None) -> bool:
        if not self._visible or not self._choices:
            return False
        if self._choice_locked:
            return False
        if self._owner is None:
            return False
        if owner is None:
            owner = self._owner
        return owner == self._owner

    def _coerce_entry(self, value: object) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        text = str(value.get("text", "")).strip()
        if not text:
            return None
        speaker = str(value.get("speaker", "")).strip()
        entry: dict[str, Any] = dict(value)
        entry["speaker"] = speaker
        entry["text"] = text
        choices = self._coerce_choices(entry.get("choices"))
        if choices:
            entry["choices"] = choices
        elif "choices" in entry:
            entry.pop("choices", None)
        return entry

    def _coerce_choices(self, value: object) -> list[dict[str, Any]]:
        if not isinstance(value, (list, tuple)):
            return []
        normalized: list[dict[str, Any]] = []
        auto_id = 0
        for raw in value:
            if isinstance(raw, str):
                text = raw.strip()
                if not text:
                    continue
                choice: dict[str, Any] = {"text": text}
            elif isinstance(raw, dict):
                text = str(raw.get("text", "")).strip()
                if not text:
                    continue
                choice = dict(raw)
                choice["text"] = text
            else:
                continue
            if "id" not in choice:
                choice["id"] = f"choice_{auto_id}"
            normalized.append(choice)
            auto_id += 1
        return normalized

    def _apply_entry(self, entry: dict[str, Any]) -> None:
        self._current_entry = dict(entry)
        if "choices" in entry:
            self._current_entry["choices"] = [dict(choice) for choice in entry["choices"]]
        self._speaker_text.text = entry.get("speaker", "")
        choices = entry.get("choices") or []
        if isinstance(choices, list):
            self._choices = [dict(choice) for choice in choices]
        else:
            self._choices = []
        self._choice_locked = False
        self._choice_index = self._compute_initial_choice_index()
        self._body_page = 0
        layout = self._current_layout_for_text(str(entry.get("text", "")))
        self._wrap_inner_width = layout.inner_width
        self._wrapped_body_lines = wrap_dialogue_body(
            str(entry.get("text", "")),
            layout.inner_width,
        )

    def _refresh_wrapped_body_if_needed(self) -> None:
        if self._current_entry is None:
            return
        inner_width = max(320.0, float(self.window.width) - 48.0) - (DIALOGUE_PADDING * 2.0)
        if abs(inner_width - self._wrap_inner_width) < 0.5:
            return
        self._wrap_inner_width = inner_width
        self._wrapped_body_lines = wrap_dialogue_body(str(self._current_entry.get("text", "")), inner_width)
        speaker = self._speaker_text.text if self._speaker_text.text else ""
        choice_labels = [str(choice.get("text", "")) for choice in self._choices]
        preview = compute_dialogue_layout(
            window_width=float(self.window.width),
            window_height=float(self.window.height),
            speaker=speaker,
            wrapped_lines=self._wrapped_body_lines,
            body_page=self._body_page,
            choice_labels=choice_labels,
        )
        if self._body_page >= preview.body_page_count:
            self._body_page = max(0, preview.body_page_count - 1)

    def _current_layout_for_text(self, text: str) -> DialogueLayout:
        box_width = max(320.0, float(self.window.width) - 48.0)
        inner_width = box_width - (DIALOGUE_PADDING * 2.0)
        wrapped = wrap_dialogue_body(text, inner_width)
        speaker = self._speaker_text.text if self._speaker_text.text else ""
        choice_labels = [str(choice.get("text", "")) for choice in self._choices]
        return compute_dialogue_layout(
            window_width=float(self.window.width),
            window_height=float(self.window.height),
            speaker=speaker,
            wrapped_lines=wrapped,
            body_page=self._body_page,
            choice_labels=choice_labels,
        )

    def _current_layout(self) -> DialogueLayout:
        self._refresh_wrapped_body_if_needed()
        speaker = self._speaker_text.text if self._speaker_text.text else ""
        choice_labels = [str(choice.get("text", "")) for choice in self._choices]
        return compute_dialogue_layout(
            window_width=float(self.window.width),
            window_height=float(self.window.height),
            speaker=speaker,
            wrapped_lines=self._wrapped_body_lines,
            body_page=self._body_page,
            choice_labels=choice_labels,
        )

    def draw(self) -> None:
        if not self._visible:
            return
        layout = self._current_layout()

        _draw_rectangle_filled(
            center_x=self.window.width / 2.0,
            center_y=layout.bottom + layout.box_height / 2.0,
            width=layout.box_width,
            height=layout.box_height,
            color=(10, 12, 20, 220),
        )
        _draw_tb_rectangle_outline(
            layout.left,
            layout.right,
            layout.top,
            layout.bottom,
            optional_arcade.arcade.color.SKY_BLUE,
            2,
        )

        text_x = layout.left + DIALOGUE_PADDING
        if self._speaker_text.text:
            self._speaker_text.x = text_x
            self._speaker_text.y = layout.speaker_y
            self._speaker_text.draw()

        body_text = "\n".join(layout.visible_body_lines)
        self._body_text.text = body_text
        self._body_text.x = text_x
        self._body_text.y = layout.body_y
        self._body_text.width = int(layout.inner_width)
        self._body_text.draw()

        if self._choices:
            choice_x = text_x + 4.0
            choice_y = layout.choice_y_start
            max_choice_width = layout.inner_width - 8.0
            for index, choice in enumerate(self._choices):
                raw_text = str(choice.get("text", ""))
                label = format_choice_label(raw_text, max_columns=layout.choice_label_columns)
                disabled = bool(choice.get("disabled"))
                is_selected = index == self._choice_index
                bg_alpha = 120 if is_selected else 0
                if bg_alpha:
                    _draw_rectangle_filled(
                        center_x=choice_x + max_choice_width / 2.0,
                        center_y=choice_y + CHOICE_LINE_HEIGHT / 2.0,
                        width=max_choice_width,
                        height=CHOICE_LINE_HEIGHT,
                        color=(80, 120, 200, bg_alpha),
                    )
                prefix = "➤" if is_selected else "·"
                color = optional_arcade.arcade.color.SKY_BLUE if is_selected else optional_arcade.arcade.color.LIGHT_GRAY
                if disabled:
                    color = optional_arcade.arcade.color.DARK_GRAY
                draw_text_cached(
                    f"{prefix} {label}",
                    choice_x,
                    choice_y,
                    color=color,
                    font_size=CHOICE_FONT_SIZE,
                    anchor_y="bottom",
                    width=int(max_choice_width),
                    cache=self._text_cache,
                )
                choice_y += CHOICE_LINE_HEIGHT

    def _compute_initial_choice_index(self) -> int:
        if not self._choices:
            return -1
        for idx, choice in enumerate(self._choices):
            if not bool(choice.get("disabled")):
                return idx
        return -1
