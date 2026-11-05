from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from engine.editor.live_session_bridge import (
    LOOPBACK_HOST,
    REQUEST_ID,
    SESSION_SCHEMA_VERSION,
    read_live_session_file,
    session_file_path,
)
from engine.repo_root import find_repo_root


def _failure(reason: str, message: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "mode": "live_editor", "reason": reason}
    if message:
        payload["message"] = message
    payload.update(extra)
    return payload


def _workspace_root(root: str | Path) -> str:
    return str(Path(root).resolve())


def _resolve_discovery_root(root: str | Path) -> Path:
    raw = Path(root).resolve()
    discovered = find_repo_root(raw)
    return (discovered or raw).resolve()


def _session_root_from_payload(payload: dict[str, Any], fallback_root: Path) -> Path:
    raw_root = str(payload.get("workspace_root") or "").strip()
    if raw_root:
        return Path(raw_root).resolve()
    return fallback_root.resolve()


def _probe_candidate_roots(raw_root: Path, server_root: Path) -> list[Path]:
    candidates: dict[str, Path] = {}

    def add(path: Path) -> None:
        resolved = path.resolve()
        candidates[str(resolved).lower()] = resolved

    add(raw_root)
    add(server_root)
    add(raw_root.parent)
    try:
        siblings = sorted(raw_root.parent.iterdir() if raw_root.parent.is_dir() else (), key=lambda p: p.name)[:50]
    except OSError:
        siblings = []
    for child in siblings:
        try:
            if child.is_dir():
                add(child)
        except OSError:
            continue
    return list(candidates.values())


def _session_root_mismatch_failure(found_root: Path, server_root: Path) -> dict[str, Any]:
    found_text = str(found_root.resolve())
    server_text = str(server_root.resolve())
    return _failure(
        "session_root_mismatch",
        (
            f"Found a live editor session rooted at {found_text} but this MCP server is rooted at {server_text}. "
            "Launch the editor and the MCP server from the SAME project root (cd into it before launching)."
        ),
        found_root=found_text,
        server_root=server_text,
    )


def _probe_for_other_session(raw_root: Path, server_root: Path) -> dict[str, Any] | None:
    for candidate in _probe_candidate_roots(raw_root, server_root):
        payload = read_live_session_file(candidate)
        if not isinstance(payload, dict):
            continue
        found_root = _session_root_from_payload(payload, candidate)
        if _workspace_root(found_root) != _workspace_root(server_root):
            return _session_root_mismatch_failure(found_root, server_root)
    return None


def _request_json(
    info: dict[str, Any],
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 2.0,
    request_id: str = "",
) -> dict[str, Any]:
    host = str(info.get("host") or "")
    port = int(info.get("port") or 0)
    token = str(info.get("token") or "")
    url = f"http://{host}:{port}{path}"
    body = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Mesh-Wait": f"{timeout * 0.75:.3f}",  # (the editor answers, even "cancelled", before this stops listening)
    }
    if request_id:
        headers["X-Mesh-Request-Id"] = request_id
    req = request.Request(url, data=body, method=method, headers=headers)
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - validated loopback host only.
        loaded = json.loads(response.read().decode("utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def new_request_id(method: str, given: str = "") -> str:
    """The id of a POST (it may change something: #462 S3): ``given`` (the caller's, for retrying safely) or a new one;
    "" for a GET (it only reads)."""
    return (given or uuid.uuid4().hex) if method == "POST" else ""


def bad_request_id(given: str) -> dict[str, Any] | None:
    """The refusal for a caller's request id the editor wouldn't take, before anything is sent; None if it's fine."""
    if not given or REQUEST_ID.fullmatch(given):
        return None
    return _failure("invalid_request_id", "request_id must be 1-64 letters, digits, '-' or '_'; nothing was sent.")


def step_request_id(request_id: str, step: str) -> str:
    """The id of one step of a call made of several requests: the same each time the call is retried with its id."""
    return hashlib.sha256(f"{request_id}:{step}".encode()).hexdigest()[:32] if request_id else ""


def unknown_outcome(exc: BaseException, request_id: str) -> dict[str, Any] | None:
    """The answer when a POST got no reply (``exc``): the editor may have run it, so it can't be called failed. None
    when it surely didn't run: a GET, an error status from the editor, or a connection refused before sending."""
    refused = isinstance(getattr(exc, "reason", None), ConnectionRefusedError) or isinstance(exc, ConnectionRefusedError)
    if not request_id or refused or isinstance(exc, error.HTTPError):
        return None
    return _failure("outcome_unknown", (
        f"The editor didn't answer ({exc}), so it isn't known whether it did this. Ask request_status with this "
        "request_id what became of it before trying again."), request_id=request_id)


def _verify_session(
    root: str | Path, *, timeout: float = 2.0
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any] | None, str]:
    """``(info, health, failure, why)``: the session for ``root`` checked against its discovery record and its own
    ``/health`` answer; ``why`` says, for a person, what didn't check out."""
    raw_root = Path(root).resolve()
    server_root = _resolve_discovery_root(raw_root)
    record_root = raw_root
    info = read_live_session_file(raw_root)
    if not isinstance(info, dict) and raw_root != server_root:
        record_root, info = server_root, read_live_session_file(server_root)
    if not isinstance(info, dict):
        failure: dict[str, Any] = _failure("no_live_session")
        if raw_root == server_root:
            failure = _probe_for_other_session(raw_root, server_root) or failure
        return None, {}, failure, "there is no readable session record"
    declared_workspace = _workspace_root(str(info.get("workspace_root") or raw_root))
    if info.get("schema_version") != SESSION_SCHEMA_VERSION:
        return None, {}, _failure("invalid_live_session", "Unsupported live session schema"), "its record has an unknown format"
    if _workspace_root(str(info.get("workspace_root") or "")) != declared_workspace:
        return None, {}, _failure("workspace_mismatch"), "its record names no project folder"
    if os.path.normcase(declared_workspace) != os.path.normcase(_workspace_root(record_root)):
        # (F1: a record copied with the project, or left by another folder's editor, isn't this project's session)
        return None, {}, _failure("workspace_mismatch"), f"its record is for another project folder ({declared_workspace})"
    if str(info.get("host") or "") != LOOPBACK_HOST:
        return None, {}, _failure("invalid_live_session", "Live session host must be 127.0.0.1"), "its record isn't local"
    if not info.get("session_id") or not info.get("token") or not info.get("port"):
        return None, {}, _failure("invalid_live_session", "Live session discovery is incomplete"), "its record is incomplete"
    try:
        health = _request_json(info, "GET", "/health", timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return None, {}, _failure("no_live_session"), f"it didn't answer ({exc})"
    if health.get("ok") is not True:
        return None, {}, _failure("no_live_session"), "its answer didn't confirm the session"
    if health.get("session_id") != info.get("session_id"):
        return None, {}, _failure("session_mismatch"), "a different session answered"
    if _workspace_root(str(health.get("workspace_root") or "")) != declared_workspace:
        return None, {}, _failure("workspace_mismatch"), "it has another project folder open"
    return info, health, None, ""


def _load_verified_session(root: str | Path, *, timeout: float = 2.0) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    info, _health, failure, _why = _verify_session(root, timeout=timeout)
    return info, failure


def session_state(root: str | Path = ".", *, timeout: float = 2.0) -> dict[str, Any]:
    """Whether an editor has the project at ``root`` open, for writing its files from outside (F1, #422).

    ``state`` is ``"live"`` once an editor's session for it is verified (``info``, and ``host``: ``mesh_studio`` or
    another editor); ``"none"`` only when there is no session record for it at all (an editor that closes removes
    its record); otherwise ``"uncertain"``, with ``problem`` (the reason, ``why``, the record's path). A record that
    can't be read or verified (malformed, no answer, a timeout, another session or project folder) isn't proof the
    editor is closed: one that crashed leaves its record until it is opened again or the record is removed.
    """
    raw_root = Path(root).resolve()
    records = [session_file_path(p) for p in dict.fromkeys((raw_root, _resolve_discovery_root(raw_root)))]
    try:
        present = [path for path in records if path.exists()]
    except OSError as exc:
        return {"state": "uncertain", "problem": {"reason": "unreadable_live_session", "why": f"it can't be checked ({exc})",
                                                  "discovery": str(records[0])}}
    if not present:
        return {"state": "none"}
    info, health, failure, why = _verify_session(raw_root, timeout=timeout)
    if info is not None:
        return {"state": "live", "info": info, "host": str(health.get("host") or "legacy_editor")}
    reason = str((failure or {}).get("reason") or "")
    if read_live_session_file(present[0].parent.parent) is None:
        reason, why = "unreadable_live_session", "its session record can't be read"
    elif reason == "no_live_session":
        reason = "unverified_live_session"
    return {"state": "uncertain", "problem": {"reason": reason, "why": why, "discovery": str(present[0])}}


def resolved_discovery_root(root: str | Path = ".") -> str:
    return str(_resolve_discovery_root(root))


def _post(info: dict[str, Any], path: str, payload: dict[str, Any], *, timeout: float,
          request_id: str = "") -> dict[str, Any]:
    bad = bad_request_id(request_id)
    if bad is not None:
        return bad
    request_id = new_request_id("POST", request_id)
    try:
        result = _request_json(info, "POST", path, payload, timeout=timeout, request_id=request_id)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return unknown_outcome(exc, request_id) or _failure("forward_failed", str(exc))
    result.setdefault("mode", "live_editor")
    return result


def live_stage_proposal(ops: list[dict[str, Any]], *, root: str = ".", timeout: float = 2.0,
                        request_id: str = "") -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    return _post(info, "/live/stage_proposal", {"ops": list(ops)}, timeout=timeout, request_id=request_id)


def live_accept_proposal(proposal_id: str, *, root: str = ".", timeout: float = 2.0,
                         request_id: str = "") -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    return _post(info, "/live/accept_proposal", {"proposal_id": proposal_id}, timeout=timeout,
                 request_id=request_id)


def live_reject_proposal(proposal_id: str, *, root: str = ".", timeout: float = 2.0,
                         request_id: str = "") -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    return _post(info, "/live/reject_proposal", {"proposal_id": proposal_id}, timeout=timeout,
                 request_id=request_id)


def live_read_scene(*, compact: bool = False, root: str = ".", timeout: float = 2.0) -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    query = parse.urlencode({"compact": "true" if compact else "false"})
    try:
        result = _request_json(info, "GET", f"/live/read_scene?{query}", timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return _failure("forward_failed", str(exc))
    result.setdefault("mode", "live_editor")
    return result


def live_stage_and_accept_add_entity(op: dict[str, Any], *, root: str = ".", timeout: float = 2.0,
                                     request_id: str = "") -> dict[str, Any]:
    """Stage ``op`` and accept it: two requests. With ``request_id``, retrying the call repeats both (each by its own
    derived id), so the entity is never added twice (#462 S3)."""
    bad = bad_request_id(request_id)
    if bad is not None:
        return bad
    stage = live_stage_proposal([op], root=root, timeout=timeout, request_id=step_request_id(request_id, "stage"))
    if stage.get("ok") is not True:
        return stage
    proposal = stage.get("proposal")
    dry_run = proposal.get("dry_run") if isinstance(proposal, dict) else None
    proposal_id = str(stage.get("proposal_id") or "")
    if not isinstance(dry_run, dict) or dry_run.get("ok") is not True:
        # It can't apply: say so (staging itself "succeeded"), and don't leave it in the editor's inbox.
        if proposal_id:
            live_reject_proposal(proposal_id, root=root, timeout=timeout,
                                 request_id=step_request_id(request_id, "reject"))
        return {**stage, "ok": False, "reason": "dry_run_failed",
                "message": str((dry_run or {}).get("message") or "The change can't be applied to the live scene.")}
    if not proposal_id:
        return _failure("invalid_live_session", "Bridge did not return a proposal id")
    accepted = live_accept_proposal(proposal_id, root=root, timeout=timeout,
                                    request_id=step_request_id(request_id, "accept"))
    accepted.setdefault("proposal_id", proposal_id)  # if the editor wants a person to accept, it's waiting there
    return accepted
