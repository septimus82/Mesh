from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any

from engine.logging_tools import get_logger

logger = get_logger(__name__)

MODEL_ID = "claude-opus-4-8"
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


class AnthropicClientFactory:
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
        model: str = MODEL_ID,
        max_tokens: int = 2048,
        max_tool_rounds: int = 8,
    ) -> None:
        self._editor = editor
        self.dispatcher = dispatcher if dispatcher is not None else getattr(editor, "main_thread_dispatcher", None)
        self.client_factory = client_factory if client_factory is not None else AnthropicClientFactory()
        self.model = str(model)
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
            assistant_blocks = ClaudeMessageAdapter.content_blocks(final_message)
            self.messages.append({"role": "assistant", "content": ClaudeMessageAdapter.to_anthropic_content(assistant_blocks)})
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
            self.messages.append({"role": "user", "content": tool_results})
        self.last_error = "Claude chat stopped after too many tool rounds"
        self._post_visible({"role": "system", "text": self.last_error, "status": "error"})

    def _stream_final_message(self, client: Any) -> Any:
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
    import json

    safe = result
    try:
        return json.dumps(safe, sort_keys=True)
    except TypeError:
        return str(safe)
