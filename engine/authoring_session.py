"""The authoring API from outside Mesh Studio: what MCP tools and the ``mesh author`` command use.

Both ends of a change go through ``engine.authoring``. What differs is where the documents live:

- **Mesh Studio has the project open** (its live session answers): changes become a *proposal*
  in Studio, which the person reviews and accepts or rejects there. Files are never written
  behind Studio's back, so its unsaved work can't be overwritten.
- **Nothing has it open:** changes apply to the project files directly (one transaction:
  all or nothing), each room checked against the scene schema before it's written.
- **It can't be told** (F1, #422): an editor's session record that can't be read or verified (no
  answer, a timeout, a malformed record, another session or project folder) isn't proof that
  Studio is closed. Nothing is read from or written to the files then; the result says why and
  what to do. Only "no session record at all" counts as closed, and ``apply`` checks it again
  just before it writes.

Every result is a plain dict with ``ok``, and on failure a ``reason`` and a ``message`` a person
or an AI can act on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error

from engine import authoring
from engine.mcp_server.live_session_client import _request_json, session_state
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


def studio_state(root: str | Path, *, timeout: float = 2.0) -> Doc:
    """Whether an editor has this project open: ``state`` ``"live"`` (with ``info`` and ``host``: ``mesh_studio`` or
    another editor), ``"none"`` or ``"uncertain"`` (``problem``); see ``live_session_client.session_state``."""
    return session_state(root, timeout=timeout)


def uncertain(state: Doc) -> Doc:
    """The refusal when it can't be told whether an editor has the project open: nothing was read or written."""
    problem = state.get("problem") or {}
    discovery = str(problem.get("discovery") or "")
    return _fail("studio_session_uncertain",
                 f"Mesh Studio may have this project open, but its session couldn't be confirmed: {problem.get('why')}. "
                 "Nothing was changed, so no unsaved work in Studio can be overwritten. If Studio is open, make sure it "
                 "is responding (not frozen or showing a dialog) and try again; changes will then go to it for review. "
                 "If it isn't running, open the project in Mesh Studio once (that replaces its leftover session "
                 f"record) or delete {discovery}, then try again.",
                 problem=problem.get("reason"), discovery=discovery)


def other_editor(host: str) -> Doc:
    """The refusal when another editor (not Mesh Studio) has the project open: its unsaved edits aren't in the files,
    and it takes no proposals, so nothing was read as current or written."""
    return _fail("other_editor_open",
                 f"Another editor ({host or 'not Mesh Studio'}) has this project open, so nothing was read or written: "
                 "its unsaved edits aren't in the files and would be overwritten, or would overwrite these changes. "
                 "Close it (saving or discarding its work), or open the project in Mesh Studio instead, where changes "
                 "are proposed for the person to review; then try again.", host=host)


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
    state = studio_state(root)
    if state["state"] == "uncertain":  # (the files may be behind what the person sees: don't offer them as current)
        return uncertain(state)
    if state["state"] == "live" and state["host"] != STUDIO_HOST:  # (its unsaved edits aren't in the files either)
        return other_editor(state["host"])
    if state["state"] == "live":
        result = _call(state["info"], "GET", "/live/read_scene")
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
    state = studio_state(root)
    if state["state"] == "uncertain":
        return uncertain(state)
    if state["state"] == "none":
        return _fail("studio_not_open", "Mesh Studio doesn't have this project open. Open it there, or use "
                                        "apply_changes to change the files directly.")
    if state["host"] != STUDIO_HOST:
        return other_editor(state["host"])
    payload: Doc = {"changes": changes, "title": title, "source": source or "an AI"}
    if base_revision is not None:
        payload["base_revision"] = int(base_revision)
    result = _call(state["info"], "POST", "/live/stage_proposal", payload)
    if result.get("ok"):
        result["next"] = "The person reviews it in Mesh Studio (top bar: AI). proposal_status tells you what they decided."
    return result


def _studio(root: str | Path) -> tuple[Doc, Doc | None]:
    """``(info, None)`` for the Mesh Studio that has this project open, else ``({}, the failure)``."""
    state = studio_state(root)
    if state["state"] == "uncertain":
        return {}, uncertain(state)
    if state["state"] != "live" or state["host"] != STUDIO_HOST:
        return {}, _fail("studio_not_open", "Mesh Studio doesn't have this project open.")
    return state["info"], None


def proposal_status(root: str | Path, proposal_id: str) -> Doc:
    info, failure = _studio(root)
    return failure or _call(info, "GET", f"/live/proposal?id={proposal_id}")


def withdraw(root: str | Path, proposal_id: str) -> Doc:
    info, failure = _studio(root)
    return failure or _call(info, "POST", "/live/reject_proposal", {"proposal_id": proposal_id})


def apply(root: str | Path, changes: list[Doc], *, dry_run: bool = False, title: str = "", source: str = "") -> Doc:
    """Change the project: as a proposal if Studio has it open, straight to its files if nothing has it open, and
    not at all if that can't be told. A proposal that fails is never written to the files instead."""
    state = studio_state(root)
    if state["state"] == "uncertain":
        return uncertain(state)
    if state["state"] == "live" and state["host"] != STUDIO_HOST:
        return other_editor(state["host"])
    if state["state"] == "live":
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
        recheck = studio_state(root)  # (just before the first write: Studio may have opened it meanwhile)
        if recheck["state"] == "uncertain":
            return uncertain(recheck)
        if recheck["state"] == "live" and recheck["host"] != STUDIO_HOST:
            return other_editor(recheck["host"])
        if recheck["state"] == "live":
            return _fail("studio_open", "Mesh Studio opened this project just now, so nothing was written: apply the "
                                        "changes again to propose them there.")
        result = authoring.apply(project, changes)
        written = project.save()
    except authoring.ChangeError as err:
        return _fail("invalid_change", str(err), index=err.index, op=err.op)
    return {"ok": True, "source": "files", "summary": authoring.summarize(before, after),
            "created": {str(k): v for k, v in result["created"].items()}, "written": written}
