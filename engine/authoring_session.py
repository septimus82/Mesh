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
  what to do. Only "no session record at all, and nothing owns the project" counts as closed.

**Who may write (#462 R2).** A project has one writable owner at a time, across processes
(``engine.editor.project_ownership``: an operating-system lock). Mesh Studio owns it while it is open.
``apply``, writing the files directly, owns it for that one write: it takes the project *before* it reads
the files and holds it until they are saved, so a Studio can't open in between (it waits a moment, then
says the project is busy), and if a Studio has it, the write is refused. A second Studio opening or
closing never changes whose project it is.

Writing the files is ``Project.save`` (F3, ``engine.project_save``): every changed file or none. A save
that fails returns ``reason: "save_failed"`` with its report as ``save``: the stage and reason code,
what happened to each file, and, if putting files back failed too, ``recovery_required`` and where
each previous version is kept. The changes themselves are not kept anywhere: apply them again.

Every result is a plain dict with ``ok``, and on failure a ``reason`` and a ``message`` a person
or an AI can act on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import error, parse

from engine import authoring
from engine.editor import project_ownership
from engine.mcp_server.live_session_client import (
    _request_json,
    bad_request_id,
    new_request_id,
    remove_abandoned_session,
    session_state,
    unknown_outcome,
)
from engine.project_save import SaveError
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
    reason, owned = problem.get("reason"), problem.get("owned")
    if owned is False and discovery:  # (#462 R2: nothing owns the project: the editor that left this record is gone)
        # (the record's own project folder: recovery removes only the record of the project it was given)
        folder = Path(discovery).parent.parent
        message = (f"No editor has this project open now, but a session record that no editor answers for is in its "
                   f"folder ({problem.get('why')}): its editor crashed or was closed by force, perhaps with unsaved "
                   "work, or the record came with a copy of the project. Nothing was changed. To write the project's "
                   "files again, open the project in Mesh Studio once (that replaces the record), or remove the "
                   f"record ({discovery}) with `mesh author recover --project \"{folder}\"`, which first makes sure "
                   "nothing has that project open; then try again.")
    elif reason == "owned_without_session":
        message = (f"This project is in use: {problem.get('why')}. Nothing was changed, so nothing of its can be "
                   "overwritten. If Mesh Studio is starting, try again in a moment; changes will then go to it for "
                   "review. If it was started with its live session turned off, close it, or start it normally.")
    elif owned:  # (an editor holds the project, and its session can't be confirmed: it is running)
        message = (f"Mesh Studio has this project open, but its session couldn't be confirmed: {problem.get('why')}. "
                   "Nothing was changed, so no unsaved work in Studio can be overwritten. Make sure Studio is "
                   "responding (not frozen or showing a dialog) and try again; changes will then go to it for review. "
                   "If it keeps failing, save your work in Studio and open the project there again: that writes its "
                   f"session record ({discovery}) afresh. Don't delete the record while Studio is open.")
    else:
        message = (f"Mesh Studio may have this project open, but its session couldn't be confirmed: {problem.get('why')}. "
                   "Nothing was changed, so no unsaved work in Studio can be overwritten. If Studio is open, make sure "
                   "it is responding (not frozen or showing a dialog) and try again; changes will then go to it for "
                   "review. If it isn't running, open the project in Mesh Studio once (that replaces its leftover "
                   f"session record) or delete {discovery}, then try again.")
    return _fail("studio_session_uncertain", message, problem=reason, discovery=discovery)


def recover(root: str | Path = ".") -> Doc:
    """Remove a session record whose editor is gone (#462 R2), so that the project's files can be written again.
    The project is owned for the moment it takes: if an editor has it open, nothing is removed. Only the record of
    the project at ``root`` is removed, the one project owned here (never another, whatever ``MESH_REPO_ROOT`` says)."""
    try:
        held = project_ownership.acquire(root, project_ownership.AUTHORING, wait=0.5)
    except project_ownership.OwnedElsewhere as owned:
        return _fail("project_open", f"Nothing was removed: {owned} Its session record is in use.")
    except project_ownership.OwnershipUnavailable as exc:
        return _fail("ownership_unknown", f"Nothing was removed: {exc}")
    with held:
        return {"ok": True, "removed": remove_abandoned_session(root)}


def other_editor(host: str) -> Doc:
    """The refusal when another editor (not Mesh Studio) has the project open: its unsaved edits aren't in the files,
    and it takes no proposals, so nothing was read as current or written."""
    return _fail("other_editor_open",
                 f"Another editor ({host or 'not Mesh Studio'}) has this project open, so nothing was read or written: "
                 "its unsaved edits aren't in the files and would be overwritten, or would overwrite these changes. "
                 "Close it (saving or discarding its work), or open the project in Mesh Studio instead, where changes "
                 "are proposed for the person to review; then try again.", host=host)


def _call(info: Doc, method: str, path: str, payload: Doc | None = None, *, timeout: float = 6.0,
          request_id: str = "") -> Doc:
    """One request to Mesh Studio. A POST that gets no answer may have run there: ``outcome_unknown`` with its
    ``request_id`` for ``request_status``, never a failure (#462 S3). The caller's ``request_id`` makes a retry the same
    request: never done twice."""
    bad = bad_request_id(request_id)
    if bad is not None:
        return bad
    request_id = new_request_id(method, request_id)
    try:
        return _request_json(info, method, path, payload, timeout=timeout, request_id=request_id)
    except (OSError, TimeoutError, ValueError, error.URLError) as exc:
        return unknown_outcome(exc, request_id) or _fail("studio_unreachable", f"Mesh Studio didn't answer: {exc}")


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
    return {"ok": True, "source": "files", "revision": None, "revision_id": None, "current_room": project.current,
            "world": docs["world"],
            "rooms": rooms, "player": docs["player"], "models": authoring.models(project)}


def propose(root: str | Path, changes: list[Doc], *, title: str = "", base_revision: int | None = None,
            source: str = "", request_id: str = "", base_revision_id: str | None = None) -> Doc:
    """Send changes to the Mesh Studio that has this project open, for the person to review. ``base_revision_id``:
    the ``revision_id`` of the reading they are based on (#462 R1); a bare ``base_revision`` is refused by Studio
    (``revision_id_required``: it can't say which session it was read in)."""
    state = studio_state(root)
    if state["state"] == "uncertain":
        return uncertain(state)
    if state["state"] == "none":
        return _fail("studio_not_open", "Mesh Studio doesn't have this project open. Open it there, or use "
                                        "apply_changes to change the files directly.")
    if state["host"] != STUDIO_HOST:
        return other_editor(state["host"])
    payload: Doc = {"changes": changes, "title": title, "source": source or "an AI"}
    if base_revision is not None:  # (as given: Mesh Studio checks it, and never takes another in its place, F6)
        payload["base_revision"] = base_revision
    if base_revision_id is not None:  # (as given, too: #462 R1)
        payload["base_revision_id"] = base_revision_id
    result = _call(state["info"], "POST", "/live/stage_proposal", payload, request_id=request_id)
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


def withdraw(root: str | Path, proposal_id: str, *, request_id: str = "") -> Doc:
    info, failure = _studio(root)
    return failure or _call(info, "POST", "/live/reject_proposal", {"proposal_id": proposal_id}, request_id=request_id)


def request_status(root: str | Path, request_id: str) -> Doc:
    """What became of a request the editor open on this project was sent (#462 S3; ``live_session_bridge``)."""
    state = studio_state(root)
    if state["state"] == "uncertain":
        return uncertain(state)
    if state["state"] != "live":
        return _fail("studio_not_open", "No editor has this project open now. One that closed never ran what it "
                                        "hadn't started; read the project to see what it holds.")
    return _call(state["info"], "GET", "/live/request?" + parse.urlencode({"id": request_id}))


def apply(root: str | Path, changes: list[Doc], *, dry_run: bool = False, title: str = "", source: str = "",
          request_id: str = "") -> Doc:
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
        result = propose(root, changes, title=title, source=source, request_id=request_id)
        if result.get("ok"):
            result["note"] = ("Mesh Studio has this project open, so the changes were proposed there instead of "
                              "written to the files (that would overwrite the person's unsaved work).")
        return result
    held = None
    if not dry_run:
        # (#462 R2) Own the project for this write, from before its files are read until they are saved: no Studio
        # can open it meanwhile, and if one has it (it opened since the check above) nothing is read or written.
        try:
            held = project_ownership.acquire(root, project_ownership.AUTHORING, wait=0.5)
        except project_ownership.OwnedElsewhere as owned:
            kind = owned.holder.get("kind")
            if kind == project_ownership.AUTHORING:
                return _fail("project_busy", "Another tool is writing this project's files right now, so nothing was "
                                             "written. Apply the changes again in a moment.")
            if kind == project_ownership.EDITOR:
                return other_editor(project_ownership.EDITOR)
            return _fail("studio_open", "Mesh Studio opened this project just now, so nothing was written: apply the "
                                        "changes again to propose them there.")
        except project_ownership.OwnershipUnavailable as exc:
            return _fail("ownership_unknown", f"Nothing was written: {exc}")
    try:
        return _apply_to_files(root, changes, dry_run, held)
    finally:
        if held is not None:
            held.release()


def _apply_to_files(root: str | Path, changes: list[Doc], dry_run: bool, held: Any = None) -> Doc:
    """The changes applied to the project's files (``apply`` owns the project, unless it is only a dry run). The save
    writes only files ``held`` covers (#462 R5 remediation B: a room in a nested project refuses it, nothing written)."""
    try:
        project = open_project(root)
        before, after = authoring.dry_run(project, changes)
        if dry_run:
            return {"ok": True, "source": "files", "dry_run": True, "summary": authoring.summarize(before, after, project.root)}
        result = authoring.apply(project, changes)
        written = project.save(owner=held)
    except authoring.ChangeError as err:
        return _fail("invalid_change", str(err), index=err.index, op=err.op)
    except SaveError as err:
        project.discard_unsaved_files()  # (#462 S4: nothing saved, so a new room's map file goes, unless it needs recovery)
        again = ("Apply the changes again once the files are put back." if err.report["recovery_required"]
                 else "Apply them again once the problem is fixed.")
        return _fail("save_failed", f"The changes were checked but not saved: {err} {again}",
                     save={**err.report, "unsaved_edits_kept": False})
    return {"ok": True, "source": "files", "summary": authoring.summarize(before, after, project.root),
            "created": {str(k): v for k, v in result["created"].items()}, "written": written}
