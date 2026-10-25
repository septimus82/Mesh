"""Milestone 16 Stage 6A, proven in a hidden window: a project made from the HD-2D RPG (Preview) template opens
in Mesh Studio, is edited there (a building moved, a person placed on a raised floor in 3D, a lamp changed, an AI's
proposal accepted), saved, reopened and played: stairs, bridge, underpass, three conversations, a sign, a door to
the second room, quick save and load (tooling/hd2d_starter_demo.py). GL-gated: set MESH_GL_SMOKE=1."""

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
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),  # Studio's text fields (pre-existing)
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    import hd2d_starter_demo as demo

    report = demo.check(tmp_path_factory.mktemp("starter"))
    return {s["step"]: s for s in report["steps"]} | {"timings": report["timings"], "gl": report["gl"]}


def _walk(run: dict) -> dict:
    return {w["after"]: w for w in run["play"]["walk"]}


def test_the_project_opens_in_studio_as_hd2d(run: dict) -> None:
    opened = run["open"]
    assert opened["hd2d"] and opened["error"] is None and opened["structures"] >= 40 and opened["room"] == "start"


def test_a_building_is_picked_and_moved(run: dict) -> None:
    move = run["move_building"]
    assert move["picked"] == "shop"
    assert move["shop"]["x"] == (24 + 4 + 1) * 32.0, "dragged 1 m east"


def test_a_structure_is_picked_and_turned(run: dict) -> None:
    turn = run["turn_structure"]
    assert turn["picked"] == "crate_1" and turn["crate"]["rotation"] == 90.0
    assert turn["see_through"] is True and turn["see_through_undone"] is None, "See-through on, then undone"


def test_a_starter_model_is_browsed_and_placed(run: dict) -> None:
    place = run["place_model"]
    assert any(label.startswith("Lamp post") for label in place["listed"]), "the kit is in the catalogue"
    assert place["placed"] and place["structure"]["model"] == "assets/models/lamp_post.glb"
    assert (place["structure"]["x"], place["structure"]["y"]) == (22.0 * 32, 11.0 * 32)


def test_a_person_is_placed_on_a_raised_floor_by_clicking_in_3d(run: dict) -> None:
    place = run["place_person"]
    assert "Nobody could stand there" in place["refused_message"], "a click into the fence is refused"
    assert list(place["marker"]) == [10.0, 24.0, 2.0]
    assert place["entity"]["elevation"] == 64.0 and "2.0 m up" in place["message"]
    assert place["stands_on"][1].startswith("plateau_west_") and place["stands_on"][0] == pytest.approx(2.0)
    assert place["gone_after_undo"] and place["back_after_redo"]


def test_what_the_new_person_says_is_edited_in_studio(run: dict) -> None:
    edit = run["edit_person"]
    assert edit["selected"] == run["place_person"]["entity"]["id"] and edit["says"] == "Welcome to the west hill!"


def test_a_lamp_changes_colour_and_height(run: dict) -> None:
    lamp = run["modify_light"]["lamp"]
    assert lamp["color"] == "#88bbff" and lamp["elevation"] == 96.0 and run["modify_light"]["renderer_lamps"] == 2


def test_an_ai_places_a_sign_on_the_hill_and_the_person_accepts(run: dict) -> None:
    ai = run["ai_proposal"]
    assert ai["sign"] is not None and ai["sign"]["elevation"] == 64.0


def test_everything_survives_save_and_reopen(run: dict) -> None:
    assert run["save_reopen"]["same"] is True


def test_play_climbs_crosses_ducks_under_talks_reads_and_changes_rooms(run: dict) -> None:
    w = _walk(run)
    assert w["up the west stairs onto the plateau"]["elevation_m"] == 2.0
    assert w["across the bridge onto the east plateau"]["floor"].startswith("plateau_east_")
    assert w["down the east stairs"]["elevation_m"] == 0.0
    under = w["under the bridge"]
    assert under["elevation_m"] == 0.0 and under["floor"] == "ground" and under["feet_m"][1] > 23.0
    talks = {key: w[key] for key in ("talked to the new person", "talked to the Elder", "read the sign")}
    assert all(t["dialogue_opened"] and t["dialogue_closed"] for t in talks.values())
    assert talks["talked to the new person"]["speaker"] == "Person"
    assert talks["talked to the new person"]["first_line"] == "Welcome to the west hill!", "the line edited in Studio"
    assert talks["talked to the Elder"]["speaker"] == "Elder"
    assert talks["talked to the Elder"]["first_line"] == "Welcome to Mesh Village!"
    assert talks["read the sign"]["first_line"] == "Mesh Village"
    inside = w["through the cottage door"]
    assert inside["room"].endswith("cottage.json") and inside["floor"] == "room/col_floor"
    loaded = w["quick-saved, moved, quick-loaded"]
    assert loaded["moved_to"] != loaded["saved_at"] and loaded["feet_m"] == loaded["saved_at"]
    assert run["play"]["mode_after_stop"] == "edit"


def test_gpu_objects_do_not_grow_across_play_stop(run: dict) -> None:
    gl = run["gl"]
    assert gl["edit_after_second_play_stop"] == gl["edit_after_stop"], gl


def test_the_kit_is_in_the_model_browser_and_another_model_imports(run: dict) -> None:
    names = {t.split("  ")[0] for t in run["model_browser"]["listed"]}
    assert {"Cottage", "Shop", "Staircase", "Bridge (6 m)"} & names
    assert run["model_browser"]["imported"].startswith("Imported Cottage V2")
