"""Dialogue box overlay for speaker-tagged dialogue lines with choices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


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
        self._text_cache = TextCache()
        speaker_color = getattr(optional_arcade.arcade.color, "ALPINE", optional_arcade.arcade.color.WHITE)
        self._speaker_text = optional_arcade.arcade.Text(
            text="",
            x=0,
            y=0,
            color=speaker_color,
            font_size=16,
            anchor_y="top",
            bold=True,
        )
        self._body_text = optional_arcade.arcade.Text(
            text="",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
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
        self._speaker_text.text = ""
        self._body_text.text = ""

    def close(self) -> None:
        self.clear()

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        self._speaker_text.y = self.window.height - 54
        self._speaker_text.x = 20
        self._body_text.y = self.window.height - 80
        self._body_text.x = 20

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
        self._body_text.text = entry.get("text", "")
        choices = entry.get("choices") or []
        if isinstance(choices, list):
            self._choices = [dict(choice) for choice in choices]
        else:
            self._choices = []
        self._choice_locked = False
        self._choice_index = self._compute_initial_choice_index()

    def draw(self) -> None:
        if not self._visible:
            return
        width = max(320.0, self.window.width - 48.0)
        height = 150.0
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = 24.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=self.window.width / 2.0,
            center_y=bottom + height / 2.0,
            width=width,
            height=height,
            color=(10, 12, 20, 220),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        padding = 24.0
        self._speaker_text.x = left + padding
        self._speaker_text.y = top - padding / 2.0
        self._speaker_text.draw()

        self._body_text.x = left + padding
        self._body_text.y = top - padding - 16.0
        self._body_text.width = int(width - padding * 2.0)
        self._body_text.draw()

        if self._choices:
            choice_x = left + padding + 4.0
            choice_y = bottom + padding + 8.0
            line_height = 20.0
            max_choice_width = width - padding * 2.0 - 8.0
            for index, choice in enumerate(self._choices):
                text = choice.get("text", "")
                disabled = bool(choice.get("disabled"))
                is_selected = index == self._choice_index
                bg_alpha = 120 if is_selected else 0
                if bg_alpha:
                    _draw_rectangle_filled(
                        center_x=choice_x + max_choice_width / 2.0,
                        center_y=choice_y + line_height / 2.0,
                        width=max_choice_width,
                        height=line_height,
                        color=(80, 120, 200, bg_alpha),
                    )
                prefix = "➤" if is_selected else "·"
                color = optional_arcade.arcade.color.SKY_BLUE if is_selected else optional_arcade.arcade.color.LIGHT_GRAY
                if disabled:
                    color = optional_arcade.arcade.color.DARK_GRAY
                draw_text_cached(
                    f"{prefix} {text}",
                    choice_x,
                    choice_y,
                    color=color,
                    font_size=13,
                    anchor_y="bottom",
                    width=int(max_choice_width),
                    cache=self._text_cache,
                )
                choice_y += line_height

    def _compute_initial_choice_index(self) -> int:
        if not self._choices:
            return -1
        for idx, choice in enumerate(self._choices):
            if not bool(choice.get("disabled")):
                return idx
        return -1
