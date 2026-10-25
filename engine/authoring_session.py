"""The authoring API from outside Mesh Studio: what MCP tools and the ``mesh author`` command use.

Both ends of a change go through ``engine.authoring``. What differs is where the documents live:

- **Mesh Studio has the project open** (its live session answers): changes become a *proposal*
  in Studio, which the person reviews and accepts or rejects there. Files are never written
  behind Studio's back, so its unsaved work can't be overwritten.
- **Nothing has it open:** changes apply to the project files directly (one transaction:
  all or nothing), each room checked against the scene schema before it's written.

Every result is a plain dict with ``ok``, and on failure a ``reason`` and a ``message`` a person
or an AI can act on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error

from engine import authoring
from engine.mcp_server.live_session_client import _load_verified_session, _request_json
from engine.studio_project import Project

Doc = dict[str, Any]
STUDIO_HOST = "mesh_studio"


def _fail(reason: str, message: str, **extra: Any) -> Doc:
    return {"ok": False, "reason": reason, "message": message, **extra}


def open_project(root: str | Path) -> Project:
    root = Path(root).resolve()
    try:
        config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise authoring.ChangeError(0, "open", f"{root} isn't a Mesh project (no readable config.json).") from exc
    project = Project.open(root, config.get("world_file"))
    if project is None:
        raise authoring.ChangeError(0, "open", f"{root} has no world file, so it has no rooms to edit.")
    return project


def studio_session(root: str | Path, *, timeout: float = 2.0) -> tuple[Doc | None, str]:
    """``(session, host)`` if an editor has this project open; host is ``mesh_studio`` or another editor."""
    info, failure = _load_verified_session(root, timeout=timeout)
    if info is None or failure is not None:
        return None, ""
    try:
        health = _request_json(info, "GET", "/health", timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError):
        return None, ""
    return info, str(health.get("host") or "legacy_editor")


def _call(info: Doc, method: str, path: str, payload: Doc | None = None, *, timeout: float = 6.0) -> Doc:
    try:
        return _request_json(info, method, path, payload, timeout=timeout)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return _fail("studio_unreachable", f"Mesh Studio didn't answer: {exc}")


def operations() -> Doc:
    """What can be changed, generated from the engine's own operations."""
    return {"ok": True, "how": authoring.__doc__.split("\n\n", 2)[2].strip(), "operations": authoring.describe()}


def read_project(root: str | Path = ".") -> Doc:
    """Every room, as Studio has it (unsaved edits included, with its revision) or as saved on disk."""
    info, host = studio_session(root)
    if info is not None and host == STUDIO_HOST:
        result = _call(info, "GET", "/live/read_scene")
        result["source"] = "mesh_studio"
        return result
    try:
        project = open_project(root)
    except authoring.ChangeError as err:
        return _fail("not_a_project", err.reason)
    docs = project.all_documents()
    # Rooms with the shared player filled in, as Studio shows them; ``player`` is its one definition.
    rooms = {key: {"label": label, "path": path, "room": project.scene(key)} for key, label, path in project.rooms()}
    return {"ok": True, "source": "files", "revision": None, "current_room": project.current, "world": docs["world"],
            "rooms": rooms, "player": docs["player"], "models": authoring.models(project)}


def propose(root: str | Path, changes: list[Doc], *, title: str = "", base_revision: int | None = None,
            source: str = "") -> Doc:
    """Send changes to the Mesh Studio that has this project open, for the person to review."""
    info, host = studio_session(root)
    if info is None:
        return _fail("studio_not_open", "Mesh Studio doesn't have this project open. Open it there, or use "
                                        "apply_changes to change the files directly.")
    if host != STUDIO_HOST:
        return _fail("other_editor_open", "Another editor has this project open; close it or open the project in "
                                          "Mesh Studio.")
    payload: Doc = {"changes": changes, "title": title, "source": source or "an AI"}
    if base_revision is not None:
        payload["base_revision"] = int(base_revision)
    result = _call(info, "POST", "/live/stage_proposal", payload)
    if result.get("ok"):
        result["next"] = "The person reviews it in Mesh Studio (top bar: AI). proposal_status tells you what they decided."
    return result


def proposal_status(root: str | Path, proposal_id: str) -> Doc:
    info, host = studio_session(root)
    if info is None or host != STUDIO_HOST:
        return _fail("studio_not_open", "Mesh Studio doesn't have this project open.")
    return _call(info, "GET", f"/live/proposal?id={proposal_id}")


def withdraw(root: str | Path, proposal_id: str) -> Doc:
    info, host = studio_session(root)
    if info is None or host != STUDIO_HOST:
        return _fail("studio_not_open", "Mesh Studio doesn't have this project open.")
    return _call(info, "POST", "/live/reject_proposal", {"proposal_id": proposal_id})


def apply(root: str | Path, changes: list[Doc], *, dry_run: bool = False, title: str = "", source: str = "") -> Doc:
    """Change the project: as a proposal if Studio has it open, otherwise straight to its files."""
    info, host = studio_session(root)
    if info is not None:
        if dry_run:
            return _fail("studio_open", "Mesh Studio has this project open: propose the changes there instead.")
        result = propose(root, changes, title=title, source=source)
        if result.get("ok"):
            result["note"] = ("Mesh Studio has this project open, so the changes were proposed there instead of "
                              "written to the files (that would overwrite the person's unsaved work).")
        return result
    try:
        project = open_project(root)
        before, after = authoring.dry_run(project, changes)
        if dry_run:
            return {"ok": True, "source": "files", "dry_run": True, "summary": authoring.summarize(before, after)}
        result = authoring.apply(project, changes)
        written = project.save()
    except authoring.ChangeError as err:
        return _fail("invalid_change", str(err), index=err.index, op=err.op)
    return {"ok": True, "source": "files", "summary": authoring.summarize(before, after),
            "created": {str(k): v for k, v in result["created"].items()}, "written": written}
