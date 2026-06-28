from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.dock_tab_registry import DOCK_TAB_TOOLTIPS, RIGHT_DOCK_TABS
from engine.editor.editor_dock_controller import EditorDockController
from engine.editor.editor_focus_model import is_text_input_active_for_controller
from engine.editor_runtime.editor_input_shortcut_handlers import is_text_input_active
from engine.ui_overlays.ai_chat_overlay import AIChatOverlay, build_transcript_lines, wrap_transcript_text
from tests.test_cocreative_chatbox_14a import _FakeClient, _FakeFactory, _run_chat_to_completion, _text, _tool_use
from tests.test_cocreative_live_ops import _entity_names, _make_controller


def test_ai_chat_dock_is_registered_and_toggleable() -> None:
    assert "AI Chat" in RIGHT_DOCK_TABS
    assert "AI Chat" in DOCK_TAB_TOOLTIPS

    class HostStub:
        def __init__(self) -> None:
            self.active = True
            self._menu_active = None
            self.entity_panels_active = False
            self.entity_panels_focus = ""
            self.asset_browser_active = False
            self.problems = SimpleNamespace(preview_open=False, close_preview=lambda _host: None)
            self.panels = SimpleNamespace(close_context_menu=lambda: None)
            self.search = SimpleNamespace(sync_search_focus=lambda: None)
            self.autosaved = False

        def _autosave_workspace(self) -> None:
            self.autosaved = True

    dock = EditorDockController(None, left_tab="Outliner", right_tab="Inspector")
    host = HostStub()

    assert dock.apply_tab_change(host, "right", "AI Chat") is True
    assert dock.right_tab == "AI Chat"
    assert host.autosaved is True


def test_ai_chat_send_and_cancel_click_dispatch_through_editor_mouse_router(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    controller.chat.current_input = "stage a crate"
    submit_calls: list[str] = []
    cancel_calls: list[bool] = []

    def submit_spy() -> dict[str, Any]:
        submit_calls.append(controller.chat.current_input)
        return {"ok": True}

    def cancel_spy() -> dict[str, Any]:
        cancel_calls.append(True)
        return {"ok": True}

    controller.chat.submit_current_input = submit_spy  # type: ignore[method-assign]
    controller.chat.cancel = cancel_spy  # type: ignore[method-assign]

    send_x, send_y = _button_center(overlay, "send")
    assert controller.handle_mouse_click(send_x, send_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    cancel_x, cancel_y = _button_center(overlay, "cancel")
    assert controller.handle_mouse_click(cancel_x, cancel_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert submit_calls == ["stage a crate"]
    assert cancel_calls == [True]


def test_ai_chat_text_input_routes_through_editor_text_and_key_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    input_x, input_y = _input_center(overlay)

    assert controller.handle_mouse_click(input_x, input_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    controller.handle_text_input("a")
    controller.handle_text_input("b")
    assert controller.chat.current_input == "ab"

    assert controller.handle_input(optional_arcade.arcade.key.BACKSPACE, 0) is True
    assert controller.chat.current_input == "a"

    submit_calls: list[str] = []

    def submit_spy() -> dict[str, Any]:
        submit_calls.append(controller.chat.current_input)
        return {"ok": True}

    controller.chat.submit_current_input = submit_spy  # type: ignore[method-assign]

    assert controller.handle_input(optional_arcade.arcade.key.ENTER, 0) is True
    assert submit_calls == ["a"]


def test_ai_chat_input_focus_marks_text_input_active(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    input_x, input_y = _input_center(overlay)

    assert is_text_input_active(controller) is False

    assert controller.handle_mouse_click(input_x, input_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert is_text_input_active(controller) is True
    assert is_text_input_active_for_controller("ai_chat", controller) is True

    assert controller.handle_input(optional_arcade.arcade.key.ESCAPE, 0) is True
    assert is_text_input_active(controller) is False

    controller.chat.input_focused = True
    controller.dock.set_right_tab("Inspector", force=True)
    assert is_text_input_active(controller) is False


def test_ai_chat_focus_suppresses_global_command_palette_hotkey(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    calls: list[str] = []
    controller.run_editor_action = lambda action_id: calls.append(str(action_id)) or True  # type: ignore[method-assign]
    input_x, input_y = _input_center(overlay)
    assert controller.handle_mouse_click(input_x, input_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    handled = controller.handle_input(optional_arcade.arcade.key.P, optional_arcade.arcade.key.MOD_CTRL)

    assert handled is True
    assert calls == []
    assert controller.chat.input_focused is True

    controller.chat.input_focused = False
    handled = controller.handle_input(optional_arcade.arcade.key.P, optional_arcade.arcade.key.MOD_CTRL)

    assert handled is True
    assert calls == ["editor.command_palette.toggle"]


def test_ai_chat_click_outside_input_releases_focus(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    input_x, input_y = _input_center(overlay)
    assert controller.handle_mouse_click(input_x, input_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    rect = getattr(overlay, "_transcript_rect")
    assert rect is not None
    left, bottom, width, height = rect
    assert controller.handle_mouse_click(left + width - 2, bottom + height - 2, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.chat.input_focused is False


def test_ai_chat_overlay_click_not_reached_from_other_right_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    x, y = _button_center(overlay, "send")
    calls: list[tuple[float, float, int, int]] = []

    def fail_if_called(px: float, py: float, button: int, modifiers: int = 0) -> bool:
        calls.append((px, py, button, modifiers))
        return True

    overlay.on_mouse_press = fail_if_called  # type: ignore[method-assign]
    controller.dock.set_right_tab("Inspector", force=True)

    handled = controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)

    assert handled is True
    assert calls == []


def test_ai_chat_send_disabled_while_controller_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    controller.chat.current_input = "second run"
    controller.chat.is_running = True
    submit_calls: list[str] = []
    controller.chat.submit_current_input = lambda: submit_calls.append(controller.chat.current_input) or {"ok": True}  # type: ignore[method-assign]

    x, y = _button_center(overlay, "send")
    assert controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert submit_calls == []


def test_ai_chat_dock_submit_stages_proposal_and_updates_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    client = _FakeClient(
        [
            {
                "content": [
                    _tool_use(
                        "tool-1",
                        "stage_proposal",
                        {
                            "ops": [
                                {
                                    "type": "add_entity_from_prefab",
                                    "prefab_id": "crate",
                                    "x": 64,
                                    "y": 80,
                                    "name": "dock_chat_crate",
                                }
                            ]
                        },
                    )
                ]
            },
            {"content": [_text("Staged a crate proposal.")]},
        ]
    )
    controller.chat.set_client_factory(_FakeFactory(client))
    input_x, input_y = _input_center(overlay)

    assert controller.handle_mouse_click(input_x, input_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    for char in "crate":
        controller.handle_text_input(char)
    send_x, send_y = _button_center(overlay, "send")
    assert controller.handle_mouse_click(send_x, send_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    _run_chat_to_completion(controller)

    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    pending = controller.proposal_inbox.list_pending()
    assert len(pending) == 1
    assert "dock_chat_crate" in pending[0]["preview_summary"]
    visible_text = [str(message.get("text", "")) for message in controller.chat.visible_messages]
    assert "crate" in visible_text
    assert "Staged a crate proposal." in visible_text
    assert "dock_chat_crate" not in _entity_names(controller.window.scene_controller.build_scene_snapshot(compact=False))


def test_ai_chat_wrap_helper_and_layout_include_all_wrapped_lines() -> None:
    long_text = "alpha beta gamma delta epsilon zeta"

    wrapped = wrap_transcript_text(long_text, 12)
    layout = build_transcript_lines([{"role": "assistant", "text": long_text}], 12)

    assert len(wrapped) > 1
    assert all(len(line) <= 12 for line in wrapped)
    assert [line["text"] for line in layout] == wrap_transcript_text(f"assistant: {long_text}", 12)
    assert len(layout) > 1


def test_ai_chat_transcript_scroll_changes_visible_window(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _make_controller()
    overlay = _install_and_draw_chat_overlay(controller, monkeypatch)
    controller.chat.visible_messages = [{"role": "assistant", "text": f"message {idx} " * 5} for idx in range(20)]
    overlay.draw()
    rect = getattr(overlay, "_transcript_rect")
    assert rect is not None
    left, bottom, width, height = rect
    assert len(getattr(overlay, "_transcript_lines")) > int(height // 18)

    assert overlay.on_mouse_scroll(left + width / 2, bottom + height / 2, 0, 4) is True

    assert getattr(overlay, "_scroll_offset_lines") > 0


def _install_and_draw_chat_overlay(controller: Any, monkeypatch: pytest.MonkeyPatch) -> AIChatOverlay:
    import engine.ui_overlays.ai_chat_overlay as overlay_module

    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_filled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_outline", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *_args, **_kwargs: None)
    controller.window.editor_controller = controller
    overlay = AIChatOverlay(controller.window)
    controller.window.ai_chat_overlay = overlay
    controller.dock.set_right_tab("AI Chat", force=True)
    overlay.draw()
    return overlay


def _button_center(overlay: AIChatOverlay, action: str) -> tuple[float, float]:
    left, bottom, width, height = getattr(overlay, "_button_rects")[action]
    return left + (width / 2), bottom + (height / 2)


def _input_center(overlay: AIChatOverlay) -> tuple[float, float]:
    rect = getattr(overlay, "_input_rect")
    assert rect is not None
    left, bottom, width, height = rect
    return left + (width / 2), bottom + (height / 2)
