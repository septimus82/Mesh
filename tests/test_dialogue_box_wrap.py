"""Headless tests for dialogue box word-wrap, sizing, pagination, and choices."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import engine.ui_overlays.dialogue_box as dialogue_box_module
from engine.ui_overlays.ai_chat_overlay import wrap_transcript_text
from engine.ui_overlays.dialogue_box import (
    BODY_LINE_HEIGHT,
    CHOICE_LINE_HEIGHT,
    DIALOGUE_PADDING,
    MAX_DIALOGUE_HEIGHT,
    MIN_DIALOGUE_HEIGHT,
    DialogueBox,
    compute_dialogue_layout,
    dialogue_inner_columns,
    format_choice_label,
    wrap_dialogue_body,
)


class _TextStub:
    def __init__(self, **kwargs: Any) -> None:
        self.text = str(kwargs.get("text", ""))
        self.x = kwargs.get("x", 0)
        self.y = kwargs.get("y", 0)
        self.width = kwargs.get("width", 0)

    def draw(self) -> None:
        return


def _window(*, width: float = 1280.0, height: float = 720.0) -> SimpleNamespace:
    return SimpleNamespace(width=width, height=height)


def _dialogue_box(monkeypatch: pytest.MonkeyPatch) -> DialogueBox:
    monkeypatch.setattr(dialogue_box_module.optional_arcade.arcade, "Text", _TextStub)
    return DialogueBox(_window())


@pytest.mark.fast
def test_wrap_dialogue_body_splits_long_line_within_inner_width() -> None:
    inner_width = 400.0
    columns = dialogue_inner_columns(inner_width)
    long_line = "word " * 80
    wrapped = wrap_dialogue_body(long_line, inner_width)

    assert len(wrapped) > 1
    assert all(len(line) <= columns for line in wrapped)


@pytest.mark.fast
def test_wrap_dialogue_body_breaks_on_word_boundaries() -> None:
    inner_width = 200.0
    columns = dialogue_inner_columns(inner_width)
    text = "alpha beta gamma delta epsilon zeta eta theta"
    wrapped = wrap_dialogue_body(text, inner_width)
    expected = wrap_transcript_text(text, columns)

    assert wrapped == expected
    assert len(wrapped) > 1
    for line in wrapped:
        assert "alpha beta" not in line or line == wrapped[0]


@pytest.mark.fast
def test_box_height_grows_with_wrapped_line_count() -> None:
    window_width = 1280.0
    window_height = 720.0
    inner_width = max(320.0, window_width - 48.0) - (DIALOGUE_PADDING * 2.0)
    short_lines = wrap_dialogue_body("Short line.", inner_width)
    long_lines = wrap_dialogue_body("word " * 120, inner_width)

    short_layout = compute_dialogue_layout(
        window_width=window_width,
        window_height=window_height,
        speaker="NPC",
        wrapped_lines=short_lines,
        body_page=0,
        choice_labels=[],
    )
    long_layout = compute_dialogue_layout(
        window_width=window_width,
        window_height=window_height,
        speaker="NPC",
        wrapped_lines=long_lines,
        body_page=0,
        choice_labels=[],
    )

    assert long_layout.box_height >= short_layout.box_height
    assert short_layout.box_height >= MIN_DIALOGUE_HEIGHT
    assert long_layout.box_height <= MAX_DIALOGUE_HEIGHT
    assert len(long_layout.visible_body_lines) * BODY_LINE_HEIGHT <= long_layout.box_height


@pytest.mark.fast
def test_box_paginates_when_wrapped_text_exceeds_max_height() -> None:
    window_width = 1280.0
    window_height = 720.0
    inner_width = max(320.0, window_width - 48.0) - (DIALOGUE_PADDING * 2.0)
    wrapped = wrap_dialogue_body("paragraph " * 200, inner_width)

    layout = compute_dialogue_layout(
        window_width=window_width,
        window_height=window_height,
        speaker="Storyteller",
        wrapped_lines=wrapped,
        body_page=0,
        choice_labels=[],
    )

    assert layout.body_page_count > 1
    assert layout.box_height <= MAX_DIALOGUE_HEIGHT
    assert len(layout.visible_body_lines) < len(wrapped)

    page_two = compute_dialogue_layout(
        window_width=window_width,
        window_height=window_height,
        speaker="Storyteller",
        wrapped_lines=wrapped,
        body_page=1,
        choice_labels=[],
    )
    assert page_two.body_page == 1
    assert page_two.visible_body_lines != layout.visible_body_lines


@pytest.mark.fast
def test_choice_labels_ellipsize_within_columns() -> None:
    max_columns = 20
    long_label = "A" * 80
    formatted = format_choice_label(long_label, max_columns=max_columns)

    assert len(formatted) <= max_columns
    assert formatted.endswith("...")


@pytest.mark.fast
def test_choices_fit_inside_box_bounds() -> None:
    window_width = 1280.0
    window_height = 720.0
    choices = ["Short", "Another option that is extremely long and should be truncated"]
    inner_width = max(320.0, window_width - 48.0) - (DIALOGUE_PADDING * 2.0)
    wrapped = wrap_dialogue_body("Hello traveller.", inner_width)
    layout = compute_dialogue_layout(
        window_width=window_width,
        window_height=window_height,
        speaker="Merchant",
        wrapped_lines=wrapped,
        body_page=0,
        choice_labels=choices,
    )

    choice_bottom = layout.choice_y_start
    for label in choices:
        formatted = format_choice_label(label, max_columns=layout.choice_label_columns)
        assert len(formatted) <= layout.choice_label_columns
        assert choice_bottom >= layout.bottom + DIALOGUE_PADDING
        choice_bottom += CHOICE_LINE_HEIGHT

    assert layout.left + DIALOGUE_PADDING + layout.inner_width <= layout.right


@pytest.mark.fast
def test_dialogue_box_advance_paginates_before_next_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    box = _dialogue_box(monkeypatch)
    long_text = "segment " * 300
    box.play([{"speaker": "Guide", "text": long_text}, {"speaker": "Guide", "text": "Done."}], owner="npc")

    first_layout = box._current_layout()
    assert first_layout.body_page_count > 1
    assert box._body_page == 0

    assert box.advance(owner="npc") is True
    assert box._body_page == 1
    assert box._current_entry is not None
    assert str(box._current_entry.get("text", "")).startswith("segment")

    while box._body_page + 1 < box._current_layout().body_page_count:
        assert box.advance(owner="npc") is True

    assert box.advance(owner="npc") is True
    assert box._body_page == 0
    assert box.get_current_entry() is not None
    assert box.get_current_entry()["text"] == "Done."
