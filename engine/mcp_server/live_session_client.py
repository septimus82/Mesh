from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, request

from engine.editor.live_session_bridge import (
    LOOPBACK_HOST,
    SESSION_SCHEMA_VERSION,
    read_live_session_file,
)


def _failure(reason: str, message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "mode": "live_editor", "reason": reason}
    if message:
        payload["message"] = message
    return payload


def _workspace_root(root: str | Path) -> str:
    return str(Path(root).resolve())


def _request_json(
    info: dict[str, Any],
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 2.0,
) -> dict[str, Any]:
    host = str(info.get("host") or "")
    port = int(info.get("port") or 0)
    token = str(info.get("token") or "")
    url = f"http://{host}:{port}{path}"
    body = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
    req = request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - validated loopback host only.
        loaded = json.loads(response.read().decode("utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _load_verified_session(root: str | Path, *, timeout: float = 2.0) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    workspace_root = _workspace_root(root)
    info = read_live_session_file(workspace_root)
    if not isinstance(info, dict):
        return None, _failure("no_live_session")
    if info.get("schema_version") != SESSION_SCHEMA_VERSION:
        return None, _failure("invalid_live_session", "Unsupported live session schema")
    if _workspace_root(str(info.get("workspace_root") or "")) != workspace_root:
        return None, _failure("workspace_mismatch")
    if str(info.get("host") or "") != LOOPBACK_HOST:
        return None, _failure("invalid_live_session", "Live session host must be 127.0.0.1")
    if not info.get("session_id") or not info.get("token") or not info.get("port"):
        return None, _failure("invalid_live_session", "Live session discovery is incomplete")
    try:
        health = _request_json(info, "GET", "/health", timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError):
        return None, _failure("no_live_session")
    if health.get("ok") is not True:
        return None, _failure("no_live_session")
    if health.get("session_id") != info.get("session_id"):
        return None, _failure("session_mismatch")
    if _workspace_root(str(health.get("workspace_root") or "")) != workspace_root:
        return None, _failure("workspace_mismatch")
    return info, None


def live_stage_proposal(ops: list[dict[str, Any]], *, root: str = ".", timeout: float = 2.0) -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    try:
        result = _request_json(info, "POST", "/live/stage_proposal", {"ops": list(ops)}, timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return _failure("forward_failed", str(exc))
    result.setdefault("mode", "live_editor")
    return result


def live_accept_proposal(proposal_id: str, *, root: str = ".", timeout: float = 2.0) -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    try:
        result = _request_json(info, "POST", "/live/accept_proposal", {"proposal_id": proposal_id}, timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return _failure("forward_failed", str(exc))
    result.setdefault("mode", "live_editor")
    return result


def live_stage_and_accept_add_entity(op: dict[str, Any], *, root: str = ".", timeout: float = 2.0) -> dict[str, Any]:
    stage = live_stage_proposal([op], root=root, timeout=timeout)
    if stage.get("ok") is not True:
        return stage
    proposal = stage.get("proposal")
    dry_run = proposal.get("dry_run") if isinstance(proposal, dict) else None
    if not isinstance(dry_run, dict) or dry_run.get("ok") is not True:
        stage.setdefault("ok", False)
        return stage
    proposal_id = str(stage.get("proposal_id") or "")
    if not proposal_id:
        return _failure("invalid_live_session", "Bridge did not return a proposal id")
    return live_accept_proposal(proposal_id, root=root, timeout=timeout)
