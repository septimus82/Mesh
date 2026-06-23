from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.ui_overlays import dialogue_editor_overlay, item_editor_overlay, prefab_editor_overlay, quest_editor_overlay
from engine.ui_overlays.editor_database_form_helpers import FormColors
from engine.ui_overlays.theme import EDITOR_THEME

pytestmark = pytest.mark.fast


def test_editor_theme_tokens_pin_current_values() -> None:
    assert EDITOR_THEME.transparent == (0, 0, 0, 0)
    assert EDITOR_THEME.text_primary == (220, 220, 230, 255)
    assert EDITOR_THEME.text_dim == (150, 150, 160, 255)
    assert EDITOR_THEME.text_header == (200, 210, 230, 255)
    assert EDITOR_THEME.selected_row_bg == (90, 140, 200, 140)
    assert EDITOR_THEME.action_text == (100, 200, 255, 255)
    assert EDITOR_THEME.error_text == (255, 120, 120, 255)
    assert EDITOR_THEME.warning_text == (255, 200, 60, 255)
    assert EDITOR_THEME.panel_bg == (35, 35, 40, 250)
    assert EDITOR_THEME.panel_border == (60, 60, 70, 255)
    assert EDITOR_THEME.chrome_bg == (30, 30, 35, 255)
    assert EDITOR_THEME.chrome_border == (60, 60, 70, 255)
    assert EDITOR_THEME.input_bg == (22, 22, 28, 190)
    assert EDITOR_THEME.input_bg_focused == (30, 30, 36, 220)
    assert EDITOR_THEME.input_border == (90, 90, 100, 140)
    assert EDITOR_THEME.input_border_focused == (100, 200, 255, 180)
    assert EDITOR_THEME.severity_info_bg == (32, 36, 44)
    assert EDITOR_THEME.severity_info_border == (150, 190, 255)
    assert EDITOR_THEME.severity_info_text == (255, 255, 255)
    assert EDITOR_THEME.severity_warning_bg == (64, 44, 20)
    assert EDITOR_THEME.severity_warning_border == (255, 191, 92)
    assert EDITOR_THEME.severity_warning_text == (255, 244, 224)
    assert EDITOR_THEME.severity_error_bg == (72, 24, 24)
    assert EDITOR_THEME.severity_error_border == (255, 110, 110)
    assert EDITOR_THEME.severity_error_text == (255, 255, 255)


def test_editor_theme_database_form_values_match_current_form_colors() -> None:
    assert FormColors(
        text=EDITOR_THEME.text_primary,
        dim=EDITOR_THEME.text_dim,
        button=EDITOR_THEME.action_text,
    ) == FormColors(
        text=(220, 220, 230, 255),
        dim=(150, 150, 160, 255),
        button=(100, 200, 255, 255),
    )


def test_prefab_editor_form_colors_resolve_to_theme_tokens() -> None:
    assert prefab_editor_overlay.PREFAB_EDITOR_TEXT_COLOR == EDITOR_THEME.text_primary
    assert prefab_editor_overlay.PREFAB_EDITOR_DIM_COLOR == EDITOR_THEME.text_dim
    assert prefab_editor_overlay.PREFAB_EDITOR_BUTTON_COLOR == EDITOR_THEME.action_text
    assert prefab_editor_overlay._PREFAB_FORM_COLORS == FormColors(
        text=EDITOR_THEME.text_primary,
        dim=EDITOR_THEME.text_dim,
        button=EDITOR_THEME.action_text,
    )


def test_item_editor_form_colors_resolve_to_theme_tokens() -> None:
    assert item_editor_overlay.ITEM_EDITOR_TEXT_COLOR == EDITOR_THEME.text_primary
    assert item_editor_overlay.ITEM_EDITOR_DIM_COLOR == EDITOR_THEME.text_dim
    assert item_editor_overlay.ITEM_EDITOR_BUTTON_COLOR == EDITOR_THEME.action_text
    assert item_editor_overlay._ITEM_FORM_COLORS == FormColors(
        text=EDITOR_THEME.text_primary,
        dim=EDITOR_THEME.text_dim,
        button=EDITOR_THEME.action_text,
    )


def test_quest_editor_form_colors_resolve_to_theme_tokens() -> None:
    assert quest_editor_overlay.QUEST_EDITOR_TEXT_COLOR == EDITOR_THEME.text_primary
    assert quest_editor_overlay.QUEST_EDITOR_DIM_COLOR == EDITOR_THEME.text_dim
    assert quest_editor_overlay.QUEST_EDITOR_BUTTON_COLOR == EDITOR_THEME.action_text
    assert quest_editor_overlay._QUEST_FORM_COLORS == FormColors(
        text=EDITOR_THEME.text_primary,
        dim=EDITOR_THEME.text_dim,
        button=EDITOR_THEME.action_text,
    )


def test_dialogue_editor_form_colors_resolve_to_theme_tokens() -> None:
    assert dialogue_editor_overlay.DIALOGUE_EDITOR_TEXT_COLOR == EDITOR_THEME.text_primary
    assert dialogue_editor_overlay.DIALOGUE_EDITOR_DIM_COLOR == EDITOR_THEME.text_dim
    assert dialogue_editor_overlay.DIALOGUE_EDITOR_BUTTON_COLOR == EDITOR_THEME.action_text
    assert dialogue_editor_overlay.DIALOGUE_EDITOR_WARN_COLOR == EDITOR_THEME.warning_text
    assert dialogue_editor_overlay._DIALOGUE_FORM_COLORS == FormColors(
        text=EDITOR_THEME.text_primary,
        dim=EDITOR_THEME.text_dim,
        button=EDITOR_THEME.action_text,
    )


def test_prefab_editor_overlay_uses_theme_tokens_not_local_color_tuples() -> None:
    _assert_overlay_uses_theme_tokens_not_local_color_tuples(prefab_editor_overlay)


def test_database_editor_overlays_use_theme_tokens_not_local_color_tuples() -> None:
    for overlay_module in (item_editor_overlay, quest_editor_overlay, dialogue_editor_overlay):
        _assert_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module)


def _assert_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module: object) -> None:
    source_path = Path(overlay_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    raw_color_tuples: list[tuple[int, ...]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Tuple):
            continue
        values: list[int] = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, int):
                break
            values.append(element.value)
        else:
            if len(values) in {3, 4} and all(0 <= value <= 255 for value in values):
                raw_color_tuples.append(tuple(values))

    assert raw_color_tuples == []
    assert "EDITOR_THEME" in source_path.read_text(encoding="utf-8")
