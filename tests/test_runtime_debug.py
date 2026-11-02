"""D1 (#422): an AI reads the game running in a Mesh Studio play-test, and starts and stops play-tests once the person
allows it. ``engine.runtime_debug`` reads the running game's own objects (flags, quests, events, the player); this
checks what it reports, that it reports a missing system as unavailable, that reading changes nothing, that every
answer is bounded plain JSON, and the way in: MCP tool -> verified live session -> Studio's main-thread queue, with
the refusals for no Studio, an untrustworthy session record, a mismatched session, a wrong token and a Studio that
doesn't answer in time. A play-test in a real window is tests/test_runtime_debugger_gpu.py.
"""

from __future__ import annotations

import copy
import json
import math
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib import error, request

import pytest

from engine import authoring, runtime_debug, swallowed_exceptions
from engine.editor.live_session_bridge import EditorLiveSessionBridge, _count, read_live_session_file, session_file_path
from engine.events import MeshEventBus
from engine.game_state_controller import GameState
from engine.mcp_server import live_session_client, tools
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (loopback bridges and project files, like the other live-session tests)
ROOM = "packs/core_regions/scenes/start.json"
QUESTS = {"help": {"id": "help", "title": "Help the Guide",
                   "stages": [{"id": "agree", "title": "Agree"}, {"id": "cellar", "title": "The cellar"}]},
          "later": {"id": "later", "title": "Later", "stages": [{"id": "one", "title": "One"}]}}


class _Sprite:
    def __init__(self, name: str, x: float, y: float) -> None:
        self.mesh_id, self.mesh_name, self.mesh_tag = f"{name.lower()}_1", name, name.lower()
        self.center_x, self.center_y = x, y


def _window(root: Path, *, player: Any = True) -> SimpleNamespace:
    """A running game as runtime_debug sees it: the same attributes GameWindow has."""
    state = GameState()
    sprite = _Sprite("Player", 128.0, 96.0) if player is True else player
    return SimpleNamespace(
        scene_controller=SimpleNamespace(current_scene_path=str(root / ROOM), _find_player_sprite=lambda: sprite),
        game_state_controller=SimpleNamespace(state=state),
        quest_manager=SimpleNamespace(_definitions=copy.deepcopy(QUESTS)),
        event_bus=MeshEventBus())


class _Studio:
    """What StudioAIHost and runtime_debug need from Mesh Studio, without a window."""

    def __init__(self, root: Path, window: Any = None) -> None:
        self.project = Project.open(root, "packs/core_regions/worlds/main.json")
        self.window = window if window is not None else _window(root)
        self.mode, self.playtest, self.last_playtest = "edit", None, None
        self.calls: list[str] = []
        self.ai = StudioAIHost(self)

    def begin(self) -> None:  # what Studio.play records (Studio._note_playtest)
        self.mode = "play"
        self.playtest = {"id": "abc", "number": 1, "started_at": time.time() - 1, "started_by": "person",
                         "events_before": self.window.event_bus.emitted,
                         "caught_before": swallowed_exceptions.read_counts()}

    def ai_start_playtest(self) -> dict[str, Any]:
        self.calls.append("start")
        if self.mode == "play":
            return {"ok": True, "status": "already_playing"}
        self.begin()
        return {"ok": True, "status": "playing"}

    def ai_stop_playtest(self) -> dict[str, Any]:
        self.calls.append("stop")
        if self.mode != "play":
            return {"ok": True, "status": "not_playing"}
        self.mode, self.last_playtest, self.playtest = "edit", self.playtest, None
        return {"ok": True, "status": "stopped"}

    def on_ai_proposal(self, proposal: Any) -> None:
        self.calls.append("proposal")

    def on_ai_decided(self, proposal: Any) -> None:
        self.calls.append(proposal.status)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studio(root: Path) -> _Studio:
    return _Studio(root)


@pytest.fixture
def live(studio: _Studio) -> Iterator[_Studio]:
    """``studio`` with its live session running and its queue drained on another thread (as Studio's on_update)."""
    studio.ai.start()
    stop = threading.Event()

    def pump() -> None:
        while not stop.is_set():
            studio.ai.drain()
            time.sleep(0.005)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    yield studio
    stop.set()
    thread.join(timeout=2)
    studio.ai.stop()


def _snap(studio: _Studio, events: int = 20) -> dict[str, Any]:
    out = studio.ai.debug_snapshot(events)
    json.dumps(out, allow_nan=False)  # (plain JSON, always)
    return out


# --------------------------------------------------------------------- what a snapshot says

def test_while_editing_it_says_not_playing_and_reads_no_game(studio: _Studio) -> None:
    out = _snap(studio)
    assert out["ok"] and out["status"] == "not_playing" and out["sequence"] == 1
    assert out["studio"] == {"mode": "editing", "edited_room": studio.project.current, "unsaved_changes": False,
                             "revision": studio.project.revision, "ai_playtest_control": False}
    assert not {"scene", "player", "game_state", "quests", "events"} & set(out) and out["last_playtest"] is None
    assert "Play (F4)" in out["message"]
    assert _snap(studio)["sequence"] == 2  # (each read counted)


def test_while_playing_it_reads_the_running_game(studio: _Studio) -> None:
    window = studio.window
    window.event_bus.emit("scene_loaded", scene_id="before")  # (an earlier play-test's: not this one's)
    studio.begin()
    window.game_state_controller.state.flags.update(agreed=True, door_open=False)
    window.game_state_controller.state.counters["coins"] = 3.0
    window.game_state_controller.state.values.update(gold=7, quests={"help": {
        "status": "active", "current_stage": "cellar", "awaiting_stage": None, "completed_stages": ["agree"]}})
    window.event_bus.emit("dialogue_choice", entity="Guide", choice_id="help", actor=_Sprite("Guide", 1, 2))
    window.event_bus.emit("quest_stage_completed", quest_id="help", stage_id="agree")
    out = _snap(studio)
    assert out["status"] == "playing" and out["playtest"]["id"] == "abc" and out["studio"]["mode"] == "playing"
    assert out["scene"] == {"available": True, "path": ROOM, "room": {"key": studio.project.current,
                                                                       "label": studio.project.label(studio.project.current)}}
    assert out["player"] == {"available": True, "id": "player_1", "name": "Player", "tag": "player", "x": 128.0,
                             "y": 96.0, "units": "pixels"}
    state = out["game_state"]
    assert state["flags"] == {"agreed": True, "door_open": False} and state["counters"] == {"coins": 3.0}
    assert state["values"] == {"gold": 7} and "variables" not in state  # (one mapping; quests under "quests")
    assert out["quests"]["quests"] == [
        {"id": "help", "title": "Help the Guide", "auto_start": False, "status": "active", "current_stage": "cellar", "awaiting_stage": None,
         "completed_stages": ["agree"], "total_stages": 2},
        {"id": "later", "title": "Later", "auto_start": False, "status": "inactive", "current_stage": None, "awaiting_stage": None,
         "completed_stages": [], "total_stages": 1}]
    events = out["events"]
    assert [(e["seq"], e["type"], e["entity"]) for e in events["items"]] == [(2, "dialogue_choice", "Guide"),
                                                                            (3, "quest_stage_completed", None)]
    assert events["items"][0]["payload"]["actor"] == {"entity": "Guide"}  # (an object named, never written out)
    assert events["made_this_playtest"] == 2 and events["no_longer_kept"] == 0 and events["last_seq"] == 3


def test_events_are_bounded_numbered_in_order_and_say_what_was_dropped(studio: _Studio) -> None:
    studio.begin()
    for i in range(70):  # (the game's bus keeps its last 50)
        studio.window.event_bus.emit("tick", n=i)
    events = _snap(studio, events=10)["events"]
    assert [e["payload"]["n"] for e in events["items"]] == list(range(60, 70)) and events["limit"] == 10
    assert [e["seq"] for e in events["items"]] == list(range(61, 71))
    assert events["made_this_playtest"] == 70 and events["no_longer_kept"] == 20
    assert _snap(studio, events=500)["events"]["limit"] == 50 and _snap(studio, events=0)["events"]["items"] == []


def test_a_missing_system_is_reported_unavailable_not_empty(root: Path) -> None:
    bare = _Studio(root, SimpleNamespace())
    bare.mode, bare.playtest = "play", {"id": "x", "started_at": time.time()}
    out = _snap(bare)
    for part in ("scene", "player", "game_state", "quests", "events"):
        assert out[part]["available"] is False and out[part]["reason"], part
    nobody = _Studio(root, _window(root, player=None))
    nobody.begin()
    assert _snap(nobody)["player"] == {"available": False, "reason": "the running room has no player"}


def test_reading_changes_nothing_in_the_running_game(studio: _Studio) -> None:
    studio.begin()
    window = studio.window
    window.game_state_controller.state.flags["agreed"] = True
    window.event_bus.emit("dialogue_choice", entity="Guide")
    queue = [object()]  # (the events waiting for the game's next update)
    window._mesh_event_queue = queue
    before = (copy.deepcopy(window.game_state_controller.state), copy.deepcopy(window.event_bus._history),
              window.event_bus.emitted, copy.deepcopy(window.quest_manager._definitions))
    for _ in range(3):
        _snap(studio)
    after = (window.game_state_controller.state, window.event_bus._history, window.event_bus.emitted,
             window.quest_manager._definitions)
    assert before == after and window._mesh_event_queue is queue and len(queue) == 1
    assert "quests" not in window.game_state_controller.state.values  # (no quest record made by reading)
    assert studio.project.is_dirty is False and studio.project.revision == 0


def test_errors_the_engine_caught_during_the_play_test_are_listed(studio: _Studio) -> None:
    swallowed_exceptions.record_swallowed("D1-test-before", ValueError("old"))
    studio.begin()
    for _ in range(2):
        swallowed_exceptions.record_swallowed("D1-test-during", ValueError("x"))
    items = _snap(studio)["diagnostics"]["items"]
    during = [i for i in items if i["site"] == "D1-test-during"]
    assert during and during[0]["count"] == 2 and during[0]["kind"] == "caught_exception"
    assert not [i for i in items if i["site"] == "D1-test-before"]


def test_values_are_bounded_plain_json(studio: _Studio) -> None:
    deep: dict[str, Any] = {"x": 1}
    for _ in range(10):
        deep = {"in": deep}
    odd = {"nan": math.nan, "inf": -math.inf, "set": {3, 1, 2}, "obj": object(), "long": "w" * 5000,
           "many": list(range(1000)), "deep": deep, 7: "int key"}
    out = runtime_debug.plain(odd)
    json.dumps(out, allow_nan=False)
    assert out["nan"] == "nan" and out["inf"] == "-inf" and out["set"] == [1, 2, 3] and out["obj"] == "<object>"
    assert len(out["long"]) == runtime_debug.TEXT_MAX + 3 and out["many"][-1] == "... 900 more"
    assert out["7"] == "int key" and "..." in json.dumps(out["deep"])
    studio.begin()
    studio.window.game_state_controller.state.flags.update({f"f{i:04}": True for i in range(1000)})
    for i in range(50):
        studio.window.event_bus.emit("big", blob=["x" * 199] * 100, n=i)
    snap = _snap(studio, events=50)
    assert len(snap["game_state"]["flags"]) == runtime_debug.FLAGS_MAX + 1  # (and "...": how many more)
    assert len(json.dumps(snap)) <= runtime_debug.BYTES_MAX and snap["truncated"] is True


def test_the_count_of_events_asked_for_is_bounded() -> None:
    assert [_count(v) for v in ("5", "0", "-3", "999", "x", "")] == [5, 0, 0, 50, 20, 20]


# --------------------------------------------------------------------- play-test control: the person allows it

def test_play_and_stop_are_refused_until_the_person_allows_them(studio: _Studio) -> None:
    for answer in (studio.ai.debug_start_playtest(), studio.ai.debug_stop_playtest()):
        assert answer["ok"] is False and answer["reason"] == "playtest_control_off" and "top bar: AI" in answer["message"]
    assert studio.calls == [] and studio.mode == "edit"
    studio.ai.playtest_control = True
    assert [studio.ai.debug_start_playtest()["status"], studio.ai.debug_start_playtest()["status"]] == [
        "playing", "already_playing"]
    assert [studio.ai.debug_stop_playtest()["status"], studio.ai.debug_stop_playtest()["status"]] == [
        "stopped", "not_playing"]
    assert StudioAIHost(studio).playtest_control is False  # (a new Studio session: off again)


# --------------------------------------------------------------------- the way in, and its refusals

def test_the_mcp_tools_reach_studio_through_its_live_session(root: Path, live: _Studio) -> None:
    assert tools.debug_runtime_snapshot(root=str(root))["status"] == "not_playing"
    assert tools.debug_start_playtest(root=str(root))["reason"] == "playtest_control_off"
    live.ai.playtest_control = True
    assert tools.debug_start_playtest(root=str(root))["status"] == "playing"
    snap = tools.debug_runtime_snapshot(events=5, root=str(root))
    assert snap["status"] == "playing" and snap["scene"]["path"] == ROOM and snap["events"]["limit"] == 5
    assert "token" not in json.dumps(snap) and str(root) not in json.dumps(snap)
    # The authoring safeguards are untouched: a change proposed while playing waits for the person (F1, F6).
    proposed = tools.propose_changes([{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64}], root=str(root))
    assert proposed["ok"] and tools.live_accept_proposal(proposed["proposal_id"], root=str(root))["reason"] == "needs_person"
    assert live.project.revision == 0
    assert tools.debug_stop_playtest(root=str(root))["status"] == "stopped"
    assert tools.debug_runtime_snapshot(root=str(root))["status"] == "not_playing"
    assert live.calls == ["start", "proposal", "stop"]


def test_with_no_studio_the_tools_refuse_as_the_other_live_tools_do(root: Path) -> None:
    for answer in (tools.debug_runtime_snapshot(root=str(root)), tools.debug_start_playtest(root=str(root)),
                   tools.debug_stop_playtest(root=str(root))):
        assert answer["ok"] is False and answer["reason"] == "studio_not_open"


def test_a_studio_that_closed_leaves_no_session_to_ask(root: Path, studio: _Studio) -> None:
    studio.ai.start()
    studio.ai.stop()
    assert read_live_session_file(root) is None
    assert tools.debug_runtime_snapshot(root=str(root))["reason"] == "studio_not_open"


def test_a_stale_session_record_is_refused_not_trusted(root: Path, studio: _Studio) -> None:
    studio.ai.start()
    record = session_file_path(root).read_text(encoding="utf-8")
    studio.ai.stop()  # (it closed without its record being removed: a crash)
    session_file_path(root).write_text(record, encoding="utf-8")
    answer = tools.debug_runtime_snapshot(root=str(root))
    assert answer["reason"] == "studio_session_uncertain" and answer["problem"] == "unverified_live_session"


def test_another_session_answering_is_refused(root: Path, live: _Studio, monkeypatch: pytest.MonkeyPatch) -> None:
    real = live_session_client._request_json

    def request_json(info: dict[str, Any], method: str, path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        answer = real(info, method, path, *args, **kwargs)
        return {**answer, "session_id": "another"} if path == "/health" else answer

    monkeypatch.setattr(live_session_client, "_request_json", request_json)
    assert tools.debug_runtime_snapshot(root=str(root))["problem"] == "session_mismatch"
    live.ai.playtest_control = True
    assert tools.debug_start_playtest(root=str(root))["reason"] == "studio_session_uncertain" and live.calls == []


def test_a_request_without_the_sessions_token_is_unauthorized(root: Path, live: _Studio) -> None:
    info = read_live_session_file(root)
    assert info is not None
    for method, path in (("GET", "/live/debug/snapshot"), ("POST", "/live/debug/play"), ("POST", "/live/debug/stop")):
        req = request.Request(f"http://127.0.0.1:{info['port']}{path}", data=b"{}" if method == "POST" else None,
                              method=method, headers={"Authorization": "Bearer wrong"})
        with pytest.raises(error.HTTPError) as caught:
            request.urlopen(req, timeout=2)  # noqa: S310 - loopback
        assert caught.value.code == 401
        caught.value.close()  # (its response's socket)
    assert live.calls == [] and live.mode == "edit"


def test_a_studio_that_doesnt_answer_in_time_times_out(root: Path, studio: _Studio) -> None:
    studio.ai.start()  # (nothing drains its queue: Studio's main thread is busy)
    try:
        studio.ai.bridge.request_timeout = 0.2
        answer = tools.debug_runtime_snapshot(root=str(root))
        assert answer["ok"] is False and answer["reason"] == "timeout"
    finally:
        studio.ai.stop()


def test_an_editor_without_runtime_debugging_says_not_found(root: Path) -> None:
    editor = SimpleNamespace(window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM)))
    bridge = EditorLiveSessionBridge(editor, root)
    bridge.start(write_discovery=False)
    try:
        info = bridge.info.to_dict()
        for method, path in (("GET", "/live/debug/snapshot"), ("POST", "/live/debug/play")):
            with pytest.raises(error.HTTPError) as caught:
                live_session_client._request_json(info, method, path)
            assert caught.value.code == 404
            caught.value.close()
    finally:
        bridge.stop()


def test_starting_play_never_saves_or_changes_the_project(root: Path, live: _Studio) -> None:
    authoring.apply(live.project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64}])  # (unsaved work)
    on_disk = {p: p.read_bytes() for p in root.rglob("*.json") if ".mesh" not in p.parts}
    revision = live.project.revision
    live.ai.playtest_control = True
    tools.debug_start_playtest(root=str(root))
    tools.debug_runtime_snapshot(root=str(root))
    tools.debug_stop_playtest(root=str(root))
    assert live.project.is_dirty and live.project.revision == revision
    assert {p: p.read_bytes() for p in root.rglob("*.json") if ".mesh" not in p.parts} == on_disk
