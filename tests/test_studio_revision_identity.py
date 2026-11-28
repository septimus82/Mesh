"""#462 R1: a revision an AI read in one Mesh Studio session never identifies work in another.

Astra's reproduction: an AI reads a project in Studio (revision 0). The person renames an object and saves; Studio
closes and opens again, and the reopened project starts at revision 0 again. The AI's old proposal, based on revision
0, was taken as based on the current project: staged with no stale base, accepted with no conflict, over the person's
saved rename (only undo brought it back).

A revision number counts changes within one opening of the project, so it can't say which opening it came from.
``read_project`` now also gives ``revision_id``: the number with that opening's identity (``Project.session``,
random, new each time a project is opened). ``propose_changes`` takes it as ``base_revision_id``; a revision id of
another session or project is refused (``revision_from_another_session``), and a bare number is refused
(``revision_id_required``) since it can't be told apart.

Each Studio here is its own process (``tests/studio_owner_process.py``: Studio's project, AI host and live-session
bridge, the production code, with no window), so a restart is a real one. The AI is ``engine.authoring_session``
(what the MCP tools and ``mesh author`` call), in this process. Same-session behaviour (older revisions, F6
eviction, malformed input, every way in): tests/test_studio_ai_base_revision.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import authoring_session
from engine.project_scaffold import create_project
from tests.test_studio_project_ownership import ROOM, StudioProcess

pytestmark = pytest.mark.integration  # (F13-A, #422: bridges, subprocesses; every default run has it)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    """``open(root)`` starts a Studio process; every one still running is killed at the end."""
    started: list[StudioProcess] = []

    def open_studio(root: Path) -> StudioProcess:
        studio = StudioProcess(root, log=tmp_path / f"studio_{len(started)}.log")
        assert studio.start["ready"], studio.start
        started.append(studio)
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _on_disk(root: Path) -> list[str]:
    return [str(e.get("name")) for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]
            if e.get("name") not in (None, "None")]


def _names(studio: StudioProcess) -> list[str]:
    return [n for n in studio.ask("state")["names"] if n != "None"]


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and ".mesh" not in p.relative_to(root).parts}


def _warden(root: Path, studios: Any) -> str:
    """A Warden in the start room, saved (Studio opened and closed for it); its id."""
    setup = studios(root)
    setup.ask("edit Warden")
    setup.ask("save")
    assert setup.close() == 0
    return next(e["id"] for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]
                if e.get("name") == "Warden")


def _rename(entity_id: str, name: str) -> list[dict[str, Any]]:
    return [{"op": "rename_entity", "entity_id": entity_id, "name": name}]


# ---------------------------------------------------------------- the reproduction
def test_a_revision_read_before_studio_restarted_never_passes_for_the_reopened_project(root: Path, studios: Any) -> None:
    warden = _warden(root, studios)
    a = studios(root)  # Studio, one lifetime
    read = authoring_session.read_project(root)  # the AI reads: revision 0
    assert read["revision"] == 0
    a.ask(f"rename {warden} Creator Warden")  # the person renames the Warden and saves
    assert a.ask("save")["saved"] == [ROOM]
    assert a.close() == 0
    b = studios(root)  # Studio again: its project starts at revision 0 too
    files = _files(root)

    old_number = authoring_session.propose(root, _rename(warden, "AI Warden"), title="AI rename",
                                           base_revision=read["revision"])
    assert old_number["ok"] is False, "the revision read before the restart was taken as the reopened project's"
    assert old_number["reason"] == "revision_id_required" and "read_project" in old_number["message"]
    old_identity = authoring_session.propose(root, _rename(warden, "AI Warden"), title="AI rename",
                                             base_revision_id=read["revision_id"])
    assert old_identity["ok"] is False and old_identity["reason"] == "revision_from_another_session", old_identity
    assert "Read the project again" in old_identity["message"] and "revision_id" not in old_identity

    assert b.ask("state")["pending"] == []  # nothing in the person's inbox ...
    assert _files(root) == files and _on_disk(root) == ["Creator Warden"]  # ... the saved rename untouched
    assert _names(b) == ["Player", "Creator Warden"] and b.ask("state")["unsaved"] is False

    fresh = authoring_session.read_project(root)  # read again: both at revision 0, never the same identity
    assert fresh["revision"] == read["revision"] == 0 and fresh["revision_id"] != read["revision_id"]
    staged = authoring_session.propose(root, _rename(warden, "AI Warden"), title="AI rename",
                                       base_revision_id=fresh["revision_id"])
    assert staged["ok"] and staged["proposal"]["base_revision_id"] == fresh["revision_id"]
    assert any("Creator Warden" in line and "AI Warden" in line for line in staged["proposal"]["summary"])
    assert b.ask("accept")["result"]["ok"]  # the person sees what it replaces, and accepts
    assert _names(b) == ["Player", "AI Warden"]
    assert b.ask("undo")["done"] and _names(b) == ["Player", "Creator Warden"]  # still one undo step
    assert b.ask("redo")["done"] and _names(b) == ["Player", "AI Warden"]
    assert b.close() == 0


def test_a_crash_never_revives_a_revision_and_a_rejection_still_changes_nothing(root: Path, studios: Any) -> None:
    warden = _warden(root, studios)
    a = studios(root)
    read = authoring_session.read_project(root)
    a.ask(f"rename {warden} Unsaved Keeper")  # unsaved, then Studio crashes
    a.kill()
    b = studios(root)  # (the crashed Studio's record is replaced by this one's)
    for revision_id in (read["revision_id"], authoring_session.read_project(root)["revision_id"]):
        answer = authoring_session.propose(root, _rename(warden, "Guard"), base_revision_id=revision_id)
        if revision_id == read["revision_id"]:  # the crashed session's revision: refused
            assert answer["reason"] == "revision_from_another_session", answer
            assert b.ask("state")["pending"] == []
        else:  # this session's: staged, and the person may reject it
            assert answer["ok"] and b.ask("state")["pending"] == ["Changes from an AI"]
            assert b.ask("reject")["result"]["status"] == "rejected"
    assert b.ask("state")["pending"] == [] and _names(b) == ["Player", "Warden"] and _on_disk(root) == ["Warden"]
    assert b.close() == 0


def test_a_revision_of_another_project_is_refused(root: Path, tmp_path: Path, studios: Any) -> None:
    other = tmp_path / "other"
    create_project(other, "Other", template_id="blank")
    warden = _warden(root, studios)
    in_root, in_other = studios(root), studios(other)
    here, there = authoring_session.read_project(root), authoring_session.read_project(other)
    assert here["revision"] == there["revision"] == 0 and here["revision_id"] != there["revision_id"]
    refused = authoring_session.propose(root, _rename(warden, "Guard"), base_revision_id=there["revision_id"])
    assert refused["reason"] == "revision_from_another_session", refused
    assert in_root.ask("state")["pending"] == [] and in_other.ask("state")["pending"] == []
    assert authoring_session.propose(root, _rename(warden, "Guard"), base_revision_id=here["revision_id"])["ok"]
    assert in_root.close() == 0 and in_other.close() == 0
