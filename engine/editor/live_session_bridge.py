from __future__ import annotations

import json
import os
import queue
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from engine.logging_tools import get_logger

SESSION_SCHEMA_VERSION = 1
SESSION_RELATIVE_PATH = Path(".mesh") / "live_session.json"
LOOPBACK_HOST = "127.0.0.1"
logger = get_logger(__name__)


@dataclass(frozen=True)
class LiveSessionInfo:
    schema_version: int
    workspace_root: str
    host: str
    port: int
    pid: int
    session_id: str
    token: str
    current_scene_path: str
    started_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_root": self.workspace_root,
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "session_id": self.session_id,
            "token": self.token,
            "current_scene_path": self.current_scene_path,
            "started_at": self.started_at,
        }


@dataclass
class _QueuedWork:
    func: Callable[[], dict[str, Any]]
    event: threading.Event
    result: dict[str, Any] | None = None


def session_file_path(workspace_root: str | Path) -> Path:
    return Path(workspace_root).resolve() / SESSION_RELATIVE_PATH


def read_live_session_file(workspace_root: str | Path) -> dict[str, Any] | None:
    path = session_file_path(workspace_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def write_live_session_file(workspace_root: str | Path, info: LiveSessionInfo) -> Path:
    path = session_file_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    tmp_path.write_text(json.dumps(info.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def delete_live_session_file(workspace_root: str | Path, session_id: str) -> None:
    path = session_file_path(workspace_root)
    current = read_live_session_file(workspace_root)
    if not isinstance(current, dict) or current.get("session_id") != session_id:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return


class EditorLiveSessionBridge:
    """Loopback JSON bridge from the MCP subprocess to the live editor.

    HTTP handlers run on background threads. They must not touch editor, sprite,
    or GL state directly. Mutation endpoints enqueue callables here, then block
    until the editor main/update thread calls :meth:`drain_pending`.
    """

    def __init__(self, editor: Any, workspace_root: str | Path, *, request_timeout: float = 5.0) -> None:
        self.editor = editor
        self.workspace_root = Path(workspace_root).resolve()
        self.request_timeout = float(request_timeout)
        self.session_id = secrets.token_urlsafe(32)
        self.token = secrets.token_urlsafe(32)
        self.started_at = time.time()
        self._work: queue.Queue[_QueuedWork] = queue.Queue()
        self._proposals: dict[str, Any] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._info: LiveSessionInfo | None = None

    @property
    def info(self) -> LiveSessionInfo:
        if self._info is None:
            raise RuntimeError("Live bridge is not started")
        return self._info

    def start(self, *, write_discovery: bool = True) -> LiveSessionInfo:
        if self._server is not None:
            return self.info
        handler_cls = self._build_handler_class()
        server = ThreadingHTTPServer((LOOPBACK_HOST, 0), handler_cls)
        self._server = server
        port = int(server.server_address[1])
        info = LiveSessionInfo(
            schema_version=SESSION_SCHEMA_VERSION,
            workspace_root=str(self.workspace_root),
            host=LOOPBACK_HOST,
            port=port,
            pid=os.getpid(),
            session_id=self.session_id,
            token=self.token,
            current_scene_path=self._current_scene_path(),
            started_at=self.started_at,
        )
        self._info = info
        setattr(self.editor, "live_bridge", self)
        self._thread = threading.Thread(target=server.serve_forever, name="mesh-live-session-bridge", daemon=True)
        self._thread.start()
        if write_discovery:
            discovery_path = write_live_session_file(self.workspace_root, info)
            logger.info(
                "[Editor][LiveBridge] Live session ACTIVE - workspace_root=%s, discovery=%s, port=%s",
                self.workspace_root,
                discovery_path,
                port,
            )
        return info

    def stop(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            server.shutdown()
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        if self._info is not None:
            delete_live_session_file(self.workspace_root, self.session_id)
        if getattr(self.editor, "live_bridge", None) is self:
            setattr(self.editor, "live_bridge", None)

    def refresh_discovery(self) -> None:
        if self._info is None:
            return
        self._info = LiveSessionInfo(
            schema_version=self._info.schema_version,
            workspace_root=self._info.workspace_root,
            host=self._info.host,
            port=self._info.port,
            pid=self._info.pid,
            session_id=self._info.session_id,
            token=self._info.token,
            current_scene_path=self._current_scene_path(),
            started_at=self._info.started_at,
        )
        write_live_session_file(self.workspace_root, self._info)

    def drain_pending(self, *, limit: int = 50) -> int:
        drained = 0
        for _ in range(max(0, int(limit))):
            try:
                work = self._work.get_nowait()
            except queue.Empty:
                break
            try:
                work.result = work.func()
            except Exception as exc:  # noqa: BLE001
                work.result = {"ok": False, "mode": "live_editor", "reason": "exception", "message": str(exc)}
            finally:
                work.event.set()
            drained += 1
        return drained

    def pending_count(self) -> int:
        return self._work.qsize()

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        """Return GUI-safe summaries for proposals staged in this editor process."""
        rows: list[dict[str, Any]] = []
        for proposal_id, proposal in self._proposals.items():
            dry_run = getattr(proposal, "dry_run", {})
            if not isinstance(dry_run, dict):
                dry_run = {}
            affected_ids = dry_run.get("affected_ids")
            rows.append(
                {
                    "proposal_id": str(proposal_id),
                    "preview_summary": str(getattr(proposal, "preview_summary", "")),
                    "affected_ids": list(affected_ids) if isinstance(affected_ids, list) else [],
                    "dry_run": dict(dry_run),
                }
            )
        return rows

    def accept_pending_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Accept a staged proposal from the editor main thread."""
        return self._accept_proposal({"proposal_id": proposal_id})

    def reject_pending_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Reject a staged proposal from the editor main thread."""
        return self._reject_proposal({"proposal_id": proposal_id})

    def stage_pending_proposal(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        """Stage a proposal in the same store read by ProposalInbox."""
        return self._stage_proposal({"ops": ops})

    def _build_handler_class(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlsplit(self.path)
                path = parsed.path
                if not self._authorized():
                    self._send_json({"ok": False, "reason": "unauthorized"}, status=401)
                    return
                if path == "/health":
                    self._send_json(
                        {
                            "ok": True,
                            "session_id": bridge.session_id,
                            "workspace_root": str(bridge.workspace_root),
                            "current_scene_path": bridge._current_scene_path(),
                        }
                    )
                    return
                if path == "/live/read_scene":
                    compact = _truthy(parse_qs(parsed.query).get("compact", ["false"])[0])
                    self._send_json(bridge._enqueue(lambda: bridge._read_scene(compact=compact)))
                    return
                self._send_json({"ok": False, "reason": "not_found"}, status=404)

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._send_json({"ok": False, "reason": "unauthorized"}, status=401)
                    return
                path = self.path.split("?", 1)[0]
                payload = self._read_json()
                if path == "/live/stage_proposal":
                    self._send_json(bridge._enqueue(lambda: bridge._stage_proposal(payload)))
                    return
                if path == "/live/accept_proposal":
                    self._send_json(bridge._enqueue(lambda: bridge._accept_proposal(payload)))
                    return
                if path == "/live/reject_proposal":
                    self._send_json(bridge._enqueue(lambda: bridge._reject_proposal(payload)))
                    return
                self._send_json({"ok": False, "reason": "not_found"}, status=404)

            def _authorized(self) -> bool:
                return self.headers.get("Authorization", "") == f"Bearer {bridge.token}"

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0:
                    return {}
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (OSError, ValueError):
                    return {}
                return payload if isinstance(payload, dict) else {}

            def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
                body = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _enqueue(self, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        work = _QueuedWork(func=func, event=threading.Event())
        self._work.put(work)
        if not work.event.wait(timeout=self.request_timeout):
            return {"ok": False, "mode": "live_editor", "reason": "timeout", "message": "Timed out waiting for editor thread"}
        return work.result or {"ok": False, "mode": "live_editor", "reason": "empty_result"}

    def _stage_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        ops = payload.get("ops")
        if not isinstance(ops, list):
            return {"ok": False, "mode": "live_editor", "reason": "invalid_request", "message": "ops must be a list"}
        proposal = self.editor.stage_proposal(ops)
        proposal_id = uuid.uuid4().hex
        self._proposals[proposal_id] = proposal
        return {
            "ok": True,
            "mode": "live_editor",
            "proposal_id": proposal_id,
            "proposal": {
                "ops": list(getattr(proposal, "ops", [])),
                "base_revision": int(getattr(proposal, "base_revision", 0)),
                "preview_summary": str(getattr(proposal, "preview_summary", "")),
                "dry_run": getattr(proposal, "dry_run", {}),
            },
            "preview": str(getattr(proposal, "preview_summary", "")),
            "dry_run": getattr(proposal, "dry_run", {}),
        }

    def _accept_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(payload.get("proposal_id") or "")
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return {"ok": False, "mode": "live_editor", "reason": "proposal_not_found"}
        result = self.editor.accept_proposal(proposal)
        if result.get("ok") is True:
            self._proposals.pop(proposal_id, None)
        result = dict(result)
        result.setdefault("mode", "live_editor")
        result.setdefault("proposal_id", proposal_id)
        return result

    def _reject_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(payload.get("proposal_id") or "")
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return {"ok": False, "mode": "live_editor", "reason": "proposal_not_found"}
        result = dict(self.editor.reject_proposal(proposal))
        self._proposals.pop(proposal_id, None)
        result.setdefault("mode", "live_editor")
        result.setdefault("proposal_id", proposal_id)
        return result

    def _read_scene(self, *, compact: bool = False) -> dict[str, Any]:
        result = dict(self.editor.read_live_scene(compact=compact))
        result.setdefault("ok", True)
        result.setdefault("mode", "live_editor")
        return result

    def _current_scene_path(self) -> str:
        scene_controller = getattr(getattr(self.editor, "window", None), "scene_controller", None)
        return str(getattr(scene_controller, "current_scene_path", "") or "")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
