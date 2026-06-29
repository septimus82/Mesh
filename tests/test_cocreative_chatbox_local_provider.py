from __future__ import annotations

import importlib
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor.chat_session_controller import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    anthropic_tools_to_openai_tools,
    create_chat_provider_from_env,
    normalize_openai_stream,
)
from tests.test_cocreative_chatbox_14a import _run_chat_to_completion
from tests.test_cocreative_live_ops import _make_controller

pytestmark = pytest.mark.fast


class _FakeCompletions:
    def __init__(self, responses: list[list[Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> list[Any]:
        self.calls.append(dict(kwargs))
        if not self.responses:
            raise AssertionError("fake OpenAI-compatible client exhausted")
        return self.responses.pop(0)


class _FakeOpenAIClient:
    completions: _FakeCompletions
    init_kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.__class__.init_kwargs = dict(kwargs)
        self.chat = SimpleNamespace(completions=self.__class__.completions)


def _chunk(*, content: str | None = None, tool_calls: list[Any] | None = None) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls or []))])


def _tool_delta(index: int, tool_id: str | None = None, name: str | None = None, arguments: str | None = None) -> Any:
    return SimpleNamespace(
        index=index,
        id=tool_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_openai_compatible_provider_stages_proposal_through_main_thread_dispatcher() -> None:
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
    _FakeOpenAIClient.completions = _FakeCompletions(
        [
            [
                _chunk(
                    tool_calls=[
                        _tool_delta(0, tool_id="call-1", name="read_live_scene", arguments='{"compact": false}'),
                    ]
                )
            ],
            [
                _chunk(
                    tool_calls=[
                        _tool_delta(
                            0,
                            tool_id="call-2",
                            name="stage_proposal",
                            arguments=(
                                '{"ops":[{"type":"add_entity_from_prefab","prefab_id":"crate",'
                                '"x":64,"y":80,"name":"local_chat_crate"}]}'
                            ),
                        ),
                    ]
                )
            ],
            [_chunk(content="Staged one local proposal.")],
        ]
    )
    provider = OpenAICompatibleProvider(openai_cls=_FakeOpenAIClient, base_url="http://localhost:11434/v1", api_key="ollama", model="qwen3:14b")
    controller.chat.set_client_factory(provider)

    result = controller.submit_chat_prompt("add a crate locally")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert [name for name, _thread_id in calls] == ["read_live_scene", "stage_proposal"]
    assert all(thread_id == main_thread_id for _name, thread_id in calls)
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    pending = controller.proposal_inbox.list_pending()
    assert len(pending) == 1
    assert pending[0]["dry_run"]["ok"] is True
    assert "local_chat_crate" in pending[0]["preview_summary"]
    first_call = _FakeOpenAIClient.completions.calls[0]
    assert first_call["model"] == "qwen3:14b"
    assert first_call["stream"] is True
    assert first_call["messages"][0]["role"] == "system"
    assert first_call["tools"][0]["type"] == "function"
    assert _FakeOpenAIClient.init_kwargs == {"base_url": "http://localhost:11434/v1", "api_key": "ollama"}


def test_tool_definition_translation_preserves_name_and_parameters() -> None:
    translated = anthropic_tools_to_openai_tools(
        [
            {
                "name": "stage_proposal",
                "description": "Stage changes",
                "input_schema": {"type": "object", "properties": {"ops": {"type": "array"}}, "required": ["ops"]},
            }
        ]
    )

    assert translated == [
        {
            "type": "function",
            "function": {
                "name": "stage_proposal",
                "description": "Stage changes",
                "parameters": {"type": "object", "properties": {"ops": {"type": "array"}}, "required": ["ops"]},
            },
        }
    ]


def test_openai_streamed_tool_call_normalizes_to_internal_tool_use() -> None:
    blocks = normalize_openai_stream(
        [
            [_chunk(tool_calls=[_tool_delta(0, tool_id="call-", name="stage_", arguments='{"ops":')])][0],
            [_chunk(tool_calls=[_tool_delta(0, tool_id="1", name="proposal", arguments=" []}")])][0],
        ]
    )

    assert blocks == [
        {
            "type": "tool_use",
            "id": "call-1",
            "name": "stage_proposal",
            "input": {"ops": []},
        }
    ]


def test_openai_streamed_malformed_tool_arguments_become_tool_error_block() -> None:
    blocks = normalize_openai_stream([_chunk(tool_calls=[_tool_delta(0, tool_id="call-1", name="stage_proposal", arguments="{bad")])])

    assert blocks[0]["type"] == "tool_use"
    assert blocks[0]["input"] == {}
    assert "Malformed tool arguments JSON" in blocks[0]["parse_error"]


def test_text_tool_call_fenced_json_stages_proposal_on_main_thread() -> None:
    controller = _make_controller()
    main_thread_id = threading.get_ident()
    calls: list[tuple[str, int]] = []
    original_stage = controller.stage_proposal

    def stage_guard(ops: list[dict[str, Any]]) -> Any:
        calls.append(("stage_proposal", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_stage(ops)

    controller.stage_proposal = stage_guard  # type: ignore[method-assign]
    content = (
        "```json\n"
        '{"name":"stage_proposal","arguments":{"ops":[{"type":"add_entity_from_prefab",'
        '"prefab_id":"crate","x":700,"y":360,"name":"text_tool_crate"}]}}\n'
        "```"
    )
    _FakeOpenAIClient.completions = _FakeCompletions([[_chunk(content=content)], [_chunk(content="Staged.")]])
    controller.chat.set_client_factory(OpenAICompatibleProvider(openai_cls=_FakeOpenAIClient, model="qwen3:14b"))

    result = controller.submit_chat_prompt("stage from text")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert calls == [("stage_proposal", main_thread_id)]
    assert len(controller.proposal_inbox.list_pending()) == 1
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []


def test_text_tool_call_bare_json_read_live_scene_executes() -> None:
    controller = _make_controller()
    main_thread_id = threading.get_ident()
    calls: list[tuple[str, int]] = []
    original_read = controller.read_live_scene

    def read_guard(*, compact: bool = False) -> dict[str, Any]:
        calls.append(("read_live_scene", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_read(compact=compact)

    controller.read_live_scene = read_guard  # type: ignore[method-assign]
    _FakeOpenAIClient.completions = _FakeCompletions(
        [
            [_chunk(content='{"name":"read_live_scene","arguments":{"compact":false}}')],
            [_chunk(content="I inspected the scene.")],
        ]
    )
    controller.chat.set_client_factory(OpenAICompatibleProvider(openai_cls=_FakeOpenAIClient, model="qwen3:14b"))

    result = controller.submit_chat_prompt("inspect")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert calls == [("read_live_scene", main_thread_id)]
    assert controller.proposal_inbox.list_pending() == []


def test_text_tool_call_arguments_json_string_is_parsed() -> None:
    blocks = normalize_openai_stream(
        [
            _chunk(
                content=(
                    '{"name":"stage_proposal","arguments":"{\\"ops\\":[{\\"type\\":\\"add_entity_from_prefab\\",'
                    '\\"prefab_id\\":\\"crate\\",\\"x\\":700,\\"y\\":360}]}"}'
                )
            )
        ]
    )

    assert blocks == [
        {
            "type": "tool_use",
            "id": "text-tool-0",
            "name": "stage_proposal",
            "input": {"ops": [{"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 700, "y": 360}]},
        }
    ]


def test_text_tool_call_plain_prose_and_malformed_json_stay_text() -> None:
    prose_blocks = normalize_openai_stream([_chunk(content="I can help stage a proposal.")])
    malformed_blocks = normalize_openai_stream([_chunk(content="{bad")])

    assert prose_blocks == [{"type": "text", "text": "I can help stage a proposal."}]
    assert malformed_blocks == [{"type": "text", "text": "{bad"}]


def test_structured_tool_call_wins_over_text_fallback() -> None:
    blocks = normalize_openai_stream(
        [
            _chunk(
                content='{"name":"read_live_scene","arguments":{"compact":false}}',
                tool_calls=[_tool_delta(0, tool_id="call-1", name="stage_proposal", arguments='{"ops":[]}')],
            )
        ]
    )

    assert blocks == [
        {"type": "text", "text": '{"name":"read_live_scene","arguments":{"compact":false}}'},
        {"type": "tool_use", "id": "call-1", "name": "stage_proposal", "input": {"ops": []}},
    ]


def test_provider_selection_defaults_to_anthropic_and_honors_openai_compatible_env(monkeypatch: Any) -> None:
    monkeypatch.delenv("MESH_CHAT_PROVIDER", raising=False)
    assert isinstance(create_chat_provider_from_env(), AnthropicProvider)

    monkeypatch.setenv("MESH_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MESH_CHAT_MODEL", "qwen3:14b")
    provider = create_chat_provider_from_env()

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.default_model() == "qwen3:14b"


def test_missing_openai_dependency_is_graceful_and_editor_import_still_succeeds(monkeypatch: Any) -> None:
    real_import_module = importlib.import_module

    def guarded_import_module(name: str, package: str | None = None) -> Any:
        if name == "openai":
            raise ImportError("openai absent")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", guarded_import_module)

    provider = OpenAICompatibleProvider()

    assert provider.unavailable_reason() == "Local chat requires the optional chat-local extra: pip install -e .[chat-local]"
