"""The loopback bridge from outside tools (MCP, ``mesh author``) to the editor open on a project.

HTTP handlers run on background threads; editor work runs only on the editor's main thread, which drains a queue
(``drain_pending``, from its update). A request waits for its work to finish, at most until a deadline.

**Requests and their states (#462 S3).** Each POST is one request with an id: the client's ``X-Mesh-Request-Id``
(1-64 letters, digits, ``-``, ``_``), else one the bridge makes. The answer carries it as ``request_id``.

========= ====================================================== ==============================================
state     how it gets there (one lock, ``_lock``, decides each)  what the client is told
========= ====================================================== ==============================================
queued    received; waiting for the editor's main thread         (still waiting)
started   the main thread took it from the queue (``drain``)     past the deadline: ``reason: "outcome_unknown"``
finished  its work returned (or raised: ``reason: "exception"``) its result
cancelled the deadline passed, or the bridge stopped, while it   ``reason: "timeout"`` / ``"editor_stopped"``:
          was still queued: it never runs                        it never ran and never will; nothing changed
========= ====================================================== ==============================================

Only ``queued`` can become ``started`` or ``cancelled``, and whichever happens first under the lock is final: a
cancelled request is skipped when the queue is drained, and a started one is never reported cancelled or failed (its
deadline can't tell whether it changed anything: ``outcome_unknown`` says so, and ``GET /live/request?id=`` gives its
result once it has finished). The main thread takes a request off the queue and starts it in one step under the
lock, so stopping the bridge can't miss one between the two. The deadline is the bridge's ``request_timeout``, or
the client's ``X-Mesh-Wait`` (in seconds) when shorter, so that the bridge answers before the client stops listening.

The same id sent again with the same method, path and body is the same request: it waits for (or gives) the first
one's outcome, and the work never runs twice. With anything different it is refused (``request_id_conflict``). A
cancelled request stays cancelled: try again with a new id. Finished and cancelled requests are remembered for
``REQUESTS_KEPT_SECONDS``, at most ``REQUESTS_KEPT`` of them; queued and started ones until they end. GET requests
only read: they get the same deadline and cancellation, but no id, status or memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from engine.logging_tools import get_logger

SESSION_SCHEMA_VERSION = 1
SESSION_RELATIVE_PATH = Path(".mesh") / "live_session.json"
LOOPBACK_HOST = "127.0.0.1"
REQUESTS_KEPT = 200  # ended POST requests remembered, for status and repeats (#462 S3)
REQUESTS_KEPT_SECONDS = 600.0
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
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
class _Job:
    """One request's work. ``state`` (the module's table) changes only under the bridge's ``_lock``."""

    func: Callable[[], dict[str, Any]] | None  # let go once it has ended (its payload with it)
    request_id: str = ""  # "" for a GET: not remembered
    fingerprint: str = ""  # method, path and body: what a repeat of this id must match
    seconds: float = 0.0  # its deadline, as its first sender gave it ...
    deadline: float = 0.0  # ... and when that is (time.monotonic): only then is it cancelled, whoever else waits
    state: str = "queued"  # queued | started | finished | cancelled
    result: dict[str, Any] | None = None
    ended_at: float = 0.0
    done: threading.Event = field(default_factory=threading.Event)


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
        self._work: queue.Queue[_Job] = queue.Queue()
        self._lock = threading.Lock()  # every _Job.state, _requests and _closed (#462 S3); never held while work runs
        self._requests: OrderedDict[str, _Job] = OrderedDict()  # POST requests by id, oldest first
        self._closed = False
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
        with self._lock:  # what hasn't started never will, and whoever waits for it hears so now (#462 S3); a
            self._closed = True  # started request is left to finish: it is never said to be cancelled
            while True:
                try:
                    job = self._work.get_nowait()
                except queue.Empty:
                    break
                if job.state == "queued":
                    self._end(job, "cancelled", _failure("editor_stopped", "The editor closed before starting this, "
                                                         "so it never ran and nothing changed."))
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
        while drained < max(0, int(limit)):  # (cancelled requests skipped don't count against the limit)
            with self._lock:  # the one way out of "queued" here: a request already cancelled is skipped, never run.
                try:  # (taken off the queue under the lock too, so stop() can't miss one between the two)
                    job = self._work.get_nowait()
                except queue.Empty:
                    break
                if job.state != "queued" or job.func is None:
                    continue
                job.state, func = "started", job.func
            result: Any = _failure("interrupted", "The editor was interrupted while doing this: it may have done "
                                   "part of it.")
            try:
                result = func()
            except Exception as exc:  # noqa: BLE001  # REASON: live bridge work items return structured errors to MCP callers
                result = {"ok": False, "mode": "live_editor", "reason": "exception", "message": str(exc)}
            finally:  # (also when interrupted: a started request always ends, so nothing waits on it for ever)
                if not isinstance(result, dict) or not result:
                    result = {"ok": False, "mode": "live_editor", "reason": "empty_result"}
                with self._lock:
                    self._end(job, "finished", result)
            drained += 1
        return drained

    def pending_count(self) -> int:
        """Requests waiting for the editor's main thread (not those cancelled meanwhile)."""
        with self._lock, self._work.mutex:  # (the order every path takes them in: _lock, then the queue's)
            return sum(1 for job in self._work.queue if job.state == "queued")

    def request_status(self, request_id: str) -> dict[str, Any]:
        """What became of a POST request (``GET /live/request?id=``), answered at once from any thread: its ``state``,
        and its ``result`` once it has ended (the answer its sender got, or would have)."""
        with self._lock:
            self._forget_ended()
            job = self._requests.get(request_id)
            if job is None:
                shown = request_id if REQUEST_ID.fullmatch(request_id) else ""  # (never echo what isn't an id)
                return {"ok": False, "mode": "live_editor", "reason": "request_not_found", "request_id": shown,
                        "message": f"No request {shown!r} in this editor session: it never arrived, it ended more "
                                   f"than {REQUESTS_KEPT_SECONDS:g} s or {REQUESTS_KEPT} requests ago, or it was sent "
                                   "to an editor that has closed since (one that closed never ran what it hadn't "
                                   "started)."}
            status: dict[str, Any] = {"ok": True, "mode": "live_editor", "request_id": request_id, "state": job.state}
            if job.result is not None:
                status["result"] = dict(job.result)
            return status

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

    def forget_proposal(self, proposal_id: str) -> None:
        """Let go of a proposal the editor no longer remembers (Mesh Studio's history is bounded: F10)."""
        self._proposals.pop(proposal_id, None)

    def stage_pending_proposal(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        """Stage a proposal in the same store read by ProposalInbox."""
        return self._stage_proposal({"ops": ops})

    def _build_handler_class(self) -> type[BaseHTTPRequestHandler]:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            _identity: dict[str, str] = {}  # a POST's request_id and fingerprint (set per request, never mutated)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self._identity = {}  # (a GET is no request to remember, even after a POST on the same handler)
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
                            "host": str(getattr(bridge.editor, "host_kind", "legacy_editor")),
                        }
                    )
                    return
                if path == "/live/request":  # (#462 S3: answered here, never queued behind the editor's main thread)
                    self._send_json(bridge.request_status(parse_qs(parsed.query).get("id", [""])[0]))
                    return
                if path == "/live/proposal" and hasattr(bridge.editor, "proposal_status"):
                    proposal_id = parse_qs(parsed.query).get("id", [""])[0]
                    self._run(lambda: bridge.editor.proposal_status(proposal_id))
                    return
                if path == "/live/read_scene":
                    compact = _truthy(parse_qs(parsed.query).get("compact", ["false"])[0])
                    self._run(lambda: bridge._read_scene(compact=compact))
                    return
                if path == "/live/debug/act" and hasattr(bridge.editor, "debug_act_status"):  # (Mesh Studio, D2)
                    action_id = parse_qs(parsed.query).get("id", [""])[0]
                    self._run(lambda: bridge.editor.debug_act_status(action_id))
                    return
                if path == "/live/debug/interaction" and hasattr(bridge.editor, "debug_interaction"):  # (D3A)
                    entity_id = parse_qs(parsed.query).get("entity", [""])[0][:200]
                    self._run(lambda: bridge.editor.debug_interaction(entity_id))
                    return
                if path == "/live/debug/snapshot" and hasattr(bridge.editor, "debug_snapshot"):  # (Mesh Studio, D1)
                    events = _count(parse_qs(parsed.query).get("events", [""])[0])
                    self._run(lambda: bridge.editor.debug_snapshot(events))
                    return
                self._send_json({"ok": False, "reason": "not_found"}, status=404)

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._send_json({"ok": False, "reason": "unauthorized"}, status=401)
                    return
                path = self.path.split("?", 1)[0]
                body = self._read_body()
                payload = _json_object(body)
                request_id = self.headers.get("X-Mesh-Request-Id") or uuid.uuid4().hex
                if not REQUEST_ID.fullmatch(request_id):
                    self._send_json({"ok": False, "mode": "live_editor", "reason": "invalid_request_id", "message": (
                        "X-Mesh-Request-Id must be 1-64 letters, digits, '-' or '_'; nothing was done.")}, status=400)
                    return
                self._identity = {"request_id": request_id, "fingerprint": hashlib.sha256(
                    b"POST " + self.path.encode("utf-8") + b"\n" + body).hexdigest()}
                if path == "/live/stage_proposal":
                    self._run(lambda: bridge._stage_proposal(payload))
                    return
                if path == "/live/accept_proposal":
                    self._run(lambda: bridge._accept_proposal(payload))
                    return
                if path == "/live/reject_proposal":
                    self._run(lambda: bridge._reject_proposal(payload))
                    return
                if path == "/live/debug/play" and hasattr(bridge.editor, "debug_start_playtest"):
                    self._run(bridge.editor.debug_start_playtest)
                    return
                if path == "/live/debug/stop" and hasattr(bridge.editor, "debug_stop_playtest"):
                    self._run(bridge.editor.debug_stop_playtest)
                    return
                if path == "/live/debug/act" and hasattr(bridge.editor, "debug_act"):
                    self._run(lambda: bridge.editor.debug_act(payload))
                    return
                if path == "/live/debug/act/cancel" and hasattr(bridge.editor, "debug_act_cancel"):
                    action_id = str(payload.get("action_id") or "")
                    self._run(lambda: bridge.editor.debug_act_cancel(action_id))
                    return
                self._send_json({"ok": False, "reason": "not_found"}, status=404)

            def _authorized(self) -> bool:
                return self.headers.get("Authorization", "") == f"Bearer {bridge.token}"

            def _read_body(self) -> bytes:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0:
                    return b""
                try:
                    return self.rfile.read(length)
                except OSError:
                    return b""

            def _run(self, func: Callable[[], dict[str, Any]]) -> None:
                """Queue ``func`` for the editor's main thread and answer how it went (a POST: as its request)."""
                self._send_json(bridge._enqueue(func, wait=_seconds(self.headers.get("X-Mesh-Wait")), **self._identity))

            def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
                body = json.dumps(payload, sort_keys=True).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except ConnectionError:  # (the client hung up: its request's outcome stays in request_status, S3)
                    return

        return Handler

    def _enqueue(self, func: Callable[[], dict[str, Any]], *, request_id: str = "", fingerprint: str = "",
                 wait: float | None = None) -> dict[str, Any]:
        """Run ``func`` on the editor's main thread and answer how it went, by the deadline (the module's table). A
        ``request_id`` already here (a repeat) is that request again: never queued twice."""
        with self._lock:
            job = self._requests.get(request_id) if request_id else None
            if job is not None and job.fingerprint != fingerprint:
                return {"ok": False, "mode": "live_editor", "reason": "request_id_conflict", "request_id": request_id,
                        "message": f"Request {request_id!r} was already sent with another method, path or body, so "
                                   "this one was refused and nothing was done. Use a new request id."}
            deadline = self.request_timeout if wait is None else min(self.request_timeout, wait)
            first = job is None
            if job is None:
                job = _Job(func, request_id, fingerprint, deadline, time.monotonic() + deadline)
                if self._closed:
                    self._end(job, "cancelled", _failure("editor_stopped", "The editor is closing, so this was "
                                                         "never started and nothing changed."))
                else:
                    self._work.put(job)
                if request_id:
                    self._forget_ended()
                    self._requests[request_id] = job
        if not job.done.wait(timeout=deadline):
            with self._lock:  # (still queued at its own deadline: cancelled, and the drain skips it; started
                # meanwhile: left to finish. A repeat waiting less long doesn't cut its first sender's wait short.)
                if job.state == "queued" and (first or time.monotonic() >= job.deadline):
                    self._end(job, "cancelled", _failure("timeout", (
                        f"The editor was busy and didn't start this within {job.seconds:g} s, so it was cancelled: "
                        "it never ran and won't, and nothing changed. Try again.")))
        with self._lock:
            if job.result is not None:
                answer = dict(job.result)
            elif job.state == "queued":  # (a repeat that waited less long than the first)
                answer = _failure("outcome_unknown", (
                    f"This request is still waiting for the editor, which may start it within {job.seconds:g} s of "
                    "when it was first sent. Ask what became of it (request_status) before trying again."))
            else:  # started, not finished
                answer = _failure("outcome_unknown", (
                    f"The editor started this but hadn't finished it within {deadline:g} s, so it isn't known yet "
                    "whether it changed anything. It may still finish: ask what became of it (GET "
                    "/live/request?id=..., MCP: request_status) before trying again." if request_id else
                    f"The editor started this read but hadn't finished it within {deadline:g} s. Ask again."))
            answer["request_state"] = job.state
            if request_id:
                answer["request_id"] = request_id
            return answer

    def _end(self, job: _Job, state: str, result: dict[str, Any]) -> None:
        """``job`` has ended (``finished`` or ``cancelled``): wake whoever waits. Call with ``_lock`` held."""
        job.state, job.result, job.ended_at = state, result, time.monotonic()
        job.func = None  # (its closure and payload: not kept while the outcome is remembered)
        job.done.set()

    def _forget_ended(self) -> None:
        """Let go of ended requests older than ``REQUESTS_KEPT_SECONDS`` or beyond the last ``REQUESTS_KEPT``; queued
        and started ones are kept until they end. Call with ``_lock`` held."""
        now = time.monotonic()
        ended = [key for key, job in self._requests.items() if job.done.is_set()]
        for index, key in enumerate(ended):
            if len(ended) - index > REQUESTS_KEPT or now - self._requests[key].ended_at > REQUESTS_KEPT_SECONDS:
                del self._requests[key]

    def _stage_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        ops = payload.get("changes", payload.get("ops"))
        if not isinstance(ops, list):
            return {"ok": False, "mode": "live_editor", "reason": "invalid_request", "message": "ops must be a list"}
        # A host that takes the whole request (Mesh Studio: title, base_revision) gets it, and may refuse.
        stage_payload = getattr(self.editor, "stage_proposal_payload", None)
        proposal = stage_payload(payload) if callable(stage_payload) else self.editor.stage_proposal(ops)
        if isinstance(proposal, dict):
            return proposal
        proposal_id = uuid.uuid4().hex
        if hasattr(proposal, "proposal_id"):
            proposal.proposal_id = proposal_id
        self._proposals[proposal_id] = proposal
        view = getattr(proposal, "view", None)
        if callable(view):  # Mesh Studio: its own description of the proposal
            return {"ok": True, "mode": "live_studio", "proposal_id": proposal_id, "proposal": view()}
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


def _failure(reason: str, message: str) -> dict[str, Any]:
    return {"ok": False, "mode": "live_editor", "reason": reason, "message": message}


def _seconds(value: str | None) -> float | None:
    """A client's ``X-Mesh-Wait``: a positive number of seconds, else None (the bridge's own deadline)."""
    try:
        seconds = float(value or "")
    except ValueError:
        return None
    return seconds if seconds > 0 else None  # (NaN isn't > 0)


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except ValueError:  # (UnicodeDecodeError is one)
        return {}
    return payload if isinstance(payload, dict) else {}


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _count(value: str, default: int = 20, most: int = 50) -> int:
    """A count from a query (how many events a snapshot lists): a whole number, 0 to ``most``; else ``default``."""
    try:
        return max(0, min(int(value), most))
    except ValueError:
        return default
