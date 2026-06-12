from __future__ import annotations

from types import SimpleNamespace

import engine.optional_arcade as optional_arcade
from engine.input_runtime.capture_focus_query import get_capture_focus_snapshot


class _PanelsStub:
    def __init__(
        self,
        *,
        confirm_modal: bool = False,
        context_menu: bool = False,
        project_context_menu: bool = False,
        keybinds: bool = False,
    ) -> None:
        self._confirm_modal = confirm_modal
        self._context_menu = context_menu
        self._project_context_menu = project_context_menu
        self._keybinds = keybinds

    def is_confirm_modal_visible(self) -> bool:
        return self._confirm_modal

    def is_context_menu_open(self) -> bool:
        return self._context_menu

    def is_project_context_menu_open(self) -> bool:
        return self._project_context_menu

    def is_keybinds_visible(self) -> bool:
        return self._keybinds


def _make_controller(*, editor: SimpleNamespace | None, window: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(window=window, editor_controller=editor)


def test_snapshot_uses_session_flags_and_modifiers() -> None:
    session = SimpleNamespace(
        get_snapshot=lambda: SimpleNamespace(
            tile_paint_active=True,
            entity_paint_active=True,
            capture_mode_active=True,
            authoring_selected_active=True,
            project_explorer_focused=True,
            problems_panel_focused=True,
        ),
    )
    panels = _PanelsStub()
    editor = SimpleNamespace(active=True, session=session, panels=panels, project_explorer=SimpleNamespace(inline_rename_active=False))
    window = SimpleNamespace(
        editor_controller=editor,
        show_debug=True,
        command_palette_enabled=False,
        command_palette_prompt_active=False,
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(input_blocked=False),
        scene_persist_armed=False,
    )
    controller = _make_controller(editor=editor, window=window)

    mods = int(optional_arcade.arcade.key.MOD_CTRL | optional_arcade.arcade.key.MOD_SHIFT)
    snap = get_capture_focus_snapshot(controller, mods)
    assert snap.is_capture_mode_enabled is True
    assert snap.is_tile_paint_enabled is True
    assert snap.is_entity_paint_enabled is True
    assert snap.is_authoring_selected is True
    assert snap.is_project_explorer_focused is True
    assert snap.is_problems_focused is True
    assert snap.ctrl is True
    assert snap.shift is True


def test_context_menu_blocks_project_explorer_focus() -> None:
    session = SimpleNamespace(
        get_snapshot=lambda: SimpleNamespace(
            tile_paint_active=False,
            entity_paint_active=False,
            capture_mode_active=False,
            authoring_selected_active=False,
            project_explorer_focused=True,
            problems_panel_focused=False,
        ),
    )
    panels = _PanelsStub(project_context_menu=True)
    editor = SimpleNamespace(active=True, session=session, panels=panels, project_explorer=SimpleNamespace(inline_rename_active=False))
    window = SimpleNamespace(
        editor_controller=editor,
        show_debug=True,
        command_palette_enabled=False,
        command_palette_prompt_active=False,
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(input_blocked=False),
        scene_persist_armed=False,
    )
    controller = _make_controller(editor=editor, window=window)

    snap = get_capture_focus_snapshot(controller, 0)
    assert snap.is_context_menu_open is True
    assert snap.is_project_explorer_focused is False


def test_snapshot_falls_back_to_window_state_without_session() -> None:
    capture_state = SimpleNamespace(enabled=True)
    tile_paint_state = SimpleNamespace(enabled=True)
    entity_paint_state = SimpleNamespace(enabled=True)
    editor = SimpleNamespace(active=True, panels=_PanelsStub())
    window = SimpleNamespace(
        editor_controller=editor,
        show_debug=True,
        command_palette_enabled=False,
        command_palette_prompt_active=False,
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(input_blocked=False),
        scene_persist_armed=False,
        capture_state=capture_state,
        tile_paint_state=tile_paint_state,
        entity_paint_state=entity_paint_state,
        authoring_selected_entity_id="player",
    )
    controller = _make_controller(editor=editor, window=window)

    snap = get_capture_focus_snapshot(controller, 0)
    assert snap.is_capture_mode_enabled is True
    assert snap.is_tile_paint_enabled is True
    assert snap.is_entity_paint_enabled is True
    assert snap.is_authoring_selected is True
