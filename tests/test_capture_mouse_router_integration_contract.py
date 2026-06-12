from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.input_runtime.capture_mouse_router as mouse_router
from engine.input_runtime import capture_mouse_router_handlers_authoring_selected as authoring_selected_handlers

# Paint handlers - now split into per-scope modules
from engine.input_runtime import capture_mouse_router_handlers_capture_mode as capture_mode_handlers
from engine.input_runtime import capture_mouse_router_handlers_command_palette as command_palette_handlers
from engine.input_runtime import capture_mouse_router_handlers_confirm_modal as confirm_modal_handlers
from engine.input_runtime import capture_mouse_router_handlers_console as console_handlers
from engine.input_runtime import capture_mouse_router_handlers_context_menu as context_menu_handlers
from engine.input_runtime import capture_mouse_router_handlers_entity_paint as entity_paint_handlers

# Select handlers - now split into per-scope modules
from engine.input_runtime import capture_mouse_router_handlers_entity_select as entity_select_handlers
from engine.input_runtime import capture_mouse_router_handlers_global as global_handlers
from engine.input_runtime import capture_mouse_router_handlers_keybinds as keybinds_handlers
from engine.input_runtime import capture_mouse_router_handlers_problems as problems_handlers
from engine.input_runtime import capture_mouse_router_handlers_project_explorer as project_explorer_handlers
from engine.input_runtime import capture_mouse_router_handlers_tile_paint as tile_paint_handlers
from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot


def _make_snapshot(**overrides) -> CaptureFocusSnapshot:
    defaults = {
        "is_confirm_modal_open": False,
        "is_context_menu_open": False,
        "is_keybinds_recording": False,
        "is_keybinds_open": False,
        "is_inline_rename_active": False,
        "is_command_palette_open": False,
        "is_command_palette_prompt_active": False,
        "is_console_active": False,
        "is_project_explorer_focused": False,
        "is_problems_focused": False,
        "is_palette_mode_enabled": False,
        "is_capture_mode_enabled": False,
        "is_tile_paint_enabled": False,
        "is_entity_paint_enabled": False,
        "is_entity_select_active": False,
        "is_authoring_selected": False,
        "show_debug": False,
        "editor_active": False,
        "ui_blocked": False,
        "scene_persist_armed": False,
        "ctrl": False,
        "alt": False,
        "shift": False,
    }
    defaults.update(overrides)
    return CaptureFocusSnapshot(**defaults)


def _make_controller() -> SimpleNamespace:
    return SimpleNamespace(window=SimpleNamespace())


def test_ui_click_consumes_when_confirm_modal_open(monkeypatch) -> None:
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(confirm_modal_handlers, "dispatch_confirm_modal_mouse", _dispatch)
    snapshot = _make_snapshot(is_confirm_modal_open=True, editor_active=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.confirm_modal"


def test_paint_drag_consumes_in_tile_paint_mode(monkeypatch) -> None:
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_tile_paint_enabled=True)
    event = MouseEvent(kind="press", button=1, x=0.0, y=0.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.tile_paint.press"


def test_selection_drag_consumes_in_select_mode(monkeypatch) -> None:
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(entity_select_handlers, "dispatch_entity_select_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_entity_select_active=True)
    event = MouseEvent(kind="press", button=1, x=2.0, y=3.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.entity_select.press"


def test_scroll_consumes_in_paint_scope(monkeypatch) -> None:
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_tile_paint_enabled=True)
    event = MouseEvent(kind="scroll", button=None, x=0.0, y=0.0, scroll_y=1.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.tile_paint.scroll"


def test_global_mouse_falls_back_when_no_scopes(monkeypatch) -> None:
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return False

    monkeypatch.setattr(global_handlers, "dispatch_global_mouse", _dispatch)
    snapshot = _make_snapshot()
    event = MouseEvent(kind="press", button=1, x=0.0, y=0.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot) is False
    assert called["action"] == "mouse.global"


# ---------------------------------------------------------------------------
# UI scope routing tests - verify each modal scope dispatches correctly
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_context_menu_mouse_routes_to_handler(monkeypatch) -> None:
    """Context menu scope routes to context_menu handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(context_menu_handlers, "dispatch_context_menu_mouse", _dispatch)
    snapshot = _make_snapshot(is_context_menu_open=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.context_menu"


@pytest.mark.fast
def test_keybinds_mouse_routes_to_handler(monkeypatch) -> None:
    """Keybinds scope routes to keybinds handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(keybinds_handlers, "dispatch_keybinds_mouse", _dispatch)
    snapshot = _make_snapshot(is_keybinds_open=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.keybinds"


@pytest.mark.fast
def test_command_palette_mouse_routes_to_handler(monkeypatch) -> None:
    """Command palette scope routes to command_palette handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(command_palette_handlers, "dispatch_command_palette_mouse", _dispatch)
    # Command palette scope requires show_debug=True
    snapshot = _make_snapshot(is_command_palette_open=True, show_debug=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.command_palette"


@pytest.mark.fast
def test_console_mouse_routes_to_handler(monkeypatch) -> None:
    """Console scope routes to console handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(console_handlers, "dispatch_console_mouse", _dispatch)
    snapshot = _make_snapshot(is_console_active=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.console"


@pytest.mark.fast
def test_project_explorer_mouse_routes_to_handler(monkeypatch) -> None:
    """Project explorer scope routes to project_explorer handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(project_explorer_handlers, "dispatch_project_explorer_mouse", _dispatch)
    # Project explorer scope requires editor_active=True
    snapshot = _make_snapshot(is_project_explorer_focused=True, editor_active=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.project_explorer"


@pytest.mark.fast
def test_problems_mouse_routes_to_handler(monkeypatch) -> None:
    """Problems scope routes to problems handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(problems_handlers, "dispatch_problems_mouse", _dispatch)
    # Problems scope requires editor_active=True
    snapshot = _make_snapshot(is_problems_focused=True, editor_active=True)
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.problems"


# ---------------------------------------------------------------------------
# Prefix routing determinism tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_prefix_registry_determinism() -> None:
    """Prefix registry returns same handler for same action_id every time."""
    from engine.input_runtime.capture_mouse_router import MOUSE_PREFIX_DISPATCH, _get_handler

    # Test multiple lookups for the same action_id
    test_actions = [
        "mouse.confirm_modal",
        "mouse.tile_paint.press",
        "mouse.entity_select.press",
        "mouse.global",
    ]

    for action_id in test_actions:
        handlers = []
        for _ in range(3):
            for prefix, module_name, func_name in MOUSE_PREFIX_DISPATCH:
                if action_id.startswith(prefix) or action_id == prefix:
                    handlers.append(_get_handler(module_name, func_name))
                    break

        assert len(set(id(h) for h in handlers)) == 1, f"Non-deterministic handler for {action_id}"


@pytest.mark.fast
def test_longer_prefix_wins() -> None:
    """When multiple prefixes match, the longer one wins (appears first in registry)."""
    from engine.input_runtime.capture_mouse_router import MOUSE_PREFIX_DISPATCH

    # mouse.capture_mode.press should match "mouse.capture_mode." not "mouse."
    action_id = "mouse.capture_mode.press"

    matched_prefix = None
    for prefix, _, _ in MOUSE_PREFIX_DISPATCH:
        if action_id.startswith(prefix) or action_id == prefix:
            matched_prefix = prefix
            break

    assert matched_prefix == "mouse.capture_mode.", (
        f"Expected 'mouse.capture_mode.' but got '{matched_prefix}'"
    )


# ---------------------------------------------------------------------------
# Per-scope handler integration tests
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_capture_mode_drag_routes_correctly(monkeypatch) -> None:
    """Capture mode camera drag routes to capture_mode handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(capture_mode_handlers, "dispatch_capture_mode_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_capture_mode_enabled=True)
    event = MouseEvent(kind="press", button=1, x=50.0, y=50.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.capture_mode.press"


@pytest.mark.fast
def test_capture_mode_release_routes_correctly(monkeypatch) -> None:
    """Capture mode release routes to capture_mode handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(capture_mode_handlers, "dispatch_capture_mode_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_capture_mode_enabled=True)
    event = MouseEvent(kind="release", button=1, x=50.0, y=50.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.capture_mode.release"


@pytest.mark.fast
def test_tile_paint_scroll_routes_correctly(monkeypatch) -> None:
    """Tile paint scroll (brush size/layer cycling) routes to tile_paint handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_tile_paint_enabled=True)
    event = MouseEvent(kind="scroll", button=None, x=0.0, y=0.0, scroll_y=1.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.tile_paint.scroll"


@pytest.mark.fast
def test_tile_paint_release_routes_correctly(monkeypatch) -> None:
    """Tile paint release (stroke commit) routes to tile_paint handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_tile_paint_enabled=True)
    event = MouseEvent(kind="release", button=1, x=10.0, y=20.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.tile_paint.release"


@pytest.mark.fast
def test_entity_paint_press_routes_correctly(monkeypatch) -> None:
    """Entity paint stamp routes to entity_paint handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(entity_paint_handlers, "dispatch_entity_paint_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_entity_paint_enabled=True)
    event = MouseEvent(kind="press", button=1, x=100.0, y=100.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.entity_paint.press"


@pytest.mark.fast
def test_entity_paint_scroll_routes_correctly(monkeypatch) -> None:
    """Entity paint scroll (prefab cycling) routes to entity_paint handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(entity_paint_handlers, "dispatch_entity_paint_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_entity_paint_enabled=True)
    event = MouseEvent(kind="scroll", button=None, x=0.0, y=0.0, scroll_y=-1.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.entity_paint.scroll"


@pytest.mark.fast
def test_entity_select_release_routes_correctly(monkeypatch) -> None:
    """Entity select release (box selection commit) routes to entity_select handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(entity_select_handlers, "dispatch_entity_select_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_entity_select_active=True)
    event = MouseEvent(kind="release", button=1, x=200.0, y=200.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.entity_select.release"


@pytest.mark.fast
def test_authoring_selected_press_routes_correctly(monkeypatch) -> None:
    """Authoring selected press (property edit) routes to authoring_selected handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(authoring_selected_handlers, "dispatch_authoring_selected_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_authoring_selected=True)
    event = MouseEvent(kind="press", button=1, x=50.0, y=50.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.authoring_selected.press"


@pytest.mark.fast
def test_authoring_selected_release_routes_correctly(monkeypatch) -> None:
    """Authoring selected release routes to authoring_selected handler."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(authoring_selected_handlers, "dispatch_authoring_selected_mouse", _dispatch)
    snapshot = _make_snapshot(show_debug=True, is_authoring_selected=True)
    event = MouseEvent(kind="release", button=1, x=50.0, y=50.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.authoring_selected.release"


# ---------------------------------------------------------------------------
# Scope precedence tests - UI modals beat paint/select
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_confirm_modal_beats_tile_paint(monkeypatch) -> None:
    """When confirm modal is open AND tile paint is enabled, modal wins."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch_modal(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    def _dispatch_paint(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(confirm_modal_handlers, "dispatch_confirm_modal_mouse", _dispatch_modal)
    monkeypatch.setattr(tile_paint_handlers, "dispatch_tile_paint_mouse", _dispatch_paint)

    # Both scopes active - modal should win due to higher priority
    snapshot = _make_snapshot(
        is_confirm_modal_open=True,
        is_tile_paint_enabled=True,
        show_debug=True,
        editor_active=True,
    )
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.confirm_modal", (
        f"Expected modal to win but got {called.get('action')}"
    )


@pytest.mark.fast
def test_context_menu_beats_entity_select(monkeypatch) -> None:
    """When context menu is open AND entity select is active, context menu wins."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch_menu(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    def _dispatch_select(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(context_menu_handlers, "dispatch_context_menu_mouse", _dispatch_menu)
    monkeypatch.setattr(entity_select_handlers, "dispatch_entity_select_mouse", _dispatch_select)

    # Both scopes active - context menu should win due to higher priority
    snapshot = _make_snapshot(
        is_context_menu_open=True,
        is_entity_select_active=True,
        show_debug=True,
    )
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.context_menu", (
        f"Expected context_menu to win but got {called.get('action')}"
    )


@pytest.mark.fast
def test_console_beats_capture_mode(monkeypatch) -> None:
    """When console is active AND capture mode is enabled, console wins."""
    controller = _make_controller()
    called: dict[str, str] = {}

    def _dispatch_console(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    def _dispatch_capture(ctrl, event, action_id: str) -> bool:
        called["action"] = action_id
        return True

    monkeypatch.setattr(console_handlers, "dispatch_console_mouse", _dispatch_console)
    monkeypatch.setattr(capture_mode_handlers, "dispatch_capture_mode_mouse", _dispatch_capture)

    # Both scopes active - console should win due to higher priority
    snapshot = _make_snapshot(
        is_console_active=True,
        is_capture_mode_enabled=True,
        show_debug=True,
    )
    event = MouseEvent(kind="press", button=1, x=10.0, y=10.0)
    assert mouse_router.route_and_dispatch_mouse(controller, event, snapshot)
    assert called["action"] == "mouse.console", (
        f"Expected console to win but got {called.get('action')}"
    )
