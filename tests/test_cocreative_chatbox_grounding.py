from __future__ import annotations

import threading
from typing import Any

import engine.editor.chat_session_controller as chat_module
from engine.editor.chat_session_controller import CHAT_TOOLS, anthropic_tools_to_openai_tools, build_system_prompt
from tests.test_cocreative_chatbox_14a import _FakeClient, _FakeFactory, _run_chat_to_completion, _text, _tool_use
from tests.test_cocreative_chatbox_local_provider import _chunk, _FakeCompletions, _FakeOpenAIClient, _tool_delta
from tests.test_cocreative_live_ops import _make_controller


def test_grounding_prompt_says_stage_dont_guide() -> None:
    prompt = build_system_prompt()

    assert "scene-EDITING assistant" in prompt
    assert "MUST call stage_proposal" in prompt
    assert "Do NOT summarize the scene" in prompt
    assert "Do NOT" in prompt and "player-facing game guide" in prompt


def test_list_prefabs_returns_valid_palette_ids_without_mutation() -> None:
    controller = _make_controller()
    before_revision = controller.content_revision

    result = controller.chat._tool_executor.execute("list_prefabs", {})  # noqa: SLF001

    assert result["ok"] is True
    assert {prefab["id"] for prefab in result["prefabs"]} >= {"crate", "guard"}
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    assert controller.content_revision == before_revision


def test_list_entities_returns_positions_and_selected_only_without_mutation() -> None:
    controller = _make_controller()
    assert controller.apply_live_op({"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 10, "y": 20, "name": "ground_crate"})["ok"]
    assert controller.apply_live_op({"type": "add_entity_from_prefab", "prefab_id": "guard", "x": 30, "y": 40, "name": "ground_guard"})["ok"]
    controller._selected_entity_ids = ["ground_guard"]
    before_revision = controller.content_revision
    before_undo_count = len(controller.undo.undo_stack)

    all_entities = controller.chat._tool_executor.execute("list_entities", {})  # noqa: SLF001
    selected_entities = controller.chat._tool_executor.execute("list_entities", {"selected_only": True})  # noqa: SLF001

    assert {entity["id"] for entity in all_entities["entities"]} == {"ground_crate", "ground_guard"}
    guard = selected_entities["entities"][0]
    assert selected_entities["selected_only"] is True
    assert [entity["id"] for entity in selected_entities["entities"]] == ["ground_guard"]
    assert guard["x"] == 30.0
    assert guard["y"] == 40.0
    assert controller.content_revision == before_revision
    assert len(controller.undo.undo_stack) == before_undo_count


def test_new_grounding_tools_are_exposed_to_anthropic_and_openai_schemas() -> None:
    tool_names = {tool["name"] for tool in CHAT_TOOLS}
    openai_names = {tool["function"]["name"] for tool in anthropic_tools_to_openai_tools(CHAT_TOOLS)}
    stage_tool = next(tool for tool in CHAT_TOOLS if tool["name"] == "stage_proposal")

    assert {"read_live_scene", "list_prefabs", "list_entities", "stage_proposal"}.issubset(tool_names)
    assert {"read_live_scene", "list_prefabs", "list_entities", "stage_proposal"}.issubset(openai_names)
    assert "add_entity_from_prefab" in stage_tool["description"]
    assert "set_behaviour_params" in stage_tool["description"]
    assert "delete_entity" in stage_tool["description"]


def test_grounded_fake_anthropic_loop_lists_then_stages_real_prefab_on_main_thread(monkeypatch: Any) -> None:
    controller = _make_controller()
    main_thread_id = threading.get_ident()
    calls: list[tuple[str, int]] = []
    original_list_prefabs = chat_module._list_prefabs  # noqa: SLF001
    original_list_entities = chat_module._list_entities  # noqa: SLF001

    def list_prefabs_guard(editor: Any) -> dict[str, Any]:
        calls.append(("list_prefabs", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_list_prefabs(editor)

    def list_entities_guard(editor: Any, *, selected_only: bool = False) -> dict[str, Any]:
        calls.append(("list_entities", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_list_entities(editor, selected_only=selected_only)

    monkeypatch.setattr(chat_module, "_list_prefabs", list_prefabs_guard)
    monkeypatch.setattr(chat_module, "_list_entities", list_entities_guard)
    client = _FakeClient(
        [
            {"content": [_tool_use("tool-1", "list_prefabs", {})]},
            {"content": [_tool_use("tool-2", "list_entities", {"selected_only": False})]},
            {
                "content": [
                    _tool_use(
                        "tool-3",
                        "stage_proposal",
                        {
                            "ops": [
                                {
                                    "type": "add_entity_from_prefab",
                                    "prefab_id": "crate",
                                    "x": 700,
                                    "y": 360,
                                    "name": "grounded_crate",
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

    result = controller.submit_chat_prompt("add a crate")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert calls == [("list_prefabs", main_thread_id), ("list_entities", main_thread_id)]
    assert len(controller.proposal_inbox.list_pending()) == 1
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    assert any(tool["name"] == "list_prefabs" for tool in client.messages.calls[0]["tools"])


def test_text_fallback_grounding_tool_executes_read_only(monkeypatch: Any) -> None:
    controller = _make_controller()
    main_thread_id = threading.get_ident()
    calls: list[tuple[str, int]] = []
    original_list_prefabs = chat_module._list_prefabs  # noqa: SLF001

    def list_prefabs_guard(editor: Any) -> dict[str, Any]:
        calls.append(("list_prefabs", threading.get_ident()))
        assert threading.get_ident() == main_thread_id
        return original_list_prefabs(editor)

    monkeypatch.setattr(chat_module, "_list_prefabs", list_prefabs_guard)
    _FakeOpenAIClient.completions = _FakeCompletions(
        [
            [_chunk(content='{"name":"list_prefabs","arguments":{}}')],
            [_chunk(content="I found the prefabs.")],
        ]
    )
    controller.chat.set_client_factory(chat_module.OpenAICompatibleProvider(openai_cls=_FakeOpenAIClient, model="qwen3:14b"))
    before_revision = controller.content_revision

    result = controller.submit_chat_prompt("what can you add?")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    assert calls == [("list_prefabs", main_thread_id)]
    assert controller.proposal_inbox.list_pending() == []
    assert len(controller.window.scene_controller.all_sprites) == 0
    assert controller.undo.undo_stack == []
    assert controller.content_revision == before_revision
    assert _FakeOpenAIClient.completions.calls[0]["tools"]


def test_openai_structured_grounding_tools_are_available_in_provider_call() -> None:
    controller = _make_controller()
    _FakeOpenAIClient.completions = _FakeCompletions(
        [
            [_chunk(tool_calls=[_tool_delta(0, tool_id="call-1", name="list_prefabs", arguments="{}")])],
            [_chunk(content="Done.")],
        ]
    )
    controller.chat.set_client_factory(chat_module.OpenAICompatibleProvider(openai_cls=_FakeOpenAIClient, model="qwen3:14b"))

    result = controller.submit_chat_prompt("list prefabs")
    _run_chat_to_completion(controller)

    assert result["ok"] is True
    tool_names = {tool["function"]["name"] for tool in _FakeOpenAIClient.completions.calls[0]["tools"]}
    assert {"list_prefabs", "list_entities", "stage_proposal"}.issubset(tool_names)
