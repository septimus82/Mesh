from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import engine.ui_overlays.main_menu_overlay as main_menu_module
from engine.ui_overlays.main_menu_overlay import (
    MainMenuOverlay,
    compute_menu_panel_layout,
    compute_project_browser_menu_layout,
)

pytestmark = [pytest.mark.fast]


def _capture_draw(overlay: MainMenuOverlay) -> tuple[list[tuple[str, Any]], list[dict[str, Any]]]:
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

    with (
        patch.object(main_menu_module, "_draw_rectangle_filled", fill_spy),
        patch.object(main_menu_module, "_draw_tb_rectangle_outline", outline_spy),
        patch.object(main_menu_module.optional_arcade.arcade, "Text", TextSpy),
    ):
        overlay.draw()

    return events, text_calls


def _overlay(state: str) -> MainMenuOverlay:
    window = SimpleNamespace(width=1280, height=720, paused=False)
    overlay = MainMenuOverlay(window)
    overlay.visible = True
    overlay.state = state
    return overlay


def _card_fill_count(events: list[tuple[str, Any]]) -> int:
    card_colors = {(24, 32, 42, 230), (35, 58, 70, 245)}
    return sum(1 for kind, value in events if kind == "fill" and value in card_colors)


def test_title_screen_draws_mesh_title_and_one_card_per_item() -> None:
    overlay = _overlay("main")
    with patch.object(
        overlay,
        "_items",
        return_value=[("Start Game", "start_game"), ("Settings", "settings"), ("Quit", "quit")],
    ):
        events, text_calls = _capture_draw(overlay)

    by_text = {call["text"]: call for call in text_calls}
    assert by_text["MESH"]["bold"] is True
    assert by_text["Title Screen"]["anchor_x"] == "center"
    assert _card_fill_count(events) == 3
    layout = compute_menu_panel_layout(1280, 720, item_count=3, selected_index=0)
    for previous, current in zip(layout.cards, layout.cards[1:]):
        assert current.top < previous.bottom
    for card in layout.cards:
        assert layout.panel.left < card.left < card.right < layout.panel.right
        assert layout.panel.bottom < card.bottom < card.top < layout.panel.top


def test_title_screen_selected_index_gets_highlight_treatment() -> None:
    overlay = _overlay("main")
    overlay._selection_index = 1
    with patch.object(overlay, "_items", return_value=[("Start Game", "start_game"), ("Settings", "settings")]):
        events, text_calls = _capture_draw(overlay)

    assert ("fill", (35, 58, 70, 245)) in events
    assert ("fill", (116, 241, 218, 255)) in events
    assert ("outline", (108, 224, 210, 255)) in events
    assert next(call for call in text_calls if call["text"] == "Settings")["bold"] is True


def test_create_project_template_draws_template_cards_with_descriptions() -> None:
    class Template:
        def __init__(self, title: str, description: str) -> None:
            self.title = title
            self.description = description

    overlay = _overlay("create_project_template")
    overlay._template_index = 1
    templates = [Template("Blank", "Empty project"), Template("Demo", "Starter scene")]
    with patch("engine.project_templates.list_templates", return_value=templates):
        events, text_calls = _capture_draw(overlay)

    assert ("text", "New Project") in events
    assert ("text", "Empty project") in events
    assert ("text", "Starter scene") in events
    assert _card_fill_count(events) == 2
    assert next(call for call in text_calls if call["text"] == "Demo")["bold"] is True


def test_settings_draws_cards_with_values_and_selected_highlight() -> None:
    overlay = _overlay("settings")
    overlay._settings_index = 2
    overlay._runtime_settings = lambda: SimpleNamespace(
        music_volume=1.0,
        sfx_volume=0.35,
        fog_enabled=True,
        soft_shadows_enabled=False,
    )

    events, text_calls = _capture_draw(overlay)

    assert ("text", "Settings") in events
    assert ("text", "100%") in events
    assert ("text", "35%") in events
    assert ("text", "ON") in events
    assert ("text", "OFF") in events
    assert _card_fill_count(events) == len(main_menu_module.SETTINGS_ROWS)
    assert next(call for call in text_calls if call["text"] == "Fog")["bold"] is True


def test_shared_refactor_preserves_get_lines_and_project_browser_layout() -> None:
    overlay = _overlay("main")
    with patch.object(overlay, "_has_continue", return_value=False):
        assert overlay.get_lines() == [
            "TITLE SCREEN",
            "",
            "> Start Game",
            "  Settings",
            "  Run Web Demo (Local Preview)",
            "  Export Web Demo (.zip)",
            "  Quit",
            "",
            "Enter Select  Esc Back  Up/Down Navigate",
        ]

    class Template:
        title = "Blank"
        description = "Empty"

    overlay.state = "create_project_template"
    with patch("engine.project_templates.list_templates", return_value=[Template()]):
        assert overlay.get_lines() == [
            "CREATE NEW PROJECT",
            "",
            "Choose Template:",
            "",
            "> Blank",
            "",
            "Info: Empty",
            "",
            "[Enter] Next  [Esc] Cancel",
        ]

    assert compute_menu_panel_layout(1280, 720, 3, 1) == compute_project_browser_menu_layout(1280, 720, 3, 1)
