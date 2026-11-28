"""F1 (#422), in the fast tier: authoring from outside Studio writes files only when no editor has the project open.

The rule, decided without a running editor: only "no session record at all" allows the files to be written; a record
that can't be read or verified, or a verified session of any editor, refuses, and nothing is written or created. The
same guarantees with real Studio and legacy-editor sessions, exports and the CLI are in
tests/test_authoring_session_discovery.py (the integration tier, which every default run includes; F13-A).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from engine import authoring_session
from engine.editor.live_session_bridge import LiveSessionInfo, session_file_path, write_live_session_file
from engine.mcp_server import live_session_client, tools

pytestmark = pytest.mark.fast
CHANGE = [{"op": "place_prefab", "prefab": "person", "x": 32, "y": 32}]


def _record(root: Path, **overrides: Any) -> Path:
    """A live-session record for ``root`` (as an editor writes when it opens a project); nothing listens on it."""
    info = LiveSessionInfo(schema_version=1, workspace_root=str(root.resolve()), host="127.0.0.1", port=9, pid=1,
                           session_id="session", token="token", current_scene_path="", started_at=time.time())
    write_live_session_file(root, info)
    if overrides:
        path = session_file_path(root)
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), **overrides}), encoding="utf-8")
    return session_file_path(root)


def _health(monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any] | BaseException) -> None:
    """The editor's /health answer: a dict, or an exception it raises (a timeout, a refused connection)."""
    def request(info: dict[str, Any], method: str, path: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        if isinstance(answer, BaseException):
            raise answer
        return answer
    monkeypatch.setattr(live_session_client, "_request_json", request)


def _unverifiable(case: str, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A session record for ``root`` that can't be trusted, as ``case`` says."""
    if case == "half written":
        session_file_path(root).parent.mkdir()
        session_file_path(root).write_text("{", encoding="utf-8")
        return
    if case == "another folder":  # (a record copied with the project: refused before anyone is asked)
        _record(root, workspace_root=str(root.parent.resolve()))
        _health(monkeypatch, AssertionError("an editor was asked about another folder's record"))
        return
    _record(root)
    answers: dict[str, dict[str, Any] | BaseException] = {
        "timeout": TimeoutError("timed out"), "refused": ConnectionRefusedError(10061, "refused"),
        "not ok": {"ok": False},
        "another session": {"ok": True, "session_id": "another", "workspace_root": str(root.resolve())}}
    _health(monkeypatch, answers[case])


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    (root / "notes.txt").write_text("the person's", encoding="utf-8")
    return root


def test_no_session_record_is_the_only_closed(folder: Path) -> None:
    assert authoring_session.studio_state(folder) == {"state": "none"}


@pytest.mark.parametrize(("case", "problem"), [
    ("half written", "unreadable_live_session"), ("timeout", "unverified_live_session"),
    ("refused", "unverified_live_session"), ("not ok", "unverified_live_session"),
    ("another session", "session_mismatch"), ("another folder", "workspace_mismatch"),
])
def test_a_record_that_cant_be_verified_refuses_and_writes_nothing(folder: Path, monkeypatch: pytest.MonkeyPatch,
                                                                   case: str, problem: str) -> None:
    _unverifiable(case, folder, monkeypatch)
    state = authoring_session.studio_state(folder)
    assert state["state"] == "uncertain" and state["problem"]["reason"] == problem
    assert state["problem"]["discovery"] == str(session_file_path(folder))
    before = _files(folder)
    for answer in (authoring_session.apply(folder, CHANGE), authoring_session.propose(folder, CHANGE),
                   authoring_session.read_project(folder), tools.create_scene("cellar", root=str(folder)),
                   tools.apply_ops([{"type": "create_scene", "name": "cellar"}], root=str(folder))):
        assert answer["ok"] is False and answer["reason"] == "studio_session_uncertain", answer
        assert answer["problem"] == problem and "Nothing was changed" in answer["message"]
    assert _files(folder) == before


@pytest.mark.parametrize(("host", "reason"), [("mesh_studio", "studio_open"), ("legacy_editor", "other_editor_open")])
def test_a_verified_editor_blocks_direct_writes(folder: Path, monkeypatch: pytest.MonkeyPatch, host: str,
                                                reason: str) -> None:
    """Any verified session blocks the direct-file tools (F1 review: another editor's did not)."""
    monkeypatch.setattr(authoring_session, "studio_state", lambda _root, **_kw: {"state": "live", "host": host,
                                                                                 "info": {}})
    before = _files(folder)
    for answer in (tools.create_scene("cellar", root=str(folder)),
                   tools.apply_ops([{"type": "create_scene", "name": "cellar"}], root=str(folder))):
        assert answer["ok"] is False and answer["reason"] == reason, answer
    if host != "mesh_studio":
        for answer in (authoring_session.read_project(folder), authoring_session.apply(folder, CHANGE)):
            assert answer["reason"] == "other_editor_open" and answer["host"] == host, answer
    assert _files(folder) == before
