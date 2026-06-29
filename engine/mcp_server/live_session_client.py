from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from engine.editor.live_session_bridge import (
    LOOPBACK_HOST,
    SESSION_SCHEMA_VERSION,
    read_live_session_file,
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
    raw_root = Path(root).resolve()
    server_root = _resolve_discovery_root(raw_root)
    info = read_live_session_file(raw_root)
    if not isinstance(info, dict) and raw_root != server_root:
        info = read_live_session_file(server_root)
    if not isinstance(info, dict):
        failure: dict[str, Any] = _failure("no_live_session")
        if raw_root == server_root:
            failure = _probe_for_other_session(raw_root, server_root) or failure
        return None, failure
    declared_workspace = _workspace_root(str(info.get("workspace_root") or raw_root))
    if info.get("schema_version") != SESSION_SCHEMA_VERSION:
        return None, _failure("invalid_live_session", "Unsupported live session schema")
    if _workspace_root(str(info.get("workspace_root") or "")) != declared_workspace:
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
    if _workspace_root(str(health.get("workspace_root") or "")) != declared_workspace:
        return None, _failure("workspace_mismatch")
    return info, None


def resolved_discovery_root(root: str | Path = ".") -> str:
    return str(_resolve_discovery_root(root))


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


def live_reject_proposal(proposal_id: str, *, root: str = ".", timeout: float = 2.0) -> dict[str, Any]:
    info, failure = _load_verified_session(root, timeout=timeout)
    if failure is not None or info is None:
        return failure or _failure("no_live_session")
    try:
        result = _request_json(info, "POST", "/live/reject_proposal", {"proposal_id": proposal_id}, timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return _failure("forward_failed", str(exc))
    result.setdefault("mode", "live_editor")
    return result


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
