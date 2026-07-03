from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.editor_dock_controller import EditorDockController
from engine.game_parts.ui_dispatcher import init_ui_dispatcher
from engine.ui_contract import PERSISTENT_UI_ATTRS
from engine.ui_controller import UIController

pytestmark = pytest.mark.fast


_EDITOR_PERSISTENT_OVERLAY_ATTRS: tuple[str, ...] = (
    "command_palette_overlay",
    "editor_command_palette_overlay",
    "editor_shell_overlay",
    "menu_bar_overlay",
    "context_menu_overlay",
    "entity_panels_overlay",
    "component_inspector_overlay",
    "hd2d_settings_panel_overlay",
    "editor_status_bar_overlay",
    "scene_switcher_overlay",
    "scene_browser_overlay",
    "project_explorer_overlay",
    "asset_browser_overlay",
    "item_editor_overlay",
    "prefab_editor_overlay",
    "quest_editor_overlay",
    "undo_history_overlay",
    "problems_panel_overlay",
    "debug_panels_overlay",
    "find_everything_overlay",
    "light_occluder_overlay",
    "selection_outline_overlay",
    "editor_hover_highlight_overlay",
    "marquee_select_overlay",
    "editor_gizmo_overlay",
    "editor_tooltip_overlay",
    "editor_cursor_hint_overlay",
)


@dataclass(frozen=True)
class _DockScenario:
    left_tab: str
    right_tab: str


_DOCK_SCENARIOS: tuple[_DockScenario, ...] = (
    _DockScenario("Project", "Inspector"),
    _DockScenario("Scene", "Assets"),
    _DockScenario("Outliner", "Items"),
    _DockScenario("Outliner", "Prefabs"),
    _DockScenario("Outliner", "Quests"),
    _DockScenario("Outliner", "History"),
    _DockScenario("Outliner", "Problems"),
    _DockScenario("Outliner", "Debug"),
)


class _DummyText:
    def __init__(self, *_args, **_kwargs) -> None:
        self.position = (0, 0)
        self.rotation = 0

    def draw(self) -> None:
        return


def _install_draw_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "draw_text",
        "draw_rectangle_filled",
        "draw_rectangle_outline",
        "draw_lrbt_rectangle_filled",
        "draw_lrbt_rectangle_outline",
        "draw_line",
        "draw_circle_outline",
        "draw_circle_filled",
        "draw_line_strip",
    ):
        if hasattr(optional_arcade.arcade, name):
            monkeypatch.setattr(optional_arcade.arcade, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(optional_arcade.arcade, "Text", _DummyText, raising=False)


def _make_window() -> SimpleNamespace:
    window = SimpleNamespace(width=800, height=600, text_cache=None)
    window.ui_controller = UIController(window)
    window.register_ui_element = lambda element, **kwargs: window.ui_controller.register_ui_element(
        element, **kwargs
    )
    window.clear_ui_elements = lambda: window.ui_controller.clear_ui_elements()
    window.engine_config = SimpleNamespace(debug_mode=False)
    window.scene_controller = SimpleNamespace(
        current_scene_path="scenes/test_scene.json",
        get_authored_scene_payload=lambda: {"entities": []},
    )
    window.input_controller = SimpleNamespace(mouse_x=0.0, mouse_y=0.0)
    window.screen_to_world = lambda x, y: (x, y)
    editor = SimpleNamespace(
        active=True,
        window=window,
        dock=EditorDockController(None),
        ui_layers=SimpleNamespace(register_layer=lambda *args, **kwargs: None),
        providers=SimpleNamespace(),
        selected_entity=None,
        scene_dirty=False,
        tool_mode="MOVE",
        _selected_entity_ids=[],
        _primary_selected_id=None,
        _problems_issues=[],
        _entity_panels_outliner_lines=lambda: [],
        _entity_panels_inspector_lines=lambda: ["No selection"],
    )
    window.editor_controller = editor
    init_ui_dispatcher(window)
    return window


def test_persistent_editor_overlays_draw_without_import_or_attribute_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_draw_stubs(monkeypatch)
    missing_contract_attrs = [
        attr for attr in _EDITOR_PERSISTENT_OVERLAY_ATTRS if attr not in PERSISTENT_UI_ATTRS
    ]
    assert missing_contract_attrs == []

    window = _make_window()
    unexpected_errors: list[str] = []
    ignored_errors: list[str] = []
    editor = window.editor_controller
    dock = getattr(editor, "dock", None)

    for scenario in _DOCK_SCENARIOS:
        if dock is not None:
            dock.set_left_tab(scenario.left_tab, force=True)
            dock.set_right_tab(scenario.right_tab, force=True)
        editor.scene_browser_active = scenario.left_tab == "Scene"
        editor.entity_panels_active = scenario.left_tab == "Outliner" or scenario.right_tab == "Inspector"
        editor.asset_browser_active = scenario.right_tab == "Assets"

        for attr_name in _EDITOR_PERSISTENT_OVERLAY_ATTRS:
            overlay = getattr(window, attr_name, None)
            draw = getattr(overlay, "draw", None)
            if not callable(draw):
                continue
            try:
                draw()
            except (ImportError, AttributeError, ModuleNotFoundError) as exc:
                unexpected_errors.append(
                    f"{attr_name} {scenario.left_tab}/{scenario.right_tab}: "
                    f"{type(exc).__name__}: {exc}"
                )
            except Exception as exc:  # noqa: BLE001
                ignored_errors.append(
                    f"{attr_name} {scenario.left_tab}/{scenario.right_tab}: "
                    f"{type(exc).__name__}: {exc}"
                )

    assert unexpected_errors == [], "\n".join(unexpected_errors)
