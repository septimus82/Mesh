from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any

from engine.logging_tools import get_logger

logger = get_logger(__name__)

MODEL_ID = "claude-opus-4-8"
OPENAI_COMPATIBLE_MODEL_ID = "qwen3:14b"
OPENAI_COMPATIBLE_BASE_URL = "http://localhost:11434/v1"
SYSTEM_PROMPT = (
    "You are Mesh's in-editor co-creative scene assistant. Inspect the live scene before proposing "
    "changes. You may stage proposals for the human to review in the AI Proposals dock. Never accept "
    "or apply proposals yourself."
)


CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_live_scene",
        "description": "Read the current unsaved live editor scene and metadata.",
        "input_schema": {
            "type": "object",
            "properties": {"compact": {"type": "boolean"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "stage_proposal",
        "description": "Stage a proposal for human review in the AI Proposals dock. Does not apply changes.",
        "input_schema": {
            "type": "object",
            "properties": {"ops": {"type": "array", "items": {"type": "object"}}},
            "required": ["ops"],
            "additionalProperties": False,
        },
    },
]


@dataclass
class ChatRunResult:
    ok: bool
    message: str


class AnthropicProvider:
    def __init__(self, *, api_key_env: str = "ANTHROPIC_API_KEY") -> None:
        self.api_key_env = api_key_env
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError:
            self._anthropic_cls: Any = None
        else:
            self._anthropic_cls = Anthropic

    def unavailable_reason(self) -> str | None:
        if self._anthropic_cls is None:
            return "Claude chat requires the optional chat extra: pip install -e .[chat]"
        if not os.environ.get(self.api_key_env):
            return f"Claude API key missing. Set {self.api_key_env}."
        return None

    def create_client(self) -> Any:
        if self._anthropic_cls is None:
            raise RuntimeError("Anthropic SDK is not available")
        return self._anthropic_cls()

    def default_model(self) -> str:
        return os.environ.get("MESH_CHAT_MODEL") or MODEL_ID

    def stream_final_message(self, client: Any, *, model: str, max_tokens: int, messages: list[dict[str, Any]]) -> Any:
        stream_ctx = client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            tools=CHAT_TOOLS,
            messages=list(messages),
        )
        with stream_ctx as stream:
            return stream.get_final_message()

    def content_blocks(self, message: Any) -> list[dict[str, Any]]:
        return ClaudeMessageAdapter.content_blocks(message)

    def assistant_content(self, blocks: list[dict[str, Any]]) -> Any:
        return ClaudeMessageAdapter.to_anthropic_content(blocks)

    def tool_result_message(self, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "user", "content": tool_results}


AnthropicClientFactory = AnthropicProvider


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        openai_cls: Any | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("MESH_CHAT_BASE_URL") or OPENAI_COMPATIBLE_BASE_URL
        self.api_key = api_key if api_key is not None else os.environ.get("MESH_CHAT_API_KEY", "ollama")
        self._model = model or os.environ.get("MESH_CHAT_MODEL") or OPENAI_COMPATIBLE_MODEL_ID
        if openai_cls is not None:
            self._openai_cls = openai_cls
        else:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError:
                self._openai_cls = None
            else:
                self._openai_cls = OpenAI

    def unavailable_reason(self) -> str | None:
        if self._openai_cls is None:
            return "Local chat requires the optional chat-local extra: pip install -e .[chat-local]"
        return None

    def create_client(self) -> Any:
        if self._openai_cls is None:
            raise RuntimeError("OpenAI SDK is not available")
        return self._openai_cls(base_url=self.base_url, api_key=self.api_key)

    def default_model(self) -> str:
        return self._model

    def stream_final_message(self, client: Any, *, model: str, max_tokens: int, messages: list[dict[str, Any]]) -> Any:
        stream = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=_to_openai_messages(messages),
            tools=anthropic_tools_to_openai_tools(CHAT_TOOLS),
            stream=True,
        )
        return {"content": normalize_openai_stream(stream)}

    def content_blocks(self, message: Any) -> list[dict[str, Any]]:
        content = _get(message, "content", [])
        if not isinstance(content, list):
            return []
        return [dict(block) for block in content if isinstance(block, dict)]

    def assistant_content(self, blocks: list[dict[str, Any]]) -> Any:
        return [dict(block) for block in blocks]

    def tool_result_message(self, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": "user", "content": tool_results}


def create_chat_provider_from_env() -> Any:
    provider_name = (os.environ.get("MESH_CHAT_PROVIDER") or "anthropic").strip().lower()
    if provider_name in {"openai_compatible", "openai-compatible", "local", "ollama"}:
        return OpenAICompatibleProvider()
    return AnthropicProvider()


class ClaudeMessageAdapter:
    @staticmethod
    def content_blocks(message: Any) -> list[dict[str, Any]]:
        content = _get(message, "content", [])
        if not isinstance(content, list):
            return []
        return [ClaudeMessageAdapter.block(block) for block in content]

    @staticmethod
    def block(block: Any) -> dict[str, Any]:
        if isinstance(block, dict):
            return dict(block)
        payload: dict[str, Any] = {}
        for name in ("type", "id", "name", "input", "text"):
            if hasattr(block, name):
                payload[name] = getattr(block, name)
        return payload

    @staticmethod
    def to_anthropic_content(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(block) for block in blocks]


class ToolExecutor:
    def __init__(self, editor: Any, dispatcher: Any) -> None:
        self._editor = editor
        self._dispatcher = dispatcher

    def execute(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name == "read_live_scene":
            compact = bool(payload.get("compact", False)) if isinstance(payload, dict) else False
            return self._dispatcher.call_sync(lambda: dict(self._editor.read_live_scene(compact=compact)))
        if name == "stage_proposal":
            ops = payload.get("ops") if isinstance(payload, dict) else None
            if not isinstance(ops, list):
                return {"ok": False, "reason": "invalid_request", "message": "ops must be a list"}
            result = self._dispatcher.call_sync(lambda: _stage_into_inbox(self._editor, ops))
            dry_run = result.get("dry_run") if isinstance(result.get("dry_run"), dict) else {}
            if dry_run.get("ok") is False:
                result = dict(result)
                result["ok"] = False
            return result
        return {"ok": False, "reason": "unknown_tool", "message": f"Unsupported tool '{name}'"}


class ChatSessionController:
    def __init__(
        self,
        editor: Any,
        *,
        client_factory: Any | None = None,
        dispatcher: Any | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        max_tool_rounds: int = 8,
    ) -> None:
        self._editor = editor
        self.dispatcher = dispatcher if dispatcher is not None else getattr(editor, "main_thread_dispatcher", None)
        self.client_factory = client_factory if client_factory is not None else create_chat_provider_from_env()
        default_model = _call_optional(self.client_factory, "default_model") or MODEL_ID
        self.model = str(model or default_model)
        self.max_tokens = int(max_tokens)
        self.max_tool_rounds = int(max_tool_rounds)
        self.messages: list[dict[str, Any]] = []
        self.visible_messages: list[dict[str, Any]] = []
        self.current_input = ""
        self.input_focused = False
        self.last_error: str | None = None
        self.is_running = False
        self.cancel_requested = False
        self._worker: threading.Thread | None = None
        self._tool_executor = ToolExecutor(editor, self.dispatcher)

    def set_client_factory(self, factory: Any) -> None:
        self.client_factory = factory
        default_model = _call_optional(self.client_factory, "default_model")
        if default_model:
            self.model = str(default_model)

    def submit(self, text: str) -> dict[str, Any]:
        prompt = str(text or "").strip()
        if not prompt:
            return {"ok": False, "reason": "empty_prompt", "message": "Prompt is empty"}
        if self.is_running:
            return {"ok": False, "reason": "busy", "message": "Claude chat is already running"}
        unavailable = _call_optional(self.client_factory, "unavailable_reason")
        if unavailable:
            self.last_error = str(unavailable)
            self.visible_messages.append({"role": "system", "text": self.last_error, "status": "error"})
            return {"ok": False, "reason": "provider_unavailable", "message": self.last_error}

        self.messages.append({"role": "user", "content": prompt})
        self.visible_messages.append({"role": "user", "text": prompt})
        self.current_input = ""
        self.last_error = None
        self.cancel_requested = False
        self.is_running = True
        self._worker = threading.Thread(target=self._run_worker, name="mesh-claude-chat", daemon=True)
        self._worker.start()
        return {"ok": True, "message": "Claude chat started"}

    def submit_current_input(self) -> dict[str, Any]:
        return self.submit(self.current_input)

    def cancel(self) -> dict[str, Any]:
        self.cancel_requested = True
        if self.is_running:
            self.visible_messages.append({"role": "system", "text": "Claude chat cancellation requested.", "status": "cancelled"})
            return {"ok": True, "message": "Claude chat cancellation requested"}
        return {"ok": False, "reason": "not_running", "message": "Claude chat is not running"}

    def append_input_text(self, text: str) -> bool:
        if not self.input_focused:
            return False
        if text and text.isprintable():
            self.current_input += text
            return True
        return False

    def backspace_input(self) -> bool:
        if not self.input_focused:
            return False
        self.current_input = self.current_input[:-1]
        return True

    def drain(self, *, limit: int = 50) -> int:
        drain = getattr(self.dispatcher, "drain", None)
        if callable(drain):
            return int(drain(limit=limit))
        return 0

    def worker_alive(self) -> bool:
        return bool(self._worker is not None and self._worker.is_alive())

    def _run_worker(self) -> None:
        try:
            client = self.client_factory.create_client()
            self._run_tool_loop(client)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Claude chat worker failed: %s", exc)
            self.last_error = str(exc)
            self._post_visible({"role": "system", "text": self.last_error, "status": "error"})
        finally:
            self.is_running = False

    def _run_tool_loop(self, client: Any) -> None:
        for _round in range(self.max_tool_rounds):
            if self.cancel_requested:
                return
            final_message = self._stream_final_message(client)
            assistant_blocks = self._content_blocks(final_message)
            self.messages.append({"role": "assistant", "content": self._assistant_content(assistant_blocks)})
            text = _join_text(assistant_blocks)
            if text:
                self._post_visible({"role": "assistant", "text": text})

            tool_results: list[dict[str, Any]] = []
            for block in assistant_blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                tool_name = str(block.get("name") or "")
                tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                parse_error = block.get("parse_error")
                if parse_error:
                    result = {
                        "ok": False,
                        "reason": "malformed_tool_arguments",
                        "message": str(parse_error),
                    }
                else:
                    result = self._tool_executor.execute(tool_name, tool_input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": _tool_result_text(result),
                        "is_error": result.get("ok") is False,
                    }
                )
            if not tool_results:
                return
            self.messages.append(self._tool_result_message(tool_results))
        self.last_error = "Claude chat stopped after too many tool rounds"
        self._post_visible({"role": "system", "text": self.last_error, "status": "error"})

    def _stream_final_message(self, client: Any) -> Any:
        streamer = getattr(self.client_factory, "stream_final_message", None)
        if callable(streamer):
            return streamer(client, model=self.model, max_tokens=self.max_tokens, messages=list(self.messages))
        stream_ctx = client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            tools=CHAT_TOOLS,
            messages=list(self.messages),
        )
        with stream_ctx as stream:
            return stream.get_final_message()

    def _content_blocks(self, message: Any) -> list[dict[str, Any]]:
        adapter = getattr(self.client_factory, "content_blocks", None)
        if callable(adapter):
            return adapter(message)
        return ClaudeMessageAdapter.content_blocks(message)

    def _assistant_content(self, blocks: list[dict[str, Any]]) -> Any:
        adapter = getattr(self.client_factory, "assistant_content", None)
        if callable(adapter):
            return adapter(blocks)
        return ClaudeMessageAdapter.to_anthropic_content(blocks)

    def _tool_result_message(self, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
        adapter = getattr(self.client_factory, "tool_result_message", None)
        if callable(adapter):
            return dict(adapter(tool_results))
        return {"role": "user", "content": tool_results}

    def _post_visible(self, message: dict[str, Any]) -> None:
        post = getattr(self.dispatcher, "post", None)
        if callable(post):
            post(lambda: self.visible_messages.append(message))
        else:
            self.visible_messages.append(message)


def _stage_into_inbox(editor: Any, ops: list[dict[str, Any]]) -> dict[str, Any]:
    bridge = getattr(editor, "live_bridge", None)
    stage = getattr(bridge, "stage_pending_proposal", None) if bridge is not None else None
    if not callable(stage):
        from engine.editor.live_session_bridge import EditorLiveSessionBridge  # noqa: PLC0415

        try:
            root = editor._get_repo_root()
        except Exception:  # noqa: BLE001
            root = "."
        bridge = EditorLiveSessionBridge(editor, root)
        setattr(editor, "live_bridge", bridge)
        stage = bridge.stage_pending_proposal
    return dict(stage(ops))


def anthropic_tools_to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for tool in tools:
        parameters = tool.get("input_schema") if isinstance(tool.get("input_schema"), dict) else {"type": "object"}
        translated.append(
            {
                "type": "function",
                "function": {
                    "name": str(tool.get("name") or ""),
                    "description": str(tool.get("description") or ""),
                    "parameters": dict(parameters),
                },
            }
        )
    return translated


def normalize_openai_stream(stream: Any) -> list[dict[str, Any]]:
    text_parts: list[str] = []
    tool_calls: dict[int, dict[str, str]] = {}
    fallback_index = 0
    for chunk in stream:
        choices = _get(chunk, "choices", [])
        if not choices:
            continue
        delta = _get(choices[0], "delta", {})
        content = _get(delta, "content", None)
        if content:
            text_parts.append(str(content))
        for call in _get(delta, "tool_calls", []) or []:
            raw_index = _get(call, "index", None)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = fallback_index
                fallback_index += 1
            state = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
            call_id = _get(call, "id", None)
            if call_id:
                state["id"] += str(call_id)
            function = _get(call, "function", {})
            name = _get(function, "name", None)
            if name:
                state["name"] += str(name)
            arguments = _get(function, "arguments", None)
            if arguments:
                state["arguments"] += str(arguments)

    blocks: list[dict[str, Any]] = []
    text = "".join(text_parts)
    if text:
        blocks.append({"type": "text", "text": text})
    for index in sorted(tool_calls):
        state = tool_calls[index]
        parsed, parse_error = _parse_openai_tool_arguments(state.get("arguments", ""))
        block: dict[str, Any] = {
            "type": "tool_use",
            "id": state.get("id") or f"tool-{index}",
            "name": state.get("name") or "",
            "input": parsed,
        }
        if parse_error:
            block["parse_error"] = parse_error
        blocks.append(block)
    if text and not any(block.get("type") == "tool_use" for block in blocks):
        fallback_blocks = _extract_text_tool_calls(text)
        if fallback_blocks:
            return fallback_blocks
    return blocks


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content")
        if role == "user" and isinstance(content, str):
            converted.append({"role": "user", "content": content})
            continue
        if role == "assistant" and isinstance(content, list):
            blocks = [block for block in content if isinstance(block, dict)]
            text = _join_text(blocks)
            tool_calls = []
            for block in blocks:
                if block.get("type") != "tool_use":
                    continue
                tool_calls.append(
                    {
                        "id": str(block.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or ""),
                            "arguments": json.dumps(block.get("input") if isinstance(block.get("input"), dict) else {}),
                        },
                    }
                )
            payload: dict[str, Any] = {"role": "assistant", "content": text or None}
            if tool_calls:
                payload["tool_calls"] = tool_calls
            converted.append(payload)
            continue
        if role == "user" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id") or ""),
                        "content": str(block.get("content") or ""),
                    }
                )
            continue
        if isinstance(content, str):
            converted.append({"role": role, "content": content})
    return converted


def _parse_openai_tool_arguments(raw_arguments: str) -> tuple[dict[str, Any], str | None]:
    raw = str(raw_arguments or "").strip()
    if not raw:
        return {}, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"Malformed tool arguments JSON: {exc.msg}"
    if not isinstance(parsed, dict):
        return {}, "Malformed tool arguments JSON: expected an object"
    return parsed, None


def _extract_text_tool_calls(text: str) -> list[dict[str, Any]]:
    payload = _extract_json_payload_from_text(text)
    if payload is None:
        return []
    calls = payload if isinstance(payload, list) else [payload]
    blocks: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            return []
        block = _text_tool_call_to_block(call, index)
        if block is None:
            return []
        blocks.append(block)
    return blocks


def _extract_json_payload_from_text(text: str) -> Any | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    fenced = _extract_fenced_json_body(raw)
    candidates = [fenced] if fenced is not None else []
    candidates.append(raw)
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return json.loads(candidate.strip())
        except (TypeError, json.JSONDecodeError):
            continue
    return None


def _extract_fenced_json_body(text: str) -> str | None:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return None
    lines = stripped.splitlines()
    if len(lines) < 3:
        return None
    opener = lines[0].strip().lower()
    if opener not in {"```", "```json"}:
        return None
    closer_index = next((index for index in range(1, len(lines)) if lines[index].strip() == "```"), None)
    if closer_index is None:
        return None
    return "\n".join(lines[1:closer_index]).strip()


def _text_tool_call_to_block(call: dict[str, Any], index: int) -> dict[str, Any] | None:
    name = call.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    raw_arguments = call.get("arguments", call.get("parameters"))
    arguments = _coerce_text_tool_arguments(raw_arguments)
    if arguments is None:
        return None
    tool_id = call.get("id") or call.get("tool_use_id") or call.get("tool_call_id") or f"text-tool-{index}"
    return {
        "type": "tool_use",
        "id": str(tool_id),
        "name": name.strip(),
        "input": arguments,
    }


def _coerce_text_tool_arguments(raw_arguments: Any) -> dict[str, Any] | None:
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    if isinstance(raw_arguments, str):
        parsed, parse_error = _parse_openai_tool_arguments(raw_arguments)
        if parse_error:
            return None
        return parsed
    return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _call_optional(obj: Any, name: str) -> Any:
    fn = getattr(obj, name, None)
    if callable(fn):
        return fn()
    return None


def _join_text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(str(block.get("text") or "") for block in blocks if block.get("type") == "text" and block.get("text"))


def _tool_result_text(result: dict[str, Any]) -> str:
    safe = result
    try:
        return json.dumps(safe, sort_keys=True)
    except TypeError:
        return str(safe)
