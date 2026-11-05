"""#462 S3: a request to the editor that timed out never runs later, and one that started is never called failed.

The loopback bridge queues each request for the editor's main thread and waits for it until a deadline. A request
still queued at its deadline used to be answered "timeout" and left in the queue, so the editor ran it whenever its
main thread came back: an AI told its proposal failed found it in the person's inbox (twice, if it tried again), and a
play-test said not started started. A request the main thread had started but not finished was answered "timeout"
too, though it went on to change the project.

Now each request is queued, started, finished or cancelled, one lock deciding each change (the table in
``engine.editor.live_session_bridge``): at the deadline a queued one is cancelled and never runs, and a started one is
answered ``outcome_unknown`` with its ``request_id``, which ``request_status`` answers once it has finished. The same
id again is the same request, never run twice. Stopping the editor cancels only what hasn't started.

Each test runs a real StudioAIHost on its loopback bridge over a real project, the AI going through
``authoring_session`` / the MCP tools or raw HTTP, and drains the queue itself (Studio's main thread), so every race
is ordered by events, not timing luck. They check the person's documents, inbox and play-tests, not only answers.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib import error

import pytest

from engine import authoring, authoring_session, runtime_debug, runtime_play
from engine.editor import live_session_bridge
from engine.mcp_server import live_session_client, tools
from engine.mcp_server.live_session_client import _request_json
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (F13-A: loopback bridges)
ROOM = "packs/core_regions/scenes/start.json"
BARREL = [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64}]
WAIT = 5.0  # longest any event is waited for: a hang fails the test instead of stalling it


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM))
        self.inbox: list[str] = []  # proposals the person was shown
        self.plays = 0  # play-tests started

    def on_ai_proposal(self, proposal: Any) -> None:
        self.inbox.append(proposal.title)

    def on_ai_decided(self, proposal: Any) -> None:
        pass

    def ai_start_playtest(self) -> dict[str, Any]:
        self.plays += 1
        return {"ok": True, "mode": "live_studio", "status": "playing"}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studio(root: Path) -> Iterator[tuple[_Studio, StudioAIHost]]:
    """Mesh Studio with the project open and its live session running; nothing drains until a test does."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    person = _Studio(Project(root, config["world_file"]))
    host = StudioAIHost(person)
    host.start()
    host.playtest_control = True
    try:
        yield person, host
    finally:
        host.stop()


@contextmanager
def _pumping(host: StudioAIHost) -> Iterator[None]:
    """Studio's main thread running: the queue drained until the block ends."""
    stop = threading.Event()

    def pump() -> None:
        while not stop.is_set():
            host.drain()
            stop.wait(0.005)

    thread = threading.Thread(target=pump, name="drain", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(WAIT)


def _in_thread(func: Callable[[], Any], name: str = "waiter") -> tuple[threading.Thread, list[Any]]:
    out: list[Any] = []
    thread = threading.Thread(target=lambda: out.append(func()), name=name, daemon=True)
    thread.start()
    return thread, out


def _until(check: Callable[[], bool]) -> None:
    """Wait (bounded) for another thread to reach a state the test can only observe."""
    done = threading.Event()
    for _ in range(int(WAIT / 0.005)):
        if check():
            return
        done.wait(0.005)
    raise AssertionError("timed out waiting for the bridge")


def _info(host: StudioAIHost) -> dict[str, Any]:
    return host.bridge.info.to_dict()


def _post(host: StudioAIHost, path: str, payload: dict[str, Any], request_id: str, *, timeout: float = 6.0) -> dict:
    return _request_json(_info(host), "POST", path, payload, timeout=timeout, request_id=request_id)


def _unchanged(person: _Studio, documents: dict[str, Any], revision: int) -> None:
    assert person.project.all_documents() == documents and person.project.revision == revision


class _GateLock:
    """The bridge's lock, able to hold a named thread just before it takes it: the race's window, opened on demand."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.takes: dict[str, int] = {}
        self.hold: dict[tuple[str, int], tuple[threading.Event, threading.Event]] = {}  # (thread, nth take): at, go

    def __enter__(self) -> _GateLock:
        name = threading.current_thread().name
        nth = self.takes[name] = self.takes.get(name, 0) + 1
        gate = self.hold.get((name, nth))
        if gate is not None:
            gate[0].set()
            assert gate[1].wait(WAIT)
        self._lock.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._lock.release()

    def at(self, name: str, nth: int) -> tuple[threading.Event, threading.Event]:
        self.hold[(name, nth)] = gate = (threading.Event(), threading.Event())
        return gate


# --------------------------------------------------------------------- the reported defect, through the MCP path

def test_a_proposal_that_timed_out_while_queued_never_reaches_the_person(root: Path, studio: Any) -> None:
    person, host = studio
    host.bridge.request_timeout = 0.2  # (Studio's main thread busy: nothing drains)
    documents, revision = person.project.all_documents(), person.project.revision
    answer = tools.propose_changes(BARREL, title="Barrel", root=str(root))
    assert answer["ok"] is False and answer["reason"] == "timeout"
    host.drain()  # (the main thread comes back)
    assert host.proposals == [] and person.inbox == []  # (was: staged now, after "timeout")
    _unchanged(person, documents, revision)
    assert answer["request_state"] == "cancelled" and "never ran" in answer["message"] and answer["request_id"]
    assert host.bridge.pending_count() == 0 and host.bridge.drain_pending() == 0
    status = tools.request_status(answer["request_id"], root=str(root))
    assert status["ok"] is True and status["state"] == "cancelled" and status["result"]["reason"] == "timeout"
    with _pumping(host):  # sending it again (a new request) stages it, once
        again = tools.propose_changes(BARREL, title="Barrel", root=str(root))
    assert again["ok"] is True and again["request_state"] == "finished" and person.inbox == ["Barrel"]
    assert [p.proposal_id for p in host.proposals] == [again["proposal_id"]]


def test_a_play_test_start_that_timed_out_never_starts_later(root: Path, studio: Any) -> None:
    person, host = studio
    host.bridge.request_timeout = 0.2
    answers = [runtime_debug.request_play(root) for _ in range(3)]  # (an AI trying again while Studio is busy)
    assert [a["reason"] for a in answers] == ["timeout"] * 3
    host.bridge.drain_pending()
    assert person.plays == 0  # (was: 3 play-tests started now, each after "timeout")
    assert [a["request_state"] for a in answers] == ["cancelled"] * 3 and host.bridge.drain_pending() == 0
    with _pumping(host):
        assert runtime_debug.request_play(root)["status"] == "playing"
    assert person.plays == 1


def test_a_proposal_drained_before_its_deadline_is_staged_once(root: Path, studio: Any) -> None:
    person, host = studio
    host.bridge.request_timeout = 30.0
    thread, out = _in_thread(lambda: authoring_session.propose(root, BARREL, title="Barrel"))
    _until(lambda: host.bridge.pending_count() == 1)
    assert host.bridge.drain_pending() == 1
    thread.join(WAIT)
    assert out[0]["ok"] is True and out[0]["request_state"] == "finished"
    assert [p.proposal_id for p in host.proposals] == [out[0]["proposal_id"]] and person.inbox == ["Barrel"]
    status = tools.request_status(out[0]["request_id"], root=str(root))
    assert status["state"] == "finished" and status["result"]["proposal_id"] == out[0]["proposal_id"]


# --------------------------------------------------------------------- the two transitions out of "queued"

def test_the_drain_taking_it_first_at_the_deadline_runs_it_and_says_so(root: Path, studio: Any,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    person, host = studio
    bridge = host.bridge
    gate = _GateLock()
    monkeypatch.setattr(bridge, "_lock", gate)
    at_lock, go = gate.at("waiter", 2)  # (1: registered; 2: the check at its deadline)
    payload = {"changes": BARREL, "title": "Barrel"}
    thread, out = _in_thread(lambda: bridge._enqueue(lambda: bridge._stage_proposal(payload), request_id="r1",
                                                     fingerprint="f", wait=0.1))
    assert at_lock.wait(WAIT)  # its deadline passed; it is about to cancel ...
    assert bridge.drain_pending() == 1  # ... but the main thread takes the lock first: started, run, finished
    go.set()
    thread.join(WAIT)
    assert out[0]["ok"] is True and out[0]["request_state"] == "finished"  # (not "timeout": it ran)
    assert [p.proposal_id for p in host.proposals] == [out[0]["proposal_id"]] and person.inbox == ["Barrel"]


def test_the_deadline_taking_it_first_while_the_drain_holds_it_cancels_it(root: Path, studio: Any,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    person, host = studio
    bridge = host.bridge
    documents, revision = person.project.all_documents(), person.project.revision
    gate = _GateLock()
    monkeypatch.setattr(bridge, "_lock", gate)
    drain_at_lock, drain_go = gate.at("drain", 1)  # (about to take it off the queue and start it)
    ran: list[bool] = []
    thread, out = _in_thread(lambda: bridge._enqueue(lambda: ran.append(True) or {"ok": True}, request_id="r2",
                                                     fingerprint="f", wait=0.3))
    _until(lambda: bridge.pending_count() == 1)
    drainer, drained = _in_thread(bridge.drain_pending, name="drain")
    assert drain_at_lock.wait(WAIT)
    thread.join(WAIT)  # its deadline passes while the drain waits at the lock: cancelled
    assert out[0]["reason"] == "timeout" and out[0]["request_state"] == "cancelled"
    drain_go.set()
    drainer.join(WAIT)
    assert drained == [0] and ran == []  # (the drain found it cancelled: skipped, never run)
    _unchanged(person, documents, revision)


def test_a_started_request_past_its_deadline_is_unknown_never_failed_and_its_result_comes_later(
        root: Path, studio: Any) -> None:
    person, host = studio
    bridge = host.bridge
    bridge.request_timeout = 0.2
    entered, release = threading.Event(), threading.Event()
    real = authoring.dry_run

    def slow(*args: Any, **kwargs: Any) -> Any:  # (a big project: staging outlasts the deadline)
        entered.set()
        assert release.wait(WAIT)
        return real(*args, **kwargs)

    payload = {"changes": BARREL, "title": "Slow"}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(authoring, "dry_run", slow)
        drainer, _ = _in_thread(lambda: (_until(lambda: bridge.pending_count() == 1), bridge.drain_pending()),
                                name="drain")
        answer = _post(host, "/live/stage_proposal", payload, "slow-1")
        assert entered.wait(WAIT)
        assert answer["ok"] is False and answer["reason"] == "outcome_unknown" and answer["request_state"] == "started"
        assert answer["request_id"] == "slow-1" and "request_status" in answer["message"]
        assert _post(host, "/live/stage_proposal", payload, "slow-1")["reason"] == "outcome_unknown"  # (no 2nd run)
        assert tools.request_status("slow-1", root=str(root))["state"] == "started"
        release.set()
        drainer.join(WAIT)
    status = tools.request_status("slow-1", root=str(root))
    assert status["state"] == "finished" and status["result"]["ok"] is True
    assert [p.proposal_id for p in host.proposals] == [status["result"]["proposal_id"]] and person.inbox == ["Slow"]
    again = _post(host, "/live/stage_proposal", payload, "slow-1")  # (the same request: its result, not a new run)
    assert again["proposal_id"] == status["result"]["proposal_id"] and len(host.proposals) == 1


# --------------------------------------------------------------------- the same request again

def test_the_same_request_id_runs_once_however_often_it_is_sent(root: Path, studio: Any) -> None:
    person, host = studio
    host.bridge.request_timeout = 30.0
    payload = {"changes": BARREL, "title": "Barrel"}
    first, out = _in_thread(lambda: _post(host, "/live/stage_proposal", payload, "dup-1"))
    _until(lambda: host.bridge.pending_count() == 1)
    others = [_in_thread(lambda: _post(host, "/live/stage_proposal", payload, "dup-1")) for _ in range(3)]
    assert host.bridge.pending_count() == 1
    assert host.bridge.drain_pending() == 1
    for thread, _ in [(first, out), *others]:
        thread.join(WAIT)
    answers = out + [o[0] for _, o in others]
    assert {a["proposal_id"] for a in answers} == {host.proposals[0].proposal_id} and len(host.proposals) == 1
    assert person.inbox == ["Barrel"] and host.bridge.drain_pending() == 0
    for _ in range(3):  # (status lookups: the same answer each time)
        status = tools.request_status("dup-1", root=str(root))
        assert status["state"] == "finished" and status["result"]["proposal_id"] == host.proposals[0].proposal_id


def test_a_request_id_reused_for_something_else_is_refused(root: Path, studio: Any) -> None:
    person, host = studio
    with _pumping(host):
        assert _post(host, "/live/stage_proposal", {"changes": BARREL, "title": "A"}, "same")["ok"] is True
        clash = _post(host, "/live/stage_proposal", {"changes": BARREL, "title": "B"}, "same")
        withdraw = _post(host, "/live/reject_proposal", {"proposal_id": host.proposals[0].proposal_id}, "same")
    assert clash["reason"] == "request_id_conflict" and withdraw["reason"] == "request_id_conflict"
    assert person.inbox == ["A"] and [p.status for p in host.proposals] == ["pending"]


def test_a_cancelled_request_sent_again_stays_cancelled(root: Path, studio: Any) -> None:
    person, host = studio
    host.bridge.request_timeout = 0.2
    payload = {"changes": BARREL, "title": "Barrel"}
    assert _post(host, "/live/stage_proposal", payload, "late-1")["request_state"] == "cancelled"
    again = _post(host, "/live/stage_proposal", payload, "late-1")
    assert again["reason"] == "timeout" and again["request_state"] == "cancelled"
    assert host.bridge.drain_pending() == 0 and host.proposals == [] and person.inbox == []


def test_request_ids_and_status_lookups_that_dont_fit(root: Path, studio: Any) -> None:
    _, host = studio
    with pytest.raises(error.HTTPError) as caught:
        _post(host, "/live/stage_proposal", {"changes": BARREL}, "not an id!")
    assert caught.value.code == 400
    caught.value.close()
    assert host.bridge.pending_count() == 0
    missing = tools.request_status("never-sent", root=str(root))
    assert missing["ok"] is False and missing["reason"] == "request_not_found"


# --------------------------------------------------------------------- the client: deadlines and lost answers

def test_the_legacy_clients_short_wait_gets_a_definite_answer_before_it_gives_up(root: Path, studio: Any) -> None:
    person, host = studio  # (bridge: 5 s, as shipped; the live_* client waits 2 s and says how long, X-Mesh-Wait)
    answer = live_session_client.live_stage_proposal(BARREL, root=root)
    host.bridge.drain_pending()
    assert host.proposals == [] and person.inbox == []  # (was: "forward_failed" at 2 s, then staged here)
    assert answer["reason"] == "timeout" and answer["request_state"] == "cancelled"


def test_a_lost_answer_is_unknown_and_request_status_reconciles_it(root: Path, studio: Any,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    person, host = studio
    host.bridge.request_timeout = 30.0
    monkeypatch.setattr(live_session_bridge, "_seconds", lambda _value: None)  # (the editor ignores the client's wait)
    answer = authoring_session._call(_info(host), "POST", "/live/stage_proposal", {"changes": BARREL, "title": "B"},
                                     timeout=0.3)  # (the client stops listening first: a real socket timeout)
    assert answer["ok"] is False and answer["reason"] == "outcome_unknown" and answer["request_id"]
    assert tools.request_status(answer["request_id"], root=str(root))["state"] == "queued"
    assert host.bridge.drain_pending() == 1  # (it was still waiting for the main thread: it runs, once)
    status = tools.request_status(answer["request_id"], root=str(root))
    assert status["state"] == "finished" and person.inbox == ["B"]
    assert [p.proposal_id for p in host.proposals] == [status["result"]["proposal_id"]]


def _hang_up_after_sending(info: dict[str, Any], path: str, payload: dict[str, Any], request_id: str,
                           wait: float) -> None:
    body = json.dumps(payload).encode("utf-8")
    head = (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {info['token']}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\nX-Mesh-Request-Id: {request_id}\r\n"
            f"X-Mesh-Wait: {wait}\r\n\r\n").encode("ascii")
    with socket.create_connection((info["host"], info["port"]), timeout=WAIT) as conn:
        conn.sendall(head + body)


@pytest.mark.parametrize("drained_in_time", [False, True], ids=["deadline first", "drained first"])
def test_a_client_that_hangs_up_gets_the_same_outcome(root: Path, studio: Any, drained_in_time: bool) -> None:
    person, host = studio
    documents, revision = person.project.all_documents(), person.project.revision
    _hang_up_after_sending(_info(host), "/live/stage_proposal", {"changes": BARREL, "title": "Gone"}, "gone-1",
                           wait=0.3 if not drained_in_time else 30.0)
    _until(lambda: host.bridge.request_status("gone-1")["ok"])
    if drained_in_time:
        _until(lambda: host.bridge.pending_count() == 1)
        assert host.bridge.drain_pending() == 1
        assert host.bridge.request_status("gone-1")["state"] == "finished" and person.inbox == ["Gone"]
    else:
        _until(lambda: host.bridge.request_status("gone-1")["state"] == "cancelled")
        assert host.bridge.drain_pending() == 0 and person.inbox == []
        _unchanged(person, documents, revision)


# --------------------------------------------------------------------- stopping the editor

def test_stopping_wakes_waiters_cancels_only_what_hadnt_started(root: Path, studio: Any) -> None:
    person, host = studio
    bridge = host.bridge
    bridge.request_timeout = 30.0
    entered, release = threading.Event(), threading.Event()
    ran: list[str] = []

    def started_work() -> dict[str, Any]:
        entered.set()
        assert release.wait(WAIT)
        ran.append("started")
        return {"ok": True, "done": True}

    running, running_out = _in_thread(lambda: bridge._enqueue(started_work, request_id="run-1", fingerprint="f",
                                                              wait=0.5))
    _until(lambda: bridge.pending_count() == 1)
    drainer, _ = _in_thread(bridge.drain_pending, name="drain")
    assert entered.wait(WAIT)
    queued, queued_out = _in_thread(lambda: authoring_session.propose(root, BARREL, title="Queued"))
    _until(lambda: bridge.pending_count() == 1)
    stopper, _ = _in_thread(host.stop, name="stopper")  # (from Studio's closing; must not wait for the running work)
    stopper.join(WAIT)
    assert not stopper.is_alive()
    queued.join(WAIT)
    assert queued_out[0]["reason"] == "editor_stopped" and queued_out[0]["request_state"] == "cancelled"
    running.join(WAIT)
    assert running_out[0]["reason"] == "outcome_unknown" and running_out[0]["request_state"] == "started"
    release.set()
    drainer.join(WAIT)
    assert ran == ["started"] and bridge.request_status("run-1")["state"] == "finished"
    assert bridge.drain_pending() == 0 and host.proposals == [] and person.inbox == []
    late = bridge._enqueue(lambda: {"ok": True}, request_id="after", fingerprint="f")  # (a handler still running)
    assert late["reason"] == "editor_stopped" and bridge.drain_pending() == 0


@pytest.mark.parametrize("first", ["stop", "drain"])
def test_stopping_as_the_drain_takes_a_request_either_cancels_it_or_lets_it_finish(
        root: Path, studio: Any, monkeypatch: pytest.MonkeyPatch, first: str) -> None:
    """The main thread is taking a request as Studio closes: stop first, it never runs (it used to run after stop,
    taken off the queue before the lock where stop couldn't see it); drain first, it runs and is never called
    cancelled."""
    person, host = studio
    bridge = host.bridge
    bridge.request_timeout = 30.0
    documents, revision = person.project.all_documents(), person.project.revision
    gate = _GateLock()
    monkeypatch.setattr(bridge, "_lock", gate)
    # (drain's 1st take: about to take the request and start it; its 2nd: about to end it, having run it)
    drain_at_lock, drain_go = gate.at("drain", 1 if first == "stop" else 2)
    waiter, out = _in_thread(lambda: authoring_session.propose(root, BARREL, title="Barrel", request_id="race-1"))
    _until(lambda: bridge.pending_count() == 1)
    drainer, drained = _in_thread(bridge.drain_pending, name="drain")
    assert drain_at_lock.wait(WAIT)
    stopper, _ = _in_thread(host.stop, name="stopper")
    stopper.join(WAIT)
    assert not stopper.is_alive()  # (never waits for the drain)
    if first == "drain":
        assert bridge.request_status("race-1")["state"] == "started"  # (stopping didn't call it cancelled)
    drain_go.set()
    drainer.join(WAIT)
    waiter.join(WAIT)
    status = bridge.request_status("race-1")
    if first == "stop":
        assert drained == [0] and host.proposals == [] and person.inbox == []  # never ran, not even after stop
        _unchanged(person, documents, revision)
        assert out[0]["reason"] == "editor_stopped" and out[0]["request_state"] == "cancelled"  # woken by stop
        assert status["state"] == "cancelled" and status["result"]["reason"] == "editor_stopped"
    else:
        assert drained == [1] and person.inbox == ["Barrel"]
        assert [p.proposal_id for p in host.proposals] == [out[0]["proposal_id"]]
        assert out[0]["ok"] is True and out[0]["request_state"] == "finished" and status["state"] == "finished"


# --------------------------------------------------------------------- what a timeout or retry may never bypass

def test_timeouts_and_retries_never_let_an_outside_tool_accept(root: Path, studio: Any) -> None:
    person, host = studio
    with _pumping(host):
        proposal_id = authoring_session.propose(root, BARREL, title="Barrel")["proposal_id"]
    documents, revision = person.project.all_documents(), person.project.revision
    host.bridge.request_timeout = 0.2
    assert _post(host, "/live/accept_proposal", {"proposal_id": proposal_id}, "acc-1")["reason"] == "timeout"
    assert host.bridge.drain_pending() == 0
    host.bridge.request_timeout = 30.0
    with _pumping(host):
        for request_id in ("acc-2", "acc-2", "acc-3"):
            assert _post(host, "/live/accept_proposal", {"proposal_id": proposal_id}, request_id)["reason"] == \
                "needs_person"
    assert [p.status for p in host.proposals] == ["pending"]
    _unchanged(person, documents, revision)


def test_timeouts_and_retries_never_let_an_ai_play_without_permission(root: Path, studio: Any) -> None:
    person, host = studio
    host.playtest_control = False
    host.bridge.request_timeout = 0.2
    assert runtime_debug.request_play(root)["reason"] == "timeout"
    assert runtime_play.request_action(root, {"action": "interact"})["reason"] == "timeout"
    host.bridge.request_timeout = 30.0
    with _pumping(host):
        assert runtime_debug.request_play(root)["reason"] == "playtest_control_off"
        assert runtime_play.request_action(root, {"action": "interact"})["reason"] == "gameplay_control_off"
    assert person.plays == 0 and host.play.running is None


# --------------------------------------------------------------------- memory: bounded, never losing live work

def test_ended_requests_are_forgotten_by_count_and_age_but_live_ones_are_kept(root: Path, studio: Any,
                                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _, host = studio
    bridge = host.bridge
    monkeypatch.setattr(live_session_bridge, "REQUESTS_KEPT", 3)
    with _pumping(host):
        for n in range(5):
            assert _post(host, "/live/reject_proposal", {"proposal_id": "none"}, f"old-{n}")["request_state"] == \
                "finished"
    assert [bridge.request_status(f"old-{n}")["ok"] for n in range(5)] == [False, False, True, True, True]
    bridge.request_timeout = 30.0
    waiting, _ = _in_thread(lambda: _post(host, "/live/reject_proposal", {"proposal_id": "none"}, "live-1"))
    _until(lambda: bridge.pending_count() == 1)
    monkeypatch.setattr(live_session_bridge, "REQUESTS_KEPT_SECONDS", -1.0)  # (any age)
    assert bridge.request_status("old-4")["reason"] == "request_not_found"  # (aged out)
    assert bridge.request_status("live-1")["state"] == "queued" and list(bridge._requests) == ["live-1"]
    assert bridge.drain_pending() == 1
    waiting.join(WAIT)


# --------------------------------------------------------------------- review follow-ups

def test_an_mcp_retry_with_the_same_request_id_is_done_once(root: Path, studio: Any) -> None:
    person, host = studio
    with _pumping(host):
        first = tools.propose_changes(BARREL, title="Barrel", root=str(root), request_id="ai-try-1")
        again = tools.propose_changes(BARREL, title="Barrel", root=str(root), request_id="ai-try-1")
        both = [live_session_client.live_stage_and_accept_add_entity(BARREL[0], root=root, request_id="legacy-1")
                for _ in range(2)]  # (legacy: stage, then accept or withdraw; each step repeated by its derived id)
        withdrawn = [tools.withdraw_proposal(first["proposal_id"], root=str(root), request_id="wd-1") for _ in range(2)]
    assert first["proposal_id"] == again["proposal_id"] and first["request_id"] == "ai-try-1"
    assert both[0] == both[1] and both[0]["proposal_id"] == host.proposals[1].proposal_id
    assert person.inbox == ["Barrel", "Changes from an AI"] and len(host.proposals) == 2
    assert withdrawn[0] == withdrawn[1] and host.proposals[0].status == "rejected"
    bad = tools.propose_changes(BARREL, root=str(root), request_id="not an id!")
    assert bad["reason"] == "invalid_request_id" and len(host.proposals) == 2


def test_an_mcp_retry_after_outcome_unknown_never_stages_twice(root: Path, studio: Any) -> None:
    person, host = studio
    host.bridge.request_timeout = 0.2
    entered, release = threading.Event(), threading.Event()
    real = authoring.dry_run

    def slow(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(WAIT)
        return real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(authoring, "dry_run", slow)
        drainer, _ = _in_thread(lambda: (_until(lambda: host.bridge.pending_count() == 1), host.bridge.drain_pending()),
                                name="drain")
        unknown = tools.propose_changes(BARREL, title="Slow", root=str(root), request_id="ai-slow")
        assert entered.wait(WAIT) and unknown["reason"] == "outcome_unknown"
        retry = tools.propose_changes(BARREL, title="Slow", root=str(root), request_id="ai-slow")  # (the AI retries)
        assert retry["reason"] == "outcome_unknown"
        release.set()
        drainer.join(WAIT)
    final = tools.propose_changes(BARREL, title="Slow", root=str(root), request_id="ai-slow")
    assert final["ok"] is True and person.inbox == ["Slow"] and len(host.proposals) == 1


def test_ended_requests_let_go_of_their_work(root: Path, studio: Any) -> None:
    _, host = studio
    bridge = host.bridge
    bridge.request_timeout = 0.1
    assert _post(host, "/live/stage_proposal", {"changes": BARREL}, "freed-1")["request_state"] == "cancelled"
    assert bridge._requests["freed-1"].func is None and [job.func for job in bridge._work.queue] == [None]
    with _pumping(host):
        bridge.request_timeout = 30.0
        assert _post(host, "/live/stage_proposal", {"changes": BARREL}, "freed-2")["ok"] is True
    assert bridge._requests["freed-2"].func is None


def test_a_repeat_waiting_less_long_doesnt_cut_the_first_senders_wait_short(root: Path, studio: Any) -> None:
    person, host = studio
    bridge = host.bridge
    payload = {"changes": BARREL, "title": "Patient"}
    first, out = _in_thread(lambda: _post(host, "/live/stage_proposal", payload, "patient-1"))  # (waits 4.5 s)
    _until(lambda: bridge.pending_count() == 1)
    hasty = _post(host, "/live/stage_proposal", payload, "patient-1", timeout=0.2)  # (waits 0.15 s)
    assert hasty["reason"] == "outcome_unknown" and hasty["request_state"] == "queued"
    assert bridge.pending_count() == 1 and bridge.drain_pending() == 1
    first.join(WAIT)
    assert out[0]["ok"] is True and person.inbox == ["Patient"]


def test_cancelled_requests_dont_use_up_the_drain_limit(root: Path, studio: Any) -> None:
    _, host = studio
    bridge = host.bridge
    ran: list[int] = []
    for n in range(60):
        bridge._enqueue(lambda: {"ok": True}, request_id=f"dead-{n}", fingerprint="f", wait=0.001)
    live, out = _in_thread(lambda: bridge._enqueue(lambda: ran.append(1) or {"ok": True}, request_id="alive",
                                                   fingerprint="f", wait=30.0))
    _until(lambda: bridge.pending_count() == 1)
    assert bridge.drain_pending(limit=50) == 1 and ran == [1]
    live.join(WAIT)
    assert out[0]["request_state"] == "finished"


def test_status_ids_are_never_cut_short_and_an_interrupted_request_still_ends(root: Path, studio: Any) -> None:
    _, host = studio
    bridge = host.bridge
    with _pumping(host):
        assert _post(host, "/live/reject_proposal", {"proposal_id": "x"}, "a" * 64)["request_state"] == "finished"
    assert tools.request_status("a" * 64 + "ZZZ", root=str(root))["reason"] == "request_not_found"

    def interrupted() -> dict[str, Any]:
        raise SystemExit(1)

    waiter, out = _in_thread(lambda: bridge._enqueue(interrupted, request_id="cut-1", fingerprint="f", wait=30.0))
    _until(lambda: bridge.pending_count() == 1)
    with pytest.raises(SystemExit):
        bridge.drain_pending()
    waiter.join(WAIT)
    assert out[0]["reason"] == "interrupted" and bridge.request_status("cut-1")["state"] == "finished"


class _LegacyEditor:
    """The legacy editor's bridge host: its accept applies the change (counted), here only once ``release`` is set."""

    host_kind = "legacy_editor"

    def __init__(self) -> None:
        self.applied = 0
        self.entered, self.release = threading.Event(), threading.Event()

    def stage_proposal(self, ops: list[dict[str, Any]]) -> Any:
        return SimpleNamespace(proposal_id="", ops=ops, base_revision=0, preview_summary="add", dry_run={"ok": True})

    def accept_proposal(self, _proposal: Any) -> dict[str, Any]:
        self.applied += 1
        self.entered.set()
        assert self.release.wait(WAIT)
        return {"ok": True}

    def reject_proposal(self, _proposal: Any) -> dict[str, Any]:
        return {"ok": True}


@pytest.mark.parametrize("given", ["ai-call-1", ""], ids=["caller's id", "no id given"])
def test_retrying_the_legacy_add_with_the_id_it_answered_adds_once(tmp_path: Path, given: str) -> None:
    editor = _LegacyEditor()
    bridge = live_session_bridge.EditorLiveSessionBridge(editor, tmp_path)
    bridge.start()
    stop = threading.Event()

    def drain() -> None:  # (the legacy editor's update)
        while not stop.is_set():
            bridge.drain_pending()
            stop.wait(0.005)

    pump = threading.Thread(target=drain, name="drain", daemon=True)
    pump.start()
    try:
        first = tools.live_add_entity_from_prefab("person", 1, 1, root=str(tmp_path), request_id=given)
        assert editor.entered.is_set() and first["reason"] == "outcome_unknown"  # (accept outlasts the 1.5 s wait)
        assert first["request_id"] == (given or first["request_id"]) and first["step_request_id"] != first["request_id"]
        assert bridge.request_status(first["step_request_id"])["state"] == "started"
        editor.release.set()
        _until(lambda: bridge.request_status(first["step_request_id"])["state"] == "finished")
        again = tools.live_add_entity_from_prefab("person", 1, 1, root=str(tmp_path), request_id=first["request_id"])
        assert again["ok"] is True and editor.applied == 1  # (was: added a second time)
    finally:
        editor.release.set()
        stop.set()
        pump.join(WAIT)
        bridge.stop()


def test_a_legacy_add_whose_accept_was_cancelled_says_whether_its_proposal_was_withdrawn(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _LegacyEditor()
    bridge = live_session_bridge.EditorLiveSessionBridge(editor, tmp_path)
    bridge.start()
    staged = threading.Event()
    real_stage = bridge._stage_proposal

    def stage_then_freeze(payload: dict[str, Any]) -> dict[str, Any]:  # (the editor freezes right after staging)
        result = real_stage(payload)
        staged.set()
        return result

    monkeypatch.setattr(bridge, "_stage_proposal", stage_then_freeze)
    drainer, _ = _in_thread(lambda: (_until(lambda: bridge.pending_count() == 1), bridge.drain_pending(limit=1)),
                            name="drain")
    try:
        answer = live_session_client.live_stage_and_accept_add_entity({"type": "add"}, root=tmp_path,
                                                                      request_id="frozen-1")
        assert staged.is_set() and answer["reason"] == "timeout" and answer["request_state"] == "cancelled"
        assert answer["withdrawn"] is False and answer["proposal_id"] in answer["message"]
        assert editor.applied == 0 and list(bridge._proposals) == [answer["proposal_id"]]  # (said, not hidden)
    finally:
        drainer.join(WAIT)
        bridge.stop()
