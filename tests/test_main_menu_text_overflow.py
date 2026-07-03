from __future__ import annotations

import pytest

from engine.ui_overlays.common import (
    text_char_capacity_for_width,
    truncate_text_to_char_limit,
    truncate_text_to_width,
)
from engine.ui_overlays.main_menu_overlay import compute_menu_panel_layout

pytestmark = pytest.mark.fast


def test_truncate_text_to_width_appends_ellipsis_for_long_path() -> None:
    layout = compute_menu_panel_layout(1280.0, 720.0, 3, 0)
    card = layout.cards[0]
    text_width = card.width - 36.0
    long_path = "C:/Users/dev/projects/" + ("nested/" * 40) + "showcase-hub"

    result = truncate_text_to_width(long_path, text_width, 11.0)

    assert result.endswith("...")
    assert len(result) < len(long_path)
    assert len(result) <= text_char_capacity_for_width(text_width, 11.0)


def test_truncate_text_to_width_keeps_short_label_unchanged() -> None:
    layout = compute_menu_panel_layout(1280.0, 720.0, 1, 0)
    card = layout.cards[0]
    label = "Showcase Hub"

    result = truncate_text_to_width(label, card.width - 36.0, 16.0)

    assert result == label


def test_truncate_text_to_char_limit_matches_legacy_three_dot_behavior() -> None:
    assert truncate_text_to_char_limit("abcdef", 3) == "abc"
    assert truncate_text_to_char_limit("abcdef", 4) == "a..."
    assert truncate_text_to_char_limit("abc", 10) == "abc"


def test_text_char_capacity_matches_proposal_inbox_formula() -> None:
    assert text_char_capacity_for_width(120.0, 11) == max(1, int(120 / (11 * 0.6)))


def test_ai_chat_input_width_formula_matches_shared_helper() -> None:
    width = 240.0
    value = "x" * 200
    assert truncate_text_to_width(value, width, 10.0) == truncate_text_to_char_limit(
        value,
        max(1, int(width / 6.0)),
    )
