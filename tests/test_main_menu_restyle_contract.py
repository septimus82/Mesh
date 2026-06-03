from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import engine.ui_overlays.main_menu_overlay as main_menu_module
from engine.ui_overlays.main_menu_overlay import MainMenuOverlay, compute_project_browser_menu_layout

pytestmark = [pytest.mark.fast]


PROJECT_ITEMS = [
    {"root": "D:/Games/Mesh", "label": "Mesh", "kind": "recent"},
    {"root": "D:/Games/Mesh", "label": "Use current repo", "kind": "current"},
    {"root": "", "label": "Create New Project...", "kind": "create"},
]


def _capture_project_browser_draw(selected_index: int = 1) -> tuple[list[tuple[str, Any]], list[dict[str, Any]]]:
    events: list[tuple[str, Any]] = []
    text_calls: list[dict[str, Any]] = []

    class TextSpy:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            text_calls.append(kwargs)
            events.append(("text", kwargs.get("text")))

        def draw(self) -> None:
            return

    def fill_spy(**kwargs: Any) -> None:
        events.append(("fill", kwargs.get("color")))

    def outline_spy(*args: Any, **_kwargs: Any) -> None:
        events.append(("outline", args[4] if len(args) > 4 else None))

    window = SimpleNamespace(width=1280, height=720, paused=False)
    overlay = MainMenuOverlay(window)
    overlay.visible = True
    overlay.state = "project_browser"
    overlay._project_index = selected_index

    with (
        patch.object(main_menu_module, "_draw_rectangle_filled", fill_spy),
        patch.object(main_menu_module, "_draw_tb_rectangle_outline", outline_spy),
        patch.object(main_menu_module.optional_arcade.arcade, "Text", TextSpy),
        patch.object(overlay, "_project_items", return_value=list(PROJECT_ITEMS)),
    ):
        overlay.draw()

    return events, text_calls


def test_project_browser_cover_is_opaque_full_window() -> None:
    events, _text_calls = _capture_project_browser_draw()

    assert events[0] == ("fill", (8, 10, 14, 255))


def test_project_browser_title_block_draws_mesh_and_subtitle() -> None:
    _events, text_calls = _capture_project_browser_draw()
    by_text = {call["text"]: call for call in text_calls}

    assert by_text["MESH"]["font_size"] == 34
    assert by_text["MESH"]["bold"] is True
    assert by_text["MESH"]["anchor_x"] == "center"
    assert by_text["Project Browser"]["font_size"] == 15
    assert by_text["Project Browser"]["anchor_x"] == "center"


def test_project_browser_layout_returns_non_overlapping_cards_inside_panel() -> None:
    layout = compute_project_browser_menu_layout(1280, 720, item_count=4, selected_index=2)

    assert len(layout.cards) == 4
    assert layout.selected_card is layout.cards[2]
    for previous, current in zip(layout.cards, layout.cards[1:]):
        assert current.top < previous.bottom
    for card in layout.cards:
        assert layout.panel.left < card.left < card.right < layout.panel.right
        assert layout.panel.bottom < card.bottom < card.top < layout.panel.top


def test_project_browser_selected_card_uses_highlight_treatment() -> None:
    events, _text_calls = _capture_project_browser_draw(selected_index=1)

    assert ("fill", (24, 32, 42, 230)) in events
    assert ("fill", (35, 58, 70, 245)) in events
    assert ("fill", (116, 241, 218, 255)) in events
    assert ("outline", (80, 110, 125, 150)) in events
    assert ("outline", (108, 224, 210, 255)) in events


def test_project_browser_draw_order_panel_cards_footer() -> None:
    events, _text_calls = _capture_project_browser_draw(selected_index=1)
    gradient_colors = {
        (22, 28, 36, 245),
        (20, 25, 33, 245),
        (18, 22, 29, 245),
        (15, 19, 25, 245),
        (12, 16, 22, 245),
    }
    card_colors = {(24, 32, 42, 230), (35, 58, 70, 245)}

    gradient_indexes = [index for index, event in enumerate(events) if event[0] == "fill" and event[1] in gradient_colors]
    card_indexes = [index for index, event in enumerate(events) if event[0] == "fill" and event[1] in card_colors]
    footer_index = events.index(("text", "Enter Select  Esc Back  Up/Down Navigate"))

    assert gradient_indexes
    assert card_indexes
    assert max(gradient_indexes) < min(card_indexes)
    assert max(card_indexes) < footer_index
