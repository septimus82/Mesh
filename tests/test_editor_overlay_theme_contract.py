from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.ui_overlays import (
    asset_browser_overlay,
    command_palette,
    common,
    component_inspector_overlay,
    confirm_modal_overlay,
    context_menu_overlay,
    debug_panels_overlay,
    dialogue_editor_overlay,
    editor_database_form_helpers,
    editor_feedback_overlay,
    editor_shell_overlay,
    editor_status_bar_overlay,
    editors,
    find_everything_overlay,
    inspector,
    item_editor_overlay,
    menu_bar_overlay,
    prefab_editor_overlay,
    problems_panel_overlay,
    project_explorer_context_menu_overlay,
    project_explorer_overlay,
    quest_editor_overlay,
    scene_browser_overlay,
    undo_history_overlay,
)
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


def test_editor_theme_panel_tokens_pin_current_values() -> None:
    assert EDITOR_THEME.field_border_idle == (85, 85, 95, 120)
    assert EDITOR_THEME.field_border_focus == (90, 120, 170, 180)
    assert EDITOR_THEME.panel_strong_bg == (18, 18, 22, 220)
    assert EDITOR_THEME.panel_strong_border == (100, 100, 110, 255)
    assert EDITOR_THEME.header_muted == (180, 200, 220, 255)
    assert EDITOR_THEME.text_dim_soft == (150, 150, 160, 200)
    assert EDITOR_THEME.accent_warm == (255, 220, 140, 255)
    assert EDITOR_THEME.tree_bg == (40, 40, 50, 255)
    assert EDITOR_THEME.tree_selected_bg == (80, 120, 180, 128)
    assert EDITOR_THEME.tree_accent == (120, 160, 220, 255)


def test_editor_theme_chrome_tokens_pin_current_values() -> None:
    assert EDITOR_THEME.chrome_accent == (70, 130, 180, 255)
    assert EDITOR_THEME.chrome_accent_bright == (80, 140, 200, 255)
    assert EDITOR_THEME.chrome_text == (220, 220, 220, 255)
    assert EDITOR_THEME.chrome_dim == (140, 140, 140, 255)
    assert EDITOR_THEME.chrome_separator == (100, 100, 100, 255)
    assert EDITOR_THEME.shell_bg == (45, 45, 50, 255)
    assert EDITOR_THEME.shell_bg_alt == (50, 50, 55, 255)
    assert EDITOR_THEME.menubar_bg == (40, 40, 45, 255)
    assert EDITOR_THEME.context_shadow == (0, 0, 0, 120)


def test_editor_theme_inspector_browser_tokens_pin_current_values() -> None:
    assert EDITOR_THEME.inspector_bg == (45, 45, 55, 255)
    assert EDITOR_THEME.inspector_border == (60, 80, 100, 255)
    assert EDITOR_THEME.inspector_selected == (70, 100, 140, 180)
    assert EDITOR_THEME.inspector_accent == (100, 180, 255, 255)
    assert EDITOR_THEME.inspector_dim == (140, 140, 150, 255)
    assert EDITOR_THEME.inspector_text_soft == (160, 160, 170, 255)
    assert EDITOR_THEME.inspector_text == (200, 200, 200, 255)
    assert EDITOR_THEME.browser_border == (100, 100, 100)
    assert EDITOR_THEME.browser_accent == (100, 200, 255)
    assert EDITOR_THEME.browser_white == (255, 255, 255)
    assert EDITOR_THEME.status_ok == (100, 255, 100)
    assert EDITOR_THEME.browser_text_dim == (170, 170, 180)
    assert EDITOR_THEME.browser_text == (180, 180, 180)
    assert EDITOR_THEME.browser_muted == (100, 100, 100)
    assert EDITOR_THEME.status_error == (255, 100, 100)
    assert EDITOR_THEME.status_warn == (255, 200, 100)
    assert EDITOR_THEME.overlay_white_soft == (255, 255, 255, 40)
    assert EDITOR_THEME.overlay_white == (255, 255, 255, 50)


def test_editor_theme_small_editor_tokens_pin_current_values() -> None:
    assert EDITOR_THEME.scrim_dim == (0, 0, 0, 200)
    assert EDITOR_THEME.scrim_dim_soft == (0, 0, 0, 170)
    assert EDITOR_THEME.scrim_dim_medium == (0, 0, 0, 180)
    assert EDITOR_THEME.black == (0, 0, 0)
    assert EDITOR_THEME.undo_selected == (70, 110, 150, 80)


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


@pytest.mark.parametrize(
    "overlay_module",
    [
        find_everything_overlay,
        scene_browser_overlay,
        problems_panel_overlay,
        debug_panels_overlay,
        project_explorer_overlay,
    ],
)
def test_panel_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module: object) -> None:
    _assert_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module)


@pytest.mark.parametrize(
    "overlay_module",
    [
        editor_shell_overlay,
        menu_bar_overlay,
        context_menu_overlay,
        project_explorer_context_menu_overlay,
    ],
)
def test_chrome_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module: object) -> None:
    _assert_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module)


@pytest.mark.parametrize(
    "overlay_module",
    [
        component_inspector_overlay,
        asset_browser_overlay,
    ],
)
def test_inspector_browser_overlay_uses_theme_tokens_not_local_color_tuples(
    overlay_module: object,
) -> None:
    _assert_overlay_uses_theme_tokens_not_local_color_tuples(overlay_module)


@pytest.mark.parametrize(
    "overlay_module",
    [
        command_palette,
        undo_history_overlay,
        confirm_modal_overlay,
        editor_status_bar_overlay,
        editors,
        common,
        inspector,
        editor_feedback_overlay,
        editor_database_form_helpers,
    ],
)
def test_small_editor_overlay_uses_theme_tokens_not_local_color_tuples(
    overlay_module: object,
) -> None:
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
