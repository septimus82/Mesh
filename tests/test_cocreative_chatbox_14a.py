from __future__ import annotations

import importlib
import threading
import time
from typing import Any

from engine.editor.chat_session_controller import AnthropicProvider
from tests.test_cocreative_live_ops import _make_controller


class _FakeStream:
    def __init__(self, message: dict[str, Any]) -> None:
        self._message = message

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def get_final_message(self) -> dict[str, Any]:
        return self._message


class _FakeMessages:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(dict(kwargs))
        if not self.responses:
            raise AssertionError("fake client exhausted")
        return _FakeStream(self.responses.pop(0))


class _FakeClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.messages = _FakeMessages(responses)


class _FakeFactory:
    def __init__(self, client: _FakeClient, *, unavailable: str | None = None) -> None:
        self.client = client
        self.unavailable = unavailable

    def unavailable_reason(self) -> str | None:
        return self.unavailable

    def create_client(self) -> _FakeClient:
        return self.client


def _tool_use(tool_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": payload}


def _text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def _run_chat_to_completion(controller: Any, *, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        controller.drain_main_thread_dispatcher()
        if not controller.chat.worker_alive() and not controller.chat.is_running:
            controller.drain_main_thread_dispatcher()
            return
        time.sleep(0.01)
    raise AssertionError("chat worker did not finish")


def test_stubbed_chat_loop_stages_one_proposal_through_main_thread_dispatcher() -> None:
    controller = _make_controller()
    main_thread_id = threading.get_ident()
    calls: list[tuple[str, int]] = []
    original_read = controller.read_live_scene
    original_stage = controller.stage_proposal

    def read_guard(*, compact: bool = False) -> dict[str, Any]:
        calls.append(("read_live_scene", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_read(compact=compact)

    def stage_guard(ops: list[dict[str, Any]]) -> Any:
        calls.append(("stage_proposal", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_stage(ops)

    controller.read_live_scene = read_guard  # type: ignore[method-assign]
    controller.stage_proposal = stage_guard  # type: ignore[method-assign]
    client = _FakeClient(
        [
            {"content": [_tool_use("tool-1", "read_live_scene", {"compact": False})]},
            {
                "content": [
                    _tool_use(
                        "tool-2",
                        "stage_proposal",
                        {
                            "ops": [
                                {
                                    "type": "add_entity_from_prefab",
                                    "prefab_id": "crate",
                                    "x": 64,
                                    "y": 80,
                                    "name": "chatbox_crate",
                                }
                            ]
                        },
                    )
                ]
            },
            {"content": [_text("Staged one crate proposal.")]},
        ]
    )
    controller.chat.set_client_factory(_FakeFactory(client))

    result = controller.submit_chat_prompt("add a crate")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert [name for name, _thread_id in calls] == ["read_live_scene", "stage_proposal"]
    assert all(thread_id == main_thread_id for _name, thread_id in calls)
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    pending = controller.proposal_inbox.list_pending()
    assert len(pending) == 1
    assert pending[0]["dry_run"]["ok"] is True
    assert "chatbox_crate" in pending[0]["preview_summary"]
    assert client.messages.calls[0]["model"] == "claude-opus-4-8"
    assert client.messages.calls[0]["thinking"] == {"type": "adaptive"}
    assert "temperature" not in client.messages.calls[0]
    assert "top_p" not in client.messages.calls[0]


def test_missing_key_surfaces_error_and_starts_no_worker() -> None:
    controller = _make_controller()
    client = _FakeClient([])
    controller.chat.set_client_factory(_FakeFactory(client, unavailable="Claude API key missing. Set ANTHROPIC_API_KEY."))

    result = controller.submit_chat_prompt("hello")

    assert result["ok"] is False
    assert result["reason"] == "provider_unavailable"
    assert controller.chat.worker_alive() is False
    assert controller.chat.is_running is False
    assert controller.chat.last_error == "Claude API key missing. Set ANTHROPIC_API_KEY."
    assert client.messages.calls == []


def test_editor_controller_import_succeeds_when_anthropic_import_fails(monkeypatch: Any) -> None:
    real_import_module = importlib.import_module

    def guarded_import_module(name: str, package: str | None = None) -> Any:
        if name == "anthropic":
            raise ImportError("anthropic absent")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", guarded_import_module)

    factory = AnthropicProvider()

    assert factory.unavailable_reason() == "Claude chat requires the optional chat extra: pip install -e .[chat]"


def test_invalid_stage_proposal_tool_result_mutates_nothing() -> None:
    controller = _make_controller()
    client = _FakeClient(
        [
            {"content": [_tool_use("tool-1", "stage_proposal", {"ops": [{"type": "not_supported"}]})]},
            {"content": [_text("That proposal failed validation.")]},
        ]
    )
    controller.chat.set_client_factory(_FakeFactory(client))

    result = controller.submit_chat_prompt("do something invalid")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    pending = controller.proposal_inbox.list_pending()
    assert len(pending) == 1
    assert pending[0]["dry_run"]["ok"] is False
    tool_result_message = client.messages.calls[1]["messages"][-1]
    assert tool_result_message["role"] == "user"
    assert tool_result_message["content"][0]["is_error"] is True
