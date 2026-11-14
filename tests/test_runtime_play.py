"""D2 (#422): an AI plays a Mesh Studio play-test with the player's own controls (``engine.runtime_play``).

Without a window: a game that records the key events it is sent and has a conversation box that answers to them, as
the real one does (move_up / move_down move the cursor, interact confirms). Checked: each action is refused with its
reason when it can't apply, and nothing is pressed then; a move holds its key for exactly its frames; a choice moves
the cursor and confirms only where it was meant to; an action is cancelled, its key let go, when the play-test stops,
the game pauses or the AI cancels it; the separate permission; and the way in from MCP over the live-session bridge,
including a 401 without the token and an action that outlasts the client's wait. The game itself, in a real window,
is tests/test_ai_playtest_gpu.py.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib import error, request

import pytest

from engine import runtime_play
from engine.editor.live_session_bridge import read_live_session_file
from engine.events import MeshEventBus
from engine.game_state_controller import GameState
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (loopback bridges and project files, like the other live-session tests)
UP, DOWN, LEFT, RIGHT, E = 1, 2, 3, 4, 5
BINDINGS = {"move_up": [UP], "move_down": [DOWN], "move_left": [LEFT], "move_right": [RIGHT], "interact": [E]}


class _Box:
    """The game's conversation box, as runtime_play reads it, answering to key presses as the real one does."""

    def __init__(self) -> None:
        self.open, self.choices, self.cursor, self.chosen = False, [], 0, []

    def is_active(self) -> bool:
        return self.open

    def get_current_entry(self) -> dict[str, Any]:
        return {"speaker": "Guide", "text": "Will you light it?"}

    def has_choices(self) -> bool:
        return self.open and bool(self.choices)

    def get_choices(self) -> list[dict[str, Any]]:
        return [dict(c) for c in self.choices]

    def get_choice_cursor(self) -> int:
        return self.cursor

    def key(self, key: int) -> None:
        if not self.open:
            return
        if self.choices and key in (UP, DOWN):
            step = 1 if key == DOWN else -1
            for _ in self.choices:  # (skipping choices that can't be made, as the real box does)
                self.cursor = (self.cursor + step) % len(self.choices)
                if not self.choices[self.cursor].get("disabled"):
                    break
        elif key == E:
            if self.choices:
                self.chosen.append(self.choices[self.cursor]["text"])
                self.choices = []
            else:
                self.open = False


class _Window:
    def __init__(self) -> None:
        self.box = _Box()
        self.down: set[int] = set()
        self.log: list[tuple[str, int]] = []
        self.paused = self.game_over = self.locked = False
        player = SimpleNamespace(center_x=100.0, center_y=50.0, mesh_name="Player", mesh_id="p", mesh_tag="player")
        self.player = player
        self.scene_controller = SimpleNamespace(current_scene_path="scenes/start.json",
                                                _find_player_sprite=lambda: player, all_sprites=[player])
        manager = SimpleNamespace(get_bindings=lambda: BINDINGS, get_keys_down=lambda: set(self.down))
        self.input_controller = SimpleNamespace(manager=manager, is_input_locked=lambda: self.locked)
        self.ui_controller = SimpleNamespace(dialogue_box=self.box)
        self.game_state_controller = SimpleNamespace(state=GameState())
        self.event_bus = MeshEventBus()

    def dispatch_event(self, name: str, key: int, _modifiers: int) -> None:
        self.log.append((name, key))
        if name == "on_key_press":
            self.down.add(key)
            self.box.key(key)
        else:
            self.down.discard(key)

    def update(self) -> None:
        """The game's update: the player walks while an arrow key is down."""
        step = {RIGHT: (5, 0), LEFT: (-5, 0), UP: (0, 5), DOWN: (0, -5)}
        for key in self.down:
            dx, dy = step.get(key, (0, 0))
            self.player.center_x += dx
            self.player.center_y += dy


class _Studio:
    def __init__(self, root: Path) -> None:
        self.project = Project.open(root, "packs/core_regions/worlds/main.json")
        self.window = _Window()
        self.mode, self.playtest, self.last_playtest = "play", {"id": "t", "started_at": time.time()}, None
        self.ai = StudioAIHost(self)
        self.ai.gameplay_control = True

    def frame(self, n: int = 1) -> None:
        """Studio's on_update, then the game's (as in Studio: the AI's keys first)."""
        for _ in range(n):
            self.ai.drain()
            if self.mode == "play":
                self.ai.play.tick()
            self.window.update()

    def on_ai_proposal(self, proposal: Any) -> None: ...
    def on_ai_decided(self, proposal: Any) -> None: ...


@pytest.fixture
def studio(tmp_path: Path) -> _Studio:
    create_project(tmp_path / "game", "Game", template_id="blank")
    return _Studio(tmp_path / "game")


def _until_done(studio: _Studio, started: dict[str, Any], limit: int = 400) -> dict[str, Any]:
    for _ in range(limit):
        status = studio.ai.debug_act_status(started["action_id"])
        if status["status"] != "running":
            return status
        studio.frame()
    raise AssertionError("still running")


# --------------------------------------------------------------------- refusals: nothing pressed

@pytest.mark.parametrize(("request_", "reason"), [
    ({"action": "jump"}, "invalid_action"),
    ({"action": "move", "direction": "north", "frames": 5}, "invalid_action"),
    ({"action": "move", "direction": "up", "frames": 0}, "invalid_action"),
    ({"action": "move", "direction": "up", "frames": 121}, "invalid_action"),
    ({"action": "move", "direction": "up", "frames": True}, "invalid_action"),
    ({"action": "move", "direction": "up", "frames": "5"}, "invalid_action"),
    ({"action": "advance"}, "no_dialogue"),
    ({"action": "choose", "choice": 0}, "no_choices"),
], ids=["unknown action", "unknown direction", "no frames", "too many frames", "a bool", "text", "nothing said",
        "no choices"])
def test_an_action_that_cant_apply_is_refused_and_presses_nothing(studio: _Studio, request_: dict[str, Any],
                                                                  reason: str) -> None:
    answer = studio.ai.debug_act(request_)
    assert answer["ok"] is False and answer["reason"] == reason and answer["message"]
    studio.frame(5)
    assert studio.window.log == [] and studio.ai.play.running is None


def test_what_is_on_screen_decides_what_can_be_done(studio: _Studio) -> None:
    box = studio.window.box
    box.open, box.choices = True, [{"text": "Yes"}, {"text": "No", "disabled": True}, {"text": "Later"}]
    assert studio.ai.debug_act({"action": "move", "direction": "up", "frames": 5})["reason"] == "dialogue_open"
    assert studio.ai.debug_act({"action": "interact"})["reason"] == "dialogue_open"
    assert studio.ai.debug_act({"action": "advance"})["reason"] == "choice_needed"
    for wanted in ("Maybe", 1, 7, True):  # (not there; can't be made now; no such number; not a choice)
        assert studio.ai.debug_act({"action": "choose", "choice": wanted})["reason"] == "choice_not_available"
    studio.mode = "edit"
    assert studio.ai.debug_act({"action": "interact"})["reason"] == "not_playing"
    studio.mode = "play"
    studio.window.paused = True
    assert studio.ai.debug_act({"action": "choose", "choice": 0})["reason"] == "game_paused"
    studio.window.paused, studio.window.locked = False, True
    assert studio.ai.debug_act({"action": "choose", "choice": 0})["reason"] == "input_locked"
    studio.window.locked = False
    studio.window.down.add(E)  # (the person is holding the key the action needs)
    assert studio.ai.debug_act({"action": "choose", "choice": 0})["reason"] == "person_using_controls"
    assert studio.window.log == []


def test_playing_needs_its_own_permission(studio: _Studio) -> None:
    studio.ai.gameplay_control, studio.ai.playtest_control = False, True  # (play-tests allowed; playing them, not)
    answer = studio.ai.debug_act({"action": "move", "direction": "up", "frames": 5})
    assert answer["reason"] == "gameplay_control_off" and "separate permission" in answer["message"]
    assert StudioAIHost(studio).gameplay_control is False  # (a new Studio session starts with it off)


# --------------------------------------------------------------------- running them

def test_a_move_holds_its_key_for_exactly_its_frames(studio: _Studio) -> None:
    started = studio.ai.debug_act({"action": "move", "direction": "right", "frames": 7})
    assert started["ok"] and started["status"] == "running"
    assert studio.ai.debug_act({"action": "interact"})["reason"] == "action_running"
    result = _until_done(studio, started)
    assert studio.window.log == [("on_key_press", RIGHT), ("on_key_release", RIGHT)]
    assert result["status"] == "done" and result["ok"] is True
    assert result["before"]["player"] == [100.0, 50.0] and result["after"]["player"] == [135.0, 50.0]  # (7 x 5 px)
    # (7 frames held, the settle frames, and the tick that saw it finish)
    assert result["frames"] == 7 + runtime_play.SETTLE_FRAMES + 1 and studio.window.down == set()


def _presses(studio: _Studio) -> list[int]:
    return [k for name, k in studio.window.log if name == "on_key_press"]


def test_a_choice_moves_the_cursor_then_confirms_where_it_was_meant(studio: _Studio) -> None:
    box = studio.window.box
    box.open, box.choices = True, [{"text": "Yes"}, {"text": "No"}, {"text": "Later"}, {"text": "Never"}]
    result = _until_done(studio, studio.ai.debug_act({"action": "choose", "choice": "Later"}))
    assert result["status"] == "done" and result["action"] == {"action": "choose", "choice": 2, "text": "Later"}
    assert [k for name, k in studio.window.log if name == "on_key_press"] == [DOWN, DOWN, E]
    assert box.chosen == ["Later"]


def test_an_available_choice_after_a_disabled_one_is_reached(studio: _Studio) -> None:
    """The game's cursor skips a choice that can't be made: one press, not two, reaches the one after it."""
    box = studio.window.box
    box.open, box.choices = True, [{"text": "Yes"}, {"text": "No", "disabled": True}, {"text": "Later"}]
    result = _until_done(studio, studio.ai.debug_act({"action": "choose", "choice": "Later"}))
    assert result["status"] == "done" and _presses(studio) == [DOWN, E] and box.chosen == ["Later"]


def test_the_cursor_goes_the_shorter_way_round(studio: _Studio) -> None:
    box = studio.window.box
    box.open, box.choices = True, [{"text": "A"}, {"text": "B"}, {"text": "C"}, {"text": "D"}]
    result = _until_done(studio, studio.ai.debug_act({"action": "choose", "choice": 3}))
    assert result["status"] == "done" and _presses(studio) == [UP, E] and box.chosen == ["D"]
    box.open, box.cursor, box.choices = True, 2, [{"text": "A"}, {"text": "B", "disabled": True}, {"text": "C"}]
    studio.window.log.clear()
    result = _until_done(studio, studio.ai.debug_act({"action": "choose", "choice": "A"}))
    assert result["status"] == "done" and _presses(studio) == [DOWN, E] and box.chosen == ["D", "A"]


@pytest.mark.parametrize("change", ["renamed", "made unavailable", "a choice put in front", "the cursor moved"])
def test_choices_that_change_before_confirming_confirm_nothing(studio: _Studio, change: str) -> None:
    box = studio.window.box
    box.open, box.choices = True, [{"text": "Yes"}, {"text": "No"}, {"text": "Later"}, {"text": "Never"}]
    started = studio.ai.debug_act({"action": "choose", "choice": "No"})  # (planned: one press down, then confirm)
    assert started["ok"]
    if change == "renamed":
        box.choices[1]["text"] = "Not now"
    elif change == "made unavailable":
        box.choices[1]["disabled"] = True
    elif change == "a choice put in front":
        box.choices.insert(0, {"text": "Wait"})
    else:
        box.cursor = 3  # (the person moved it)
    result = _until_done(studio, started)
    assert result["status"] == "cancelled" and "nothing was chosen" in result["message"]
    assert E not in _presses(studio) and box.chosen == []


def test_the_choice_under_the_cursor_is_checked_too(studio: _Studio) -> None:
    """No presses needed (the cursor is already there): it is still the asked-for choice, and still available."""
    box = studio.window.box
    box.open, box.choices = True, [{"text": "Yes"}, {"text": "No"}]
    started = studio.ai.debug_act({"action": "choose", "choice": "Yes"})
    box.choices[0]["disabled"] = True
    result = _until_done(studio, started)
    assert result["status"] == "cancelled" and "can no longer be chosen" in result["message"]
    assert _presses(studio) == [] and box.chosen == []


def test_a_cursor_that_lands_elsewhere_confirms_nothing(studio: _Studio) -> None:
    box = studio.window.box
    box.open, box.choices = True, [{"text": "Yes"}, {"text": "No"}, {"text": "Later"}]
    started = studio.ai.debug_act({"action": "choose", "choice": 1})
    box.choices[1]["disabled"] = True  # (it became unavailable after the request: the cursor skips it)
    result = _until_done(studio, started)
    assert result["status"] == "cancelled" and "nothing was chosen" in result["message"]
    assert E not in [k for _, k in studio.window.log] and box.chosen == []


@pytest.mark.parametrize("interruption", ["stopped", "paused", "cancelled", "revoked"])
def test_an_interrupted_action_lets_go_of_its_key(studio: _Studio, interruption: str) -> None:
    started = studio.ai.debug_act({"action": "move", "direction": "up", "frames": 100})
    studio.frame(10)
    assert studio.window.down == {UP}
    if interruption == "stopped":
        studio.mode = "edit"  # (Studio.stop also cancels at once; the next tick would anyway)
    elif interruption == "paused":
        studio.window.paused = True
    elif interruption == "cancelled":
        studio.ai.debug_act_cancel(started["action_id"])
    else:
        studio.ai.gameplay_control = False
        studio.ai.play.cancel("the person took back the permission to play")  # (what Studio's toggle does)
    studio.mode = "play" if interruption != "stopped" else "edit"
    studio.ai.play.tick()
    result = studio.ai.debug_act_status(started["action_id"])
    assert result["status"] == "cancelled" and studio.window.down == set()
    assert studio.window.log[-1] == ("on_key_release", UP)


def test_results_are_kept_for_a_while_then_forgotten(studio: _Studio) -> None:
    ids = []
    for _ in range(runtime_play.RESULTS_KEPT + 3):
        ids.append(_until_done(studio, studio.ai.debug_act({"action": "move", "direction": "left", "frames": 1}))
                   ["action_id"])
    assert studio.ai.debug_act_status(ids[-1])["status"] == "done"
    assert studio.ai.debug_act_status(ids[0])["reason"] == "action_not_found"


def test_the_snapshot_shows_whats_near_and_whats_said(studio: _Studio) -> None:
    window = studio.window
    near = [SimpleNamespace(center_x=100.0 + dx, center_y=50.0, mesh_name=f"N{dx}", mesh_id=f"n{dx}", mesh_tag="npc")
            for dx in (300, 40, -90, 5000)]
    window.scene_controller.all_sprites = [window.player, *near]
    window.box.open, window.box.choices = True, [{"text": "Yes"}, {"text": "No", "disabled": True}]
    snap = studio.ai.debug_snapshot(5)
    assert [e["name"] for e in snap["nearby"]["entities"]] == ["N40", "N-90", "N300"]  # (nearest first; within reach)
    assert snap["nearby"]["entities"][0] == {"id": "n40", "name": "N40", "tag": "npc", "x": 140.0, "y": 50.0,
                                             "dx": 40.0, "dy": 0.0, "distance": 40.0}
    assert snap["dialogue"] == {"available": True, "open": True, "speaker": "Guide", "text": "Will you light it?",
                                "choices": [{"index": 0, "text": "Yes", "available": True},
                                            {"index": 1, "text": "No", "available": False}], "selected": 0}
    assert snap["studio"]["ai_gameplay_control"] is True


# --------------------------------------------------------------------- from MCP, over the live session

@pytest.fixture
def live(studio: _Studio) -> Iterator[_Studio]:
    """``studio`` with its live session, its frames running on another thread (Studio's main loop)."""
    studio.ai.start()
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            studio.frame()
            time.sleep(0.002)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    yield studio
    stop.set()
    thread.join(timeout=2)
    studio.ai.stop()


def test_the_mcp_tool_plays_and_reports_what_it_did(live: _Studio) -> None:
    root = str(live.project.root)
    answer = tools.debug_play_action("move", direction="right", frames=4, root=root)
    assert answer["ok"] is True and answer["action"]["status"] == "done"
    assert answer["action"]["after"]["player"][0] == answer["action"]["before"]["player"][0] + 20
    assert answer["snapshot"]["status"] == "playing" and answer["snapshot"]["player"]["x"] == 120.0
    refused = tools.debug_play_action("advance", root=root)
    assert refused["ok"] is False and refused["reason"] == "no_dialogue"
    live.ai.gameplay_control = False
    assert tools.debug_play_action("interact", root=root)["reason"] == "gameplay_control_off"


def test_an_action_that_outlasts_the_wait_is_cancelled(live: _Studio) -> None:
    answer = runtime_play.request_action(live.project.root, {"action": "move", "direction": "up", "frames": 120},
                                         wait=0.0)
    assert answer["ok"] is False and answer["reason"] == "action_timeout" and answer["status"] == "cancelled"
    for _ in range(100):
        if not live.window.down:
            break
        time.sleep(0.01)
    assert live.window.down == set()


def test_without_studio_or_the_token_nothing_is_played(live: _Studio, tmp_path: Path) -> None:
    assert tools.debug_play_action("interact", root=str(tmp_path))["reason"] in ("studio_not_open", "not_a_project")
    info = read_live_session_file(live.project.root)
    assert info is not None
    for method, path in (("POST", "/live/debug/act"), ("GET", "/live/debug/act?id=a1"),
                         ("POST", "/live/debug/act/cancel")):
        req = request.Request(f"http://127.0.0.1:{info['port']}{path}", data=b"{}" if method == "POST" else None,
                              method=method, headers={"Authorization": "Bearer wrong"})
        with pytest.raises(error.HTTPError) as caught:
            request.urlopen(req, timeout=2)  # noqa: S310 - loopback
        assert caught.value.code == 401
        caught.value.close()
    assert live.window.log == []
