"""HD-2D online M3-5/M3-6: two clients share one HD-2D room (the owner's two-window acceptance).

M1-B's Crossing, built in Mesh Studio, with a bandit, its loot and a walk-in door added on the ground directly under the
bridge deck through the documented authoring operations (tooling/m3_two_client_evidence.py ``build_scene``). A real
authority (mesh_net.server.WorldServer) and two real hidden client windows (tooling/net_world_probe.py, each its own
process with its own copy of the project) play it, driven through the probes' command channel with key presses; every
window fact is read from that window's own objects (``run``: once for the module, each test asserting its own part).
Two more windows try to join and are refused. One test (or a few) per owner criterion:

- both players can independently move up and down the bridge: ``test_each_player_climbs_onto_the_deck_and_back_down``;
- one stands on the bridge while the other passes underneath: ``test_one_stands_on_the_deck_while_the_other_passes_beneath``;
- neither can attack, loot or trigger doors through the deck: ``test_no_attack_through_the_deck``,
  ``test_no_looting_through_the_deck``, ``test_no_door_through_the_deck``;
- both cameras follow the correct local character: ``test_each_camera_follows_its_own_character``;
- a client with mismatched or downgraded room geometry is refused safely:
  ``test_a_client_whose_geometry_differs_is_refused_and_the_room_plays_on``,
  ``test_a_client_whose_room_fell_back_to_2d_refuses_it_and_the_room_plays_on``.

Rendered evidence of the same run: ``py -3.13 tooling/m3_two_client_evidence.py docs/reviews/m3_two_client`` (this
test writes nothing into the repository). Hidden windows only, audio at master 0. GL-gated: set MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade
from engine.interaction import DEFAULT_INTERACT_MAX_DIST

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="requires real Mesh windows (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
DECK, GROUND = [64.0, "bridge_6m/col_deck"], [0.0, "ground"]
PX = 32.0


@pytest.fixture(scope="module")
def facts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    import m3_two_client_evidence as m3

    out = tmp_path_factory.mktemp("m3")
    with pytest.MonkeyPatch.context() as env:  # (for this run only, then as they were)
        env.setenv("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        project = m3.build_scene(out)
        result: dict[str, Any] = m3.run(project, out)
    return result


def _part(facts: dict[str, Any], name: str) -> dict[str, Any]:
    join = facts["join"]
    assert join["keys"] == ["crossing", "crossing"] and len(set(join["identity"])) == 1, join
    assert join["hd2d"] == [True, True], "both windows play the room in 3D"
    part: dict[str, Any] = facts[name]
    assert "error" not in part, part["error"]
    return part


def _row(seen: list[Any]) -> list[Any]:
    """A window's [x, y, elevation, floor] of an avatar, or the server's [x, y, elevation, floor, room]: the first four."""
    return list(seen[:4])


def test_each_player_climbs_onto_the_deck_and_back_down(facts: dict[str, Any]) -> None:
    """Each in turn walks up the west stairs, along the plateau onto the deck, and back down, the other standing still:
    the server, the mover's own window and the other's window all put it 2 m up on the deck, then on the ground."""
    part = _part(facts, "a")
    for name in ("a", "b"):
        walked = part[name]
        for leg, level in (("up", DECK), ("down", GROUND)):
            server = walked[leg]["server"]
            assert server[2:4] == level and server[4].startswith("crossing:"), (name, leg, server)
            assert walked[leg]["own"] == _row(server), (name, leg, "its own window", walked[leg])
            assert walked[leg]["peer"] == _row(server), (name, leg, "the other window", walked[leg])
        assert walked["other_before"] == walked["other_after"], (name, "the other moved meanwhile")


def test_one_stands_on_the_deck_while_the_other_passes_beneath(facts: dict[str, Any]) -> None:
    """A stands on the deck over the underpass while B walks beneath it from south of the deck to north of it, then
    stands directly under A: each keeps its floor, neither blocks the other, and each window draws the other at its
    own height (where the renderer's camera puts that avatar's feet, at the snapshot's elevation)."""
    part = _part(facts, "b")
    above, samples = part["above"], part["samples"]
    assert above[2:4] == DECK
    assert samples and all(s["a"] == above for s in samples), "A stayed where it stood on the deck"
    assert all(s["b"][2:4] == GROUND and abs(s["b"][0] - above[0]) <= 16 for s in samples), "B beneath it, on the ground"
    ys = [s["b"][1] for s in samples]
    assert ys == sorted(ys) and ys[0] < above[1] - 96 < above[1] + 48 < part["passed"][1], (ys, part["passed"])
    a, b = part["a"], part["b"]
    # (each walked to its spot within 8 px: a step is 7.5 px; "beneath" is within half a picture's width)
    assert a[2:4] == DECK and b[2:4] == GROUND and abs(a[1] - b[1]) <= 8 and abs(a[0] - b[0]) <= 16, (a, b)
    windows = part["windows"]
    assert windows["a"] == {"own": _row(a), "peer": _row(b)} and windows["b"] == {"own": _row(b), "peer": _row(a)}
    for name, look in part["look"].items():
        for eid, drawn in look["avatars"].items():
            feet = drawn["feet"]
            other = feet["64"] if feet["row"] == feet["0"] else feet["0"]
            bottom = drawn["box"][3]
            assert drawn["drawn"] > 100, (name, eid, drawn)
            assert abs(bottom - feet["row"]) <= 6 < abs(bottom - other), (name, eid, "drawn at the wrong height", drawn)


def test_no_attack_through_the_deck(facts: dict[str, Any]) -> None:
    """A on the deck, facing the bandit beneath with its hitbox on it (planar contact: only the floors between can
    refuse it), strikes: the server runs the swing (its cooldown starts) and the bandit keeps its HP. B on the ground
    strikes it: it dies and drops its loot, in both windows."""
    part = _part(facts, "c")
    assert part["a_at"][2:4] == DECK and part["a_facing"] == 0 and part["a_planar_hit"], part
    assert part["a_swung"], "the server ran A's attack"
    assert part["after_a_attack"] == {"hp": part["hp_before"], "dead": False}, part["after_a_attack"]
    assert part["after_b_attack"] == {"hp": 0.0, "dead": True, "dropped": True}, part["after_b_attack"]
    assert part["drops_seen"] == [[facts["join"]["bandit"]]] * 2, part["drops_seen"]


def test_no_looting_through_the_deck(facts: dict[str, Any]) -> None:
    """A on the deck, within planar reach of the loot beneath, takes (its window sends ``take``, not ``use``: the
    server's rule is what refuses it): the loot stays. B on the ground takes it."""
    part = _part(facts, "c")
    assert part["a_sent"] == ["attack", "take"], part["a_sent"]
    assert part["a_loot_distance"] <= DEFAULT_INTERACT_MAX_DIST, part
    assert part["after_a_take"] == {"dropped": True, "held": False}, part["after_a_take"]
    assert part["b_sent"] == "take" and part["b_loot_distance"] <= DEFAULT_INTERACT_MAX_DIST, part
    taken = part["after_b_take"]
    assert taken["dropped"] is False and taken["holder"] == taken["b"], taken
    assert part["loot_seen"] == [[[facts["join"]["bandit"], taken["b"]]]] * 2, part["loot_seen"]


def test_no_door_through_the_deck(facts: dict[str, Any]) -> None:
    """A walks over the door beneath on the deck, its picture across the door's area: on the deck at every moment it
    is on the area, and no transfer, in the server or its window; it ends 2 m up (on the deck, or past its west end on
    the plateau, where a slow runner's late release carries it). B walks into it on the ground: through to the Start
    room; A's window sees B go."""
    part = _part(facts, "door")
    pa, pb = facts["join"]["players"]
    # (A crosses the door's area on the deck each time it walks onto the deck, too: never a transfer, all run long)
    assert facts["transfers"] == [[pb, f"crossing:1 {facts['join']['door']} moved"]], facts["transfers"]
    assert part["a_touched_area"], "A crossed the door's area"
    assert part["a_contact_levels"] == [DECK], part["a_contact_levels"]  # (through the deck, all the way across)
    after = part["a_after"]
    assert after[2] == DECK[0] and after[3] != GROUND[1] and after[4].startswith("crossing:"), after
    assert part["a_window"] == {"key": "crossing", "loads": [after[4]], "own": after[:4]}, part["a_window"]
    assert part["b_window"]["key"] == "start" and part["b_after"][4].startswith("start:"), part
    assert part["a_sees"] == [facts["join"]["entities"][0]], part["a_sees"]


def test_each_camera_follows_its_own_character(facts: dict[str, Any]) -> None:
    """With A on the deck and B directly beneath, each window's renderer follows its own avatar (its camera_target
    and followed()), the camera at that avatar's x and at its own height over its feet: 2 m higher in A's window."""
    part = _part(facts, "d")
    for name in ("a", "b"):
        cam, own = part[name], part["entities"][name]
        assert cam["camera_target"] == own and cam["followed"] == own, (name, cam)
        assert abs(cam["camera"][0] - cam["own"][0] / PX) < 0.05, (name, cam)
        assert abs(cam["camera"][2] - (cam["own"][2] / PX + cam["camera_height"])) < 0.05, (name, cam)
    assert part["a"]["own"][2:4] == DECK and part["b"]["own"][2:4] == GROUND
    assert part["a"]["camera"][2] - part["b"]["camera"][2] == pytest.approx(2.0, abs=0.05)


def _plays_on(part: dict[str, Any], after: str, windows: str) -> None:
    """After a refused client: the two players are where they were, online (nobody else), each window playing with
    both of them; the server ran on, and the refused windows exited cleanly."""
    assert part["server_ticks"] >= 10, "the server runs on"
    assert part[after] == part["before"], "the two players are where they were, both online (and nobody else)"
    seen = part[windows]
    entities = sorted(w[1] for w in seen.values())
    assert {n: w[0] for n, w in seen.items()} == {"a": "playing", "b": "playing"}, seen
    assert all(w[2] == entities for w in seen.values()), seen
    assert part["workers"] == [], part["workers"]


def test_a_client_whose_geometry_differs_is_refused_and_the_room_plays_on(facts: dict[str, Any]) -> None:
    """A window whose files give the bridge deck a collider 0.5 m higher is refused at welcome (its world differs),
    before it loads any room; the two players play on."""
    part = _part(facts, "e")
    raised = part["raised"]
    assert raised["phase"] == "disconnected" and "different world" in raised["status"], raised
    assert raised["loads"] == [] and "playing" not in raised["phases"], raised
    _plays_on(part, "after_raised", "windows_after_raised")


def test_a_client_whose_room_fell_back_to_2d_refuses_it_and_the_room_plays_on(facts: dict[str, Any]) -> None:
    """A window whose room's 3D build fails (the driver refusing, simulated) plays it 2D: it refuses to join it (the
    M1-A-2 guard), never plays it, and leaves; the two players play on."""
    part = _part(facts, "e")
    flat = part["flat"]
    assert "simulated" in (flat["hd2d_error"] or "") and "in 2D" in (flat["refusal"] or ""), flat
    assert flat["phase"] == "disconnected" and flat["loads"] == ["crossing:1"] and "playing" not in flat["phases"], flat
    assert part["flat_member"] == {"online": False, "eid": None}, part["flat_member"]
    _plays_on(part, "after", "windows")


def test_the_windows_exit_cleanly(facts: dict[str, Any]) -> None:
    assert facts["workers"] == [], facts["workers"]
