"""D3A (#422): "why can't the player use this door?" over MCP in a real Mesh Studio play-test (tooling/
d3a_interaction_scenario.py): a door kept out by its flag, the flag set by talking, the room loaded again, then
too far, another object chosen instead, and available, which pressing interact then confirms. Silent. GL-gated:
MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import d3a_interaction_scenario

    out = tmp_path_factory.mktemp("d3a")
    os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
    return d3a_interaction_scenario.run(out)


def _code(answer: dict) -> str | None:
    return (answer.get("blocking") or {}).get("code")


def test_editing_is_not_playing(run: dict) -> None:
    assert run["1_editing"]["status"] == "not_playing"


def test_the_door_kept_out_by_its_flag_and_where_the_flag_comes_from(run: dict) -> None:
    out = run["2_no_key"]
    assert out["available"] is False and _code(out) == "in_room" and "flags keep it out" in out["blocking"]["message"]
    assert out["flags"] == {"has_key": False}
    sources = out["flag_sources"]["has_key"]
    assert [(s["entity"], s["via"], s["choice"], s["sets_to"]) for s in sources] == [
        ("Guide", "dialogue choice", "I'll light it.", True)]


def test_a_dialogue_choice_waits_for_its_flag(run: dict) -> None:
    before = {c["id"]: c for c in run["2_guide"]["dialogue"]["choices"]}
    assert before["where"]["available"] is False and before["where"]["unmet"] == ["agreed_to_help"]
    after = {c["id"]: c for c in run["3_guide"]["dialogue"]["choices"]}
    assert after["where"]["available"] is True and after["where"]["unmet"] == []


def test_after_talking_the_flag_is_met_but_the_room_loaded_first(run: dict) -> None:
    assert run["3_talk"]["said"][-1].startswith("Thank you!")
    out = run["3_key_not_reloaded"]
    assert _code(out) == "in_room" and out["flags"] == {"has_key": True}
    assert [c["code"] for c in out["possible_causes"]] == ["loaded_before_flags_were_met"]


def test_back_in_the_room_too_far_then_another_chosen_then_available(run: dict) -> None:
    assert run["4_room"].endswith("start.json")
    far = run["5_far"]
    assert _code(far) == "distance" and far["observed"][-1]["detail"]["radius"] == 72.0
    crowded = run["5_crowded"]
    selection = next(c for c in crowded["observed"] if c["code"] == "selection")
    assert _code(crowded) == "selection" and selection["detail"]["chosen"] == "notice"
    clear = run["5_clear"]
    assert clear["available"] is True and clear["blocking"] is None and clear["how"] == "interact"


def test_the_game_agrees_and_reading_changed_nothing(run: dict) -> None:
    assert run["5_pressed_interact"].endswith("cellar.json")  # (pressing interact did what "available" said)
    assert run["6_read_changed_nothing"] is True
