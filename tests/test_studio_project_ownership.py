"""#462 R2: a project has one writable owner at a time, across processes.

Astra's reproduction: Mesh Studio A has a project open with unsaved work. A second Studio, B, opens the same project
(its session record replaces A's) and closes (the record goes with it). A is still open, but an outside tool now sees
no session at all, and writes the project's files directly; A's next save then overwrites them.

Each Studio here is its own process (``tests/studio_owner_process.py``): Studio's project documents, AI host and
live-session bridge, the production code, with no window. The outside tool is ``engine.authoring_session`` (what the
MCP tools and ``mesh author`` call), in this process. The real-window check is
tests/test_studio_project_ownership_gpu.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import authoring_session
from engine.editor import project_ownership
from engine.editor.live_session_bridge import session_file_path
from engine.project_scaffold import create_project

pytestmark = pytest.mark.integration  # (F13-A, #422: bridges, subprocesses; every default run has it)
REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "tests" / "studio_owner_process.py"
ROOM = "packs/core_regions/scenes/start.json"
ADD_SEXTON = [{"op": "place_prefab", "prefab": "person", "x": 320, "y": 224},
              {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"}]


class StudioProcess:
    """A Mesh Studio session in its own process; ``start`` is what it said on opening (``ready``, or ``refused``)."""

    def __init__(self, root: Path, *args: str, log: Path, env: dict[str, str | None] | None = None) -> None:
        """``env``: what its environment has besides this process's (None: without that variable)."""
        self._log = open(log, "w", encoding="utf-8")  # noqa: SIM115  # (closed with the process: ``end``)
        self._commands, self._sent = log.with_suffix(".commands"), 0  # (commands are files, not stdin: the helper says why)
        self._commands.mkdir()
        self.proc = subprocess.Popen([sys.executable, str(HELPER), str(root), str(self._commands), *args],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=self._log, text=True,
                                     encoding="utf-8",
                                     env={k: v for k, v in {**os.environ, **(env or {})}.items() if v is not None})
        self.start = self._answer()

    def _answer(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:  # (the engine prints its own lines too: the answers are the JSON ones)
            if line.startswith("{"):
                answer = json.loads(line)
                assert isinstance(answer, dict)
                return answer
        raise AssertionError(f"the Studio process ended without answering (exit {self.proc.wait()})")

    def ask(self, command: str) -> dict[str, Any]:
        self._sent += 1
        written = self._commands / f"{self._sent:04d}.tmp"
        written.write_text(command, encoding="utf-8")
        written.replace(written.with_suffix(".cmd"))  # (whole, then in place: never read half-written)
        return self._answer()

    def close(self) -> int:
        """Closed as Studio closes."""
        if self.proc.poll() is None:
            self.ask("close")
        return self.end()

    def kill(self) -> int:
        """Ended as a crash ends it: none of its own code runs."""
        self.proc.kill()
        return self.end()

    def end(self) -> int:
        code = self.proc.wait(timeout=30)
        if self.proc.stdout is not None:
            self.proc.stdout.close()
        self._log.close()
        return code


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    """``open(root, *args, env=)`` starts a Studio process; every one still running is killed at the end."""
    started: list[StudioProcess] = []

    def open_studio(root: Path, *args: str, env: dict[str, str | None] | None = None) -> StudioProcess:
        # (a Studio that finds the project taken waits two seconds for it before saying so; here, a moment)
        studio = StudioProcess(root, *args, log=tmp_path / f"studio_{len(started)}.log",
                               env={"MESH_TEST_OWNER_WAIT": "0.3", **(env or {})})
        started.append(studio)
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()  # (its pipe and its log closed, whether it was refused, closed, killed or left running)


def _files(root: Path) -> dict[str, str]:
    """Every file of the project and its hash, the editors' own records in ``.mesh`` aside: equal before and after
    means nothing of the project was written or created."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".mesh" not in p.relative_to(root).parts}


def _on_disk(root: Path) -> list[str]:
    return [str(e.get("name")) for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]]


# ---------------------------------------------------------------- the reproduction
def test_a_second_studio_opening_and_closing_never_lets_outside_changes_past_the_first(root: Path, studios: Any) -> None:
    a = studios(root)
    assert a.start["ready"]
    a.ask("edit Unsaved Warden")  # A's unsaved work
    before = _files(root)

    b = studios(root)  # a second Studio on the same project
    if b.start["ready"]:  # (before the fix it opened: its record replaced A's, and closing it took the record away)
        b.close()
    assert b.start["ready"] is False, "the second Studio was let in"
    assert "already open in Mesh Studio" in b.start["refused"] and b.proc.wait(timeout=30) == 3

    state = authoring_session.studio_state(root)  # A is still the project's session
    assert state["state"] == "live" and state["info"]["session_id"] == a.start["session_id"]
    result = authoring_session.apply(root, ADD_SEXTON)  # an outside tool's change
    assert result["ok"] and result.get("source") != "files" and "proposed there" in result["note"]
    assert _files(root) == before, "the project's files were written behind the open Studio"
    held = a.ask("state")
    assert "Unsaved Warden" in held["names"] and "Sexton" not in held["names"] and held["unsaved"]
    assert held["pending"] == ["Changes from an AI"]

    assert a.ask("accept")["result"]["ok"]  # the person accepts it in A, and saves
    assert a.ask("save")["saved"] == [ROOM]
    assert sorted(n for n in _on_disk(root) if n != "None") == ["Sexton", "Unsaved Warden"]
    assert not list(root.rglob("*.outside-change.bak")), "A's save found the files changed under it"

    assert a.close() == 0  # A closes: the project is nobody's
    assert authoring_session.studio_state(root) == {"state": "none"}
    c = studios(root)  # and another Studio can open it
    assert c.start["ready"] and c.ask("state")["names"].count("Sexton") == 1
    assert c.close() == 0


def _answer(proc: Any) -> dict[str, Any]:
    """The next answer of a Studio process started by hand (its JSON lines; the engine prints lines of its own)."""
    answer = next(json.loads(line) for line in proc.stdout if line.startswith("{"))
    assert isinstance(answer, dict)
    return answer


def _start(root: Path, commands: Path, **env: str) -> Any:
    """A Studio process started without waiting for its answer (``_answer``); ``commands``: its command folder."""
    commands.mkdir(exist_ok=True)
    return subprocess.Popen([sys.executable, str(HELPER), str(root), str(commands)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            env={**os.environ, **env})


def _end(proc: Any) -> None:
    proc.kill()
    proc.wait(timeout=30)
    if proc.stdout is not None:
        proc.stdout.close()


# ---------------------------------------------------------------- a Studio that crashed
def test_a_crashed_studios_record_authorizes_nothing_until_it_is_recovered_on_purpose(root: Path, studios: Any) -> None:
    a = studios(root)
    a.ask("edit Unsaved Warden")
    a.kill()  # (a crash: none of its own code runs; its record stays, its hold on the project goes with the process)
    before = _files(root)
    assert session_file_path(root).is_file() and project_ownership.owned(root) is None

    state = authoring_session.studio_state(root)
    assert state["state"] == "uncertain" and state["problem"]["owned"] is False
    refused = authoring_session.apply(root, ADD_SEXTON)
    assert refused["ok"] is False and refused["reason"] == "studio_session_uncertain"
    assert "No editor has this project open now" in refused["message"] and "mesh author recover" in refused["message"]
    assert authoring_session.read_project(root)["reason"] == "studio_session_uncertain"
    assert _files(root) == before and session_file_path(root).is_file()  # nothing written, nothing removed for it

    recovered = authoring_session.recover(root)  # the explicit recovery
    assert recovered == {"ok": True, "removed": [str(session_file_path(root))]}
    assert authoring_session.studio_state(root) == {"state": "none"}
    assert authoring_session.apply(root, ADD_SEXTON)["source"] == "files" and "Sexton" in _on_disk(root)


def test_after_a_crash_the_next_studio_opens_the_project_and_is_its_session(root: Path, studios: Any) -> None:
    a = studios(root)
    a.kill()
    b = studios(root)  # the project isn't locked for good: another Studio opens it, and replaces the record
    assert b.start["ready"]
    state = authoring_session.studio_state(root)
    assert state["state"] == "live" and state["info"]["session_id"] == b.start["session_id"]
    assert "proposed there" in authoring_session.apply(root, ADD_SEXTON)["note"]
    assert b.close() == 0 and authoring_session.studio_state(root) == {"state": "none"}


def test_recovery_takes_nothing_from_a_studio_that_is_running(root: Path, studios: Any) -> None:
    a = studios(root)
    record = session_file_path(root).read_bytes()
    for _ in range(3):
        refused = authoring_session.recover(root)
        assert refused["ok"] is False and refused["reason"] == "project_open"
        assert "already open in Mesh Studio" in refused["message"]
    assert session_file_path(root).read_bytes() == record
    state = authoring_session.studio_state(root)
    assert state["state"] == "live" and state["info"]["session_id"] == a.start["session_id"]


def test_mesh_author_recover_says_what_it_did(root: Path, studios: Any, capsys: pytest.CaptureFixture[str]) -> None:
    import mesh_cli

    a = studios(root)
    assert mesh_cli.main(["author", "recover", "--project", str(root)]) == 1  # a Studio has it: nothing removed
    assert json.loads(capsys.readouterr().out)["reason"] == "project_open"
    a.kill()
    assert mesh_cli.main(["author", "recover", "--project", str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "removed": [str(session_file_path(root))]}
    assert mesh_cli.main(["author", "recover", "--project", str(root)]) == 0  # nothing left to remove: still fine
    assert json.loads(capsys.readouterr().out) == {"ok": True, "removed": []}


# ---------------------------------------------------------------- recovery repairs one project, never another
@pytest.fixture
def other(tmp_path: Path) -> Path:
    """A second project, B, beside ``root`` (A)."""
    path = tmp_path / "other"
    create_project(path, "Other", template_id="blank")
    return path


def _recover_cli(project: Path, repo_root: Path) -> tuple[int, dict[str, Any]]:
    """``mesh author recover --project PROJECT`` as its own process, run from a shell where MESH_REPO_ROOT names
    another project (``repo_root``)."""
    run = subprocess.run([sys.executable, "-m", "mesh_cli", "author", "recover", "--project", str(project)], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8", timeout=120,
                         env={**os.environ, "MESH_REPO_ROOT": str(repo_root)})
    answer = json.loads(run.stdout[run.stdout.index("{"):])  # (its answer is the JSON at the end of what it prints)
    assert isinstance(answer, dict)
    return run.returncode, answer


@pytest.mark.parametrize("how", ["recover", "mesh author recover"])
def test_recovering_one_project_never_touches_another_project_open_in_studio(
        root: Path, other: Path, studios: Any, monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    crashed = studios(root)  # A: a Studio crashed, leaving its record (one that may be recovered)
    crashed.kill()
    b = studios(other)  # B: open in Studio, with unsaved work
    b.ask("edit Unsaved Warden")
    b_record, b_files = session_file_path(other).read_bytes(), _files(other)

    if how == "recover":  # MESH_REPO_ROOT=B makes B the discovery root of A: it gives no authority over B
        with monkeypatch.context() as env:
            env.setenv("MESH_REPO_ROOT", str(other))
            recovered = authoring_session.recover(root)
        code = 0 if recovered["ok"] else 1
    else:
        code, recovered = _recover_cli(root, other)
    assert (code, recovered) == (0, {"ok": True, "removed": [str(session_file_path(root))]})  # A's record, only

    assert session_file_path(other).read_bytes() == b_record  # B's record exactly as it was
    assert (project_ownership.owned(other) or {}).get("kind") == project_ownership.STUDIO  # and B still owns B
    state = authoring_session.studio_state(other)
    assert state["state"] == "live" and state["info"]["session_id"] == b.start["session_id"]
    result = authoring_session.apply(other, ADD_SEXTON)  # outside changes to B still go to B, for review
    assert result["ok"] and "proposed there" in result["note"] and _files(other) == b_files
    held = b.ask("state")
    assert held["unsaved"] and "Unsaved Warden" in held["names"] and held["pending"] == ["Changes from an AI"]
    assert authoring_session.studio_state(root) == {"state": "none"}  # and A, recovered, may be written again
    assert b.close() == 0


def test_recovery_refuses_a_project_open_in_studio_and_touches_no_other(root: Path, other: Path, studios: Any) -> None:
    a = studios(root)  # A itself is open
    b = studios(other)
    records = {p: session_file_path(p).read_bytes() for p in (root, other)}
    code, refused = _recover_cli(root, other)
    assert (code, refused["ok"], refused["reason"]) == (1, False, "project_open")
    assert {p: session_file_path(p).read_bytes() for p in (root, other)} == records
    for studio, path in ((a, root), (b, other)):
        state = authoring_session.studio_state(path)
        assert state["state"] == "live" and state["info"]["session_id"] == studio.start["session_id"]


def test_a_record_found_through_mesh_repo_root_is_recovered_only_by_naming_its_own_project(
        root: Path, other: Path, studios: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    crashed = studios(other)  # B's Studio crashed; A has no record of its own
    crashed.kill()
    monkeypatch.setenv("MESH_REPO_ROOT", str(other))  # (so outside tools asking about A find B's record)
    refused = authoring_session.apply(root, ADD_SEXTON)
    assert refused["reason"] == "studio_session_uncertain"  # (ordinary discovery, unchanged: uncertain, refused)
    assert f'mesh author recover --project "{other.resolve()}"' in refused["message"]  # names B: the record's own project
    assert authoring_session.recover(root) == {"ok": True, "removed": []}  # recovering A removes nothing of B's
    assert session_file_path(other).is_file()
    assert authoring_session.recover(other) == {"ok": True, "removed": [str(session_file_path(other))]}


# ---------------------------------------------------------------- a Studio that is running but can't be confirmed
def _cut_short(path: Path) -> None:
    path.write_text(path.read_text(encoding="utf-8")[:40], encoding="utf-8")


def _nobody_answers(path: Path) -> None:
    path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "port": 9}), encoding="utf-8")


@pytest.mark.parametrize("damage", [_cut_short, _nobody_answers], ids=["a malformed record", "a record nobody answers at"])
def test_a_running_studio_whose_session_cant_be_confirmed_is_never_written_behind(root: Path, studios: Any,
                                                                                 damage: Any) -> None:
    a = studios(root)
    a.ask("edit Unsaved Warden")
    before = _files(root)
    damage(session_file_path(root))
    state = authoring_session.studio_state(root)
    assert state["state"] == "uncertain" and state["problem"]["owned"] is True
    refused = authoring_session.apply(root, ADD_SEXTON)
    assert refused["reason"] == "studio_session_uncertain"
    assert "Don't delete the record while Studio is open" in refused["message"]
    assert authoring_session.recover(root)["reason"] == "project_open"  # and recovery won't remove it either
    assert _files(root) == before and a.ask("state")["unsaved"] is True


# ---------------------------------------------------------------- a Studio with its live session turned off
def test_a_studio_without_a_live_session_still_owns_its_project(root: Path, studios: Any) -> None:
    a = studios(root, "nobridge")  # (as MESH_STUDIO_NO_AI_BRIDGE: no bridge, no record)
    assert a.start["ready"] and a.start["session_id"] is None and not session_file_path(root).exists()
    a.ask("edit Unsaved Warden")
    before = _files(root)
    state = authoring_session.studio_state(root)
    assert state["state"] == "uncertain" and state["problem"]["reason"] == "owned_without_session"
    assert state["problem"]["owner"] == project_ownership.STUDIO
    for answer in (authoring_session.apply(root, ADD_SEXTON), authoring_session.read_project(root)):
        assert answer["ok"] is False and answer["reason"] == "studio_session_uncertain"
        assert "This project is in use" in answer["message"]
    b = studios(root)  # nor does a second Studio get in beside it
    assert b.start["ready"] is False
    assert _files(root) == before
    assert a.close() == 0
    assert authoring_session.apply(root, ADD_SEXTON)["source"] == "files"


# ---------------------------------------------------------------- two projects
def test_two_projects_are_each_edited_in_their_own_studio(tmp_path: Path, root: Path, studios: Any) -> None:
    other = tmp_path / "other"
    create_project(other, "Other", template_id="blank")
    a, b = studios(root), studios(other)
    assert a.start["ready"] and b.start["ready"]
    for project, studio in ((root, a), (other, b)):
        state = authoring_session.studio_state(project)
        assert state["state"] == "live" and state["info"]["session_id"] == studio.start["session_id"]
        assert "proposed there" in authoring_session.apply(project, ADD_SEXTON)["note"]
        assert studio.ask("state")["pending"] == ["Changes from an AI"]
    assert a.close() == 0
    assert authoring_session.studio_state(other)["state"] == "live"  # closing one leaves the other's project its own


# ---------------------------------------------------------------- starting and stopping at the same time
def test_of_several_studios_started_at_once_one_owns_the_project(root: Path, tmp_path: Path) -> None:
    gate = tmp_path / "go"
    started = [_start(root, tmp_path / f"commands_{i}", MESH_TEST_START_GATE=str(gate), MESH_TEST_OWNER_WAIT="0")
               for i in range(6)]
    try:
        gate.write_text("go", encoding="utf-8")  # all six open the project now
        answers = [_answer(proc) for proc in started]
        owners = [answer for answer in answers if answer["ready"]]
        assert len(owners) == 1, f"{len(owners)} Studios own the project"
        assert all("already open in Mesh Studio" in answer["refused"] for answer in answers if not answer["ready"])
        state = authoring_session.studio_state(root)
        assert state["state"] == "live" and state["info"]["session_id"] == owners[0]["session_id"]
    finally:
        for proc in started:
            _end(proc)


def test_a_studio_opening_as_another_closes_gets_the_project_only_once_it_is_let_go(root: Path, tmp_path: Path,
                                                                                   studios: Any) -> None:
    a = studios(root)
    a.ask("edit Saved Warden")
    assert a.ask("save")["saved"] == [ROOM]
    waiting = _start(root, tmp_path / "commands_b", MESH_TEST_OWNER_WAIT="30")  # B opens; it waits for the project
    try:
        for _ in range(5):  # while A has it, A's is the session, and B has not opened
            state = authoring_session.studio_state(root)
            assert state["state"] == "live" and state["info"]["session_id"] == a.start["session_id"]
            assert waiting.poll() is None
        assert a.close() == 0
        b = _answer(waiting)
        assert b["ready"] and b["session_id"] != a.start["session_id"]
        state = authoring_session.studio_state(root)
        assert state["state"] == "live" and state["info"]["session_id"] == b["session_id"]
    finally:
        _end(waiting)


def test_a_studio_opening_during_an_outside_write_opens_on_what_was_written(root: Path, tmp_path: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """apply owns the project from before it reads until it has saved. A Studio started in the middle waits for
    the project (never beside the write), and then opens on the files as written: not on the ones before."""
    from engine.studio_project import Project

    real_save = Project.save
    seen: dict[str, Any] = {}

    def slow_save(self: Any) -> Any:
        seen["studio"] = _start(root, tmp_path / "commands", MESH_TEST_OWNER_WAIT="30")
        threading.Event().wait(1.5)  # (the Studio has started and waits for the project all this time)
        seen["running_during_the_write"] = seen["studio"].poll() is None
        seen["owner_during_the_write"] = project_ownership.owned(root)
        return real_save(self)

    monkeypatch.setattr(Project, "save", slow_save)
    try:
        result = authoring_session.apply(root, ADD_SEXTON)
        assert result["ok"] and result["source"] == "files"
        assert seen["running_during_the_write"]
        assert seen["owner_during_the_write"]["kind"] == project_ownership.AUTHORING
        studio = seen["studio"]
        assert _answer(studio)["ready"]
        (tmp_path / "commands" / "0001.cmd").write_text("state", encoding="utf-8")
        held = _answer(studio)
        assert "Sexton" in held["names"] and held["unsaved"] is False  # it opened on the written files
    finally:
        if "studio" in seen:
            _end(seen["studio"])


# ---------------------------------------------------------------- the launch
def test_mesh_edit_refuses_a_project_another_studio_has_before_it_opens_a_window(root: Path, studios: Any,
                                                                                capsys: pytest.CaptureFixture[str],
                                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import game_launch

    def no_window(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a window was opened")

    monkeypatch.setattr(game_launch, "GameWindow", no_window)
    a = studios(root)
    record = session_file_path(root).read_bytes()
    code = game_launch.launch_editor(project_root=root)
    assert code == project_ownership.EXIT_OPEN_ELSEWHERE == 3
    said = capsys.readouterr().out
    assert "This project is already open in Mesh Studio. Use the window that has it" in said
    assert session_file_path(root).read_bytes() == record and a.ask("state")["session_id"] == a.start["session_id"]


# ---------------------------------------------------------------- the lock itself
def test_a_project_has_one_owner_and_asking_takes_nothing(root: Path) -> None:
    assert project_ownership.owned(root) is None and not project_ownership.lock_path(root).exists()  # asking makes no file
    held = project_ownership.acquire(root, project_ownership.STUDIO)
    assert held.held and project_ownership.lock_path(root).is_file()
    owner = project_ownership.owned(root)
    assert owner is not None and owner["kind"] == project_ownership.STUDIO and owner["pid"] == os.getpid()
    with pytest.raises(project_ownership.OwnedElsewhere, match="already open in Mesh Studio") as refused:
        project_ownership.acquire(root, project_ownership.STUDIO)  # (another part of this process is refused too)
    assert refused.value.holder["kind"] == project_ownership.STUDIO
    held.release()
    held.release()  # (twice is fine)
    assert not held.held and project_ownership.owned(root) is None
    with project_ownership.acquire(root, project_ownership.AUTHORING) as writing:
        with pytest.raises(project_ownership.OwnedElsewhere, match="An outside tool is writing"):
            project_ownership.acquire(root, project_ownership.STUDIO)
        assert writing.held
    assert project_ownership.owned(root) is None


def test_many_may_ask_at_once_and_an_owner_being_made_waits_for_them(root: Path) -> None:
    project_ownership.acquire(root, project_ownership.STUDIO).release()  # (the lock file exists)
    answers: list[Any] = []

    def ask() -> None:
        answers.extend(project_ownership.owned(root) for _ in range(200))

    askers = [threading.Thread(target=ask) for _ in range(8)]
    for thread in askers:
        thread.start()
    owners = 0
    while any(thread.is_alive() for thread in askers):  # owners made and let go while 1,600 questions are asked
        project_ownership.acquire(root, project_ownership.STUDIO, wait=10.0).release()
        owners += 1
    for thread in askers:
        thread.join()
    assert len(answers) == 1600 and owners > 0
    # Every answer is "nobody" or an owner. An owner caught between taking the project and writing its note (or
    # between clearing it and letting go) is an owner whose note can't be read: {}. How often that is seen depends
    # on timing (once in 1,600 on a CI runner), so it isn't asserted here; the test below pins it without a race.
    assert all(a is None or not a or a.get("kind") == project_ownership.STUDIO for a in answers)


def test_an_owner_with_no_note_yet_is_an_owner_and_asking_waits_a_moment_for_its_note(root: Path) -> None:
    project_ownership.acquire(root, project_ownership.STUDIO).release()  # (the lock file exists, with no note in it)
    owner = os.open(project_ownership.lock_path(root), os.O_RDWR | getattr(os, "O_BINARY", 0))
    writes = threading.Timer(0.1, lambda: os.write(owner, b'{"kind": "mesh_studio"}'))
    try:
        assert project_ownership._lock(owner, exclusive=True)  # an owner, at the instant it took the project
        assert project_ownership.owned(root, wait=0.0) == {}  # owned: by someone whose note can't be read yet
        with pytest.raises(project_ownership.OwnedElsewhere) as refused:
            project_ownership.acquire(root, project_ownership.AUTHORING)
        assert refused.value.holder == {}  # (and refused as owned, whoever it is)
        writes.start()
        assert project_ownership.owned(root, wait=10.0) == {"kind": "mesh_studio"}  # asks again until it's there
    finally:
        writes.cancel()
        writes.join()
        os.close(owner)


def test_someone_asking_is_not_an_owner_to_anyone_else_who_asks(root: Path) -> None:
    project_ownership.acquire(root, project_ownership.STUDIO).release()  # (the lock file exists)
    asking = os.open(project_ownership.lock_path(root), os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        assert project_ownership._lock(asking, exclusive=False)  # someone is in the middle of asking
        assert project_ownership.owned(root, wait=0.0) is None  # another who asks is told the truth: no owner
        assert project_ownership.owned(root, wait=0.0) is None
        with pytest.raises(project_ownership.OwnedElsewhere):  # an owner can't be made that very instant ...
            project_ownership.acquire(root, project_ownership.STUDIO)
    finally:
        os.close(asking)
    project_ownership.acquire(root, project_ownership.STUDIO).release()  # ... and can the next


def test_waiting_gets_the_project_when_a_brief_owner_lets_it_go(root: Path) -> None:
    brief = project_ownership.acquire(root, project_ownership.AUTHORING)
    threading.Timer(0.3, brief.release).start()
    with pytest.raises(project_ownership.OwnedElsewhere):
        project_ownership.acquire(root, project_ownership.STUDIO)  # no waiting: refused now
    project_ownership.acquire(root, project_ownership.STUDIO, wait=10.0).release()  # waiting: it gets it


# ---------------------------------------------------------------- faults: taking, publishing, letting go
def test_a_project_whose_ownership_cant_be_established_is_not_taken_as_free(root: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    def no_locks(_fd: int, *, exclusive: bool) -> bool:
        raise OSError(37, "No locks available")

    project_ownership.acquire(root, project_ownership.STUDIO).release()  # (the lock file exists)
    monkeypatch.setattr(project_ownership, "_lock", no_locks)
    with pytest.raises(project_ownership.OwnershipUnavailable, match="can't be locked on this file system"):
        project_ownership.acquire(root, project_ownership.STUDIO)
    before = _files(root)
    state = authoring_session.studio_state(root)
    assert state["state"] == "uncertain" and state["problem"]["reason"] == "ownership_unknown"
    assert authoring_session.apply(root, ADD_SEXTON)["reason"] == "studio_session_uncertain" and _files(root) == before
    monkeypatch.undo()
    blocked = root / ".mesh"
    for path in blocked.iterdir():
        path.unlink()
    blocked.rmdir()
    blocked.write_text("not a folder", encoding="utf-8")  # the ownership file can't even be made
    assert project_ownership.owned(root) is None  # (no lock file can be there: nothing owns it; on Linux and Windows)
    with pytest.raises(project_ownership.OwnershipUnavailable, match="can't be made or opened"):
        project_ownership.acquire(root, project_ownership.STUDIO)
    assert authoring_session.apply(root, ADD_SEXTON)["reason"] == "ownership_unknown"
    assert "Sexton" not in _on_disk(root)


def test_a_session_that_fails_to_publish_leaves_nothing_behind(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.editor import live_session_bridge

    def disk_full(*_args: Any) -> Any:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(live_session_bridge, "write_live_session_file", disk_full)
    editor = SimpleNamespace(host_kind="mesh_studio")
    bridge = live_session_bridge.EditorLiveSessionBridge(editor, root)
    with pytest.raises(OSError, match="No space left"):
        bridge.start()
    assert bridge._server is None and bridge._thread is None and getattr(editor, "live_bridge", None) is None
    assert not session_file_path(root).exists() and project_ownership.owned(root) is None  # nobody's project
    monkeypatch.undo()
    bridge = live_session_bridge.EditorLiveSessionBridge(editor, root)  # and it can be opened again
    bridge.start()
    assert authoring_session.studio_state(root)["state"] == "live"
    bridge.stop()
    assert authoring_session.studio_state(root) == {"state": "none"}


def test_a_second_session_in_the_same_process_is_refused_and_touches_nothing(root: Path) -> None:
    from engine.editor.live_session_bridge import EditorLiveSessionBridge

    first = EditorLiveSessionBridge(SimpleNamespace(host_kind="mesh_studio"), root)
    first.start()
    record = session_file_path(root).read_bytes()
    second = EditorLiveSessionBridge(SimpleNamespace(host_kind="mesh_studio"), root)
    with pytest.raises(project_ownership.OwnedElsewhere):
        second.start()
    second.stop()  # (stopping what never started removes nothing)
    assert session_file_path(root).read_bytes() == record
    assert authoring_session.studio_state(root)["info"]["session_id"] == first.session_id
    first.stop()
    assert not session_file_path(root).exists() and project_ownership.owned(root) is None


def test_letting_go_never_fails_and_a_bridge_keeps_a_hold_it_was_given(root: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.editor.live_session_bridge import EditorLiveSessionBridge

    studios_hold = project_ownership.acquire(root, project_ownership.STUDIO)  # (as Mesh Studio's own)
    bridge = EditorLiveSessionBridge(SimpleNamespace(host_kind="mesh_studio"), root, ownership=studios_hold)
    bridge.start()
    bridge.stop()
    assert studios_hold.held and project_ownership.owned(root) is not None  # Studio is still open: still its project
    real_close = os.close

    def failing_close(fd: int) -> None:
        real_close(fd)
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(project_ownership.os, "close", failing_close)
    studios_hold.release()  # nothing raised
    monkeypatch.undo()
    assert not studios_hold.held and project_ownership.owned(root) is None
