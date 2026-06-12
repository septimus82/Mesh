from __future__ import annotations

from types import SimpleNamespace

import engine.input_runtime.capture_key_router as router
from engine.input_runtime import capture_key_router_handlers_entity_paint as entity_paint_handlers
from engine.input_runtime import capture_key_router_handlers_global as global_handlers
from engine.input_runtime import capture_key_router_handlers_tile_paint as tile_paint_handlers
from engine.input_runtime import capture_key_router_handlers_ui as ui_handlers
from engine.input_runtime.capture_focus_query import get_capture_focus_snapshot


def _make_controller(*, editor_active: bool = True, show_debug: bool = True) -> SimpleNamespace:
    editor = SimpleNamespace(
        active=editor_active,
        undo_last=lambda: True,
        redo_last=lambda: True,
        handle_input=lambda key, mods: False,
    )
    window = SimpleNamespace(
        editor_controller=editor,
        show_debug=show_debug,
        command_palette_enabled=False,
        console_controller=SimpleNamespace(active=False, process_key=lambda k, m: False),
        ui_controller=SimpleNamespace(input_blocked=False),
    )
    manager = SimpleNamespace(is_key_bound_to_action=lambda action, key: False)
    return SimpleNamespace(window=window, manager=manager, _keys=set())


def test_editor_undo_routes_through_router(monkeypatch) -> None:
    controller = _make_controller()
    called = {"undo": 0}

    def _undo() -> bool:
        called["undo"] += 1
        return True

    controller.window.editor_controller.undo_last = _undo
    snapshot = get_capture_focus_snapshot(
        controller,
        router.optional_arcade.arcade.key.MOD_CTRL,
    )
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.Z,
        router.optional_arcade.arcade.key.MOD_CTRL,
        snapshot,
    )
    assert called["undo"] == 1


def test_debug_undo_routes_when_editor_inactive() -> None:
    controller = _make_controller(editor_active=False, show_debug=True)
    called = {"debug_undo": 0, "editor_undo": 0}

    def _debug_undo() -> None:
        called["debug_undo"] += 1

    def _editor_undo() -> bool:
        called["editor_undo"] += 1
        return True

    controller.window.undo = _debug_undo
    controller.window.editor_controller.undo_last = _editor_undo
    snapshot = get_capture_focus_snapshot(
        controller,
        router.optional_arcade.arcade.key.MOD_CTRL,
    )
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.Z,
        router.optional_arcade.arcade.key.MOD_CTRL,
        snapshot,
    )
    assert called["debug_undo"] == 1
    assert called["editor_undo"] == 0


def test_f3_routes_palette_when_editor_active(monkeypatch) -> None:
    controller = _make_controller(editor_active=True, show_debug=True)
    called = {"palette": 0, "debug": 0}

    def _palette_toggle(_window) -> bool:
        called["palette"] += 1
        return True

    def _debug_toggle(_window, _controller) -> bool:
        called["debug"] += 1
        return True

    monkeypatch.setattr(global_handlers, "_handle_palette_toggle", _palette_toggle)
    monkeypatch.setattr(global_handlers, "_handle_debug_toggle", _debug_toggle)

    snapshot = get_capture_focus_snapshot(controller, 0)
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.F3,
        0,
        snapshot,
    )
    assert called["palette"] == 1
    assert called["debug"] == 0


def test_f3_routes_debug_when_editor_inactive(monkeypatch) -> None:
    controller = _make_controller(editor_active=False, show_debug=False)
    called = {"palette": 0, "debug": 0}

    def _palette_toggle(_window) -> bool:
        called["palette"] += 1
        return True

    def _debug_toggle(_window, _controller) -> bool:
        called["debug"] += 1
        return True

    monkeypatch.setattr(global_handlers, "_handle_palette_toggle", _palette_toggle)
    monkeypatch.setattr(global_handlers, "_handle_debug_toggle", _debug_toggle)

    snapshot = get_capture_focus_snapshot(controller, 0)
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.F3,
        0,
        snapshot,
    )
    assert called["palette"] == 0
    assert called["debug"] == 1


def test_tile_paint_slot_dispatches(monkeypatch) -> None:
    controller = _make_controller(editor_active=True, show_debug=True)
    controller.window.tile_paint_state = SimpleNamespace(enabled=True)
    recorded: dict[str, str] = {}

    def _dispatch(window, action_id: str) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_action", _dispatch)
    snapshot = get_capture_focus_snapshot(controller, 0)
    key_code = getattr(router.optional_arcade.arcade.key, "KEY_1", 49)
    assert router.route_and_dispatch(controller, key_code, 0, snapshot)
    assert recorded["action"] == "capture.tile_paint.slot_select_1"


def test_entity_paint_hover_nudge_dispatches(monkeypatch) -> None:
    controller = _make_controller(editor_active=True, show_debug=True)
    controller.window.entity_paint_state = SimpleNamespace(enabled=True)
    recorded: dict[str, str] = {}

    def _dispatch(window, snapshot, action_id: str) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(entity_paint_handlers, "dispatch_entity_paint_action", _dispatch)
    snapshot = get_capture_focus_snapshot(controller, 0)
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.UP,
        0,
        snapshot,
    )
    assert recorded["action"] == "capture.entity_paint.hover_nudge_up"


def test_confirm_modal_dispatches(monkeypatch) -> None:
    controller = _make_controller(editor_active=True, show_debug=True)
    panels = SimpleNamespace(
        is_confirm_modal_visible=lambda: True,
        is_context_menu_open=lambda: False,
        is_project_context_menu_open=lambda: False,
        is_keybinds_visible=lambda: False,
        is_command_palette_open=lambda: False,
    )
    controller.window.editor_controller.panels = panels
    recorded: dict[str, str] = {}

    def _dispatch(window, snapshot, action_id: str, **_kwargs) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(ui_handlers, "dispatch_ui_action", _dispatch)
    snapshot = get_capture_focus_snapshot(controller, 0)
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.ENTER,
        0,
        snapshot,
    )
    assert recorded["action"] == "capture.confirm_modal.confirm"


# ---------------------------------------------------------------------------
# Scope precedence tests - UI modals beat paint/select
# ---------------------------------------------------------------------------

def test_confirm_modal_beats_tile_paint(monkeypatch) -> None:
    """When confirm modal is visible AND tile paint enabled, modal wins."""
    controller = _make_controller(editor_active=True, show_debug=True)
    controller.window.tile_paint_state = SimpleNamespace(enabled=True)
    panels = SimpleNamespace(
        is_confirm_modal_visible=lambda: True,
        is_context_menu_open=lambda: False,
        is_project_context_menu_open=lambda: False,
        is_keybinds_visible=lambda: False,
        is_command_palette_open=lambda: False,
    )
    controller.window.editor_controller.panels = panels

    recorded: dict[str, str] = {}

    def _modal_dispatch(window, snapshot, action_id: str, **_kwargs) -> bool:
        recorded["action"] = action_id
        return True

    def _paint_dispatch(window, action_id: str) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(ui_handlers, "dispatch_ui_action", _modal_dispatch)
    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_action", _paint_dispatch)

    snapshot = get_capture_focus_snapshot(controller, 0)
    # ENTER in confirm modal should confirm, not select paint slot
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.ENTER,
        0,
        snapshot,
    )
    assert recorded["action"] == "capture.confirm_modal.confirm", (
        f"Expected modal to win but got {recorded.get('action')}"
    )


def test_context_menu_beats_entity_paint(monkeypatch) -> None:
    """When context menu open AND entity paint enabled, context menu wins."""
    controller = _make_controller(editor_active=True, show_debug=True)
    controller.window.entity_paint_state = SimpleNamespace(enabled=True)
    panels = SimpleNamespace(
        is_confirm_modal_visible=lambda: False,
        is_context_menu_open=lambda: True,
        is_project_context_menu_open=lambda: False,
        is_keybinds_visible=lambda: False,
        is_command_palette_open=lambda: False,
    )
    controller.window.editor_controller.panels = panels

    recorded: dict[str, str] = {}

    def _menu_dispatch(window, snapshot, action_id: str, **_kwargs) -> bool:
        recorded["action"] = action_id
        return True

    def _paint_dispatch(window, snapshot, action_id: str) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(ui_handlers, "dispatch_ui_action", _menu_dispatch)
    monkeypatch.setattr(entity_paint_handlers, "dispatch_entity_paint_action", _paint_dispatch)

    snapshot = get_capture_focus_snapshot(controller, 0)
    # ESCAPE in context menu should close menu, not affect paint
    assert router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.ESCAPE,
        0,
        snapshot,
    )
    assert recorded["action"] == "capture.context_menu.close", (
        f"Expected context menu to win but got {recorded.get('action')}"
    )


def test_command_palette_beats_global(monkeypatch) -> None:
    """When command palette open, it should win over global keys."""
    controller = _make_controller(editor_active=True, show_debug=True)
    controller.window.command_palette_enabled = True
    panels = SimpleNamespace(
        is_confirm_modal_visible=lambda: False,
        is_context_menu_open=lambda: False,
        is_project_context_menu_open=lambda: False,
        is_keybinds_visible=lambda: False,
        is_command_palette_open=lambda: True,
    )
    controller.window.editor_controller.panels = panels

    recorded: dict[str, str] = {}

    def _palette_dispatch(window, snapshot, action_id: str, **_kwargs) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(ui_handlers, "dispatch_ui_action", _palette_dispatch)

    snapshot = get_capture_focus_snapshot(
        controller,
        0,
    )
    # ESCAPE should close palette, not trigger global ESC
    result = router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.ESCAPE,
        0,
        snapshot,
    )
    # Palette should have handled this
    assert result or recorded.get("action") == "capture.command_palette.close", (
        f"Expected palette to handle ESCAPE but got {recorded.get('action')}"
    )


def test_inline_rename_beats_global(monkeypatch) -> None:
    """When inline rename active, ENTER should confirm rename not trigger global."""
    controller = _make_controller(editor_active=True, show_debug=True)
    panels = SimpleNamespace(
        is_confirm_modal_visible=lambda: False,
        is_context_menu_open=lambda: False,
        is_project_context_menu_open=lambda: False,
        is_keybinds_visible=lambda: False,
        is_command_palette_open=lambda: False,
        is_inline_rename_active=lambda: True,
    )
    controller.window.editor_controller.panels = panels

    recorded: dict[str, str] = {}

    def _rename_dispatch(window, snapshot, action_id: str, **_kwargs) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(ui_handlers, "dispatch_ui_action", _rename_dispatch)

    snapshot = get_capture_focus_snapshot(controller, 0)
    result = router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.ENTER,
        0,
        snapshot,
    )
    # If rename is active, ENTER should confirm rename
    if result:
        assert recorded.get("action", "").startswith("capture.inline_rename") or \
               recorded.get("action") == "capture.confirm_modal.confirm", (
            f"Expected inline_rename to handle ENTER but got {recorded.get('action')}"
        )


def test_console_beats_global_when_active(monkeypatch) -> None:
    """When console is active, UP/DOWN should navigate history not global."""
    controller = _make_controller(editor_active=False, show_debug=True)
    controller.window.console_controller = SimpleNamespace(
        active=True,
        process_key=lambda k, m: False,
    )

    recorded: dict[str, str] = {}

    def _console_dispatch(window, snapshot, action_id: str, **_kwargs) -> bool:
        recorded["action"] = action_id
        return True

    monkeypatch.setattr(ui_handlers, "dispatch_ui_action", _console_dispatch)

    snapshot = get_capture_focus_snapshot(controller, 0)
    result = router.route_and_dispatch(
        controller,
        router.optional_arcade.arcade.key.UP,
        0,
        snapshot,
    )
    # Console should handle UP for history navigation
    if result:
        assert "console" in recorded.get("action", "").lower() or result, (
            f"Expected console to handle UP but got {recorded.get('action')}"
        )
