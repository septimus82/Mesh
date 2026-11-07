"""Milestone 22A.1: an HD-2D room expanded with Mesh Studio's own controls (hidden window, window input events like a
person): a fresh starter project's 40 x 30 m room, with a cottage and a villager in it, grown to 48 x 36 m in Camera
and sun... > Room size; undo and redo; saved (its map file with it), reopened; in the game the player walks onto the
new ground, up to its new edge. GL-gated: MESH_GL_SMOKE=1."""

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
    import hd2d_room_expand_studio

    out = tmp_path_factory.mktemp("m22a1")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        return hd2d_room_expand_studio.studio(out)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_a_populated_room_is_expanded_in_studio_with_everything_kept(run: dict) -> None:
    assert run["panel_before"] == ["40 x 30 m (1 m is a tile)."] and run["panel_after"] == ["48 x 36 m (1 m is a tile)."]
    assert run["expanded_message"].startswith("The room is now 48 x 36 m: 8 m more to the east, 6 m more to the north")
    assert run["content_kept"]
    assert (run["undone"]["width"], run["redone"]["width"]) == (40, 48)


def test_its_map_file_is_saved_at_its_size_and_it_reopens_the_same(run: dict) -> None:
    assert run["map_file_before_save"] == [40, 30]  # the files change only when the room is saved
    disk = run["on_disk"]
    assert disk["ground_to"] == [1536.0, 1152.0] and disk["bounds"] == [0.0, 0.0, 1536.0, 1152.0]
    assert disk["world"] == [1536.0, 1152.0] and disk["tilemap"] == disk["map_file"] == [48, 36]
    assert [list(layer) for layer in disk["map_file_layers"]] == [[48, 36, 48 * 36]]
    assert run["reopened"]["size"]["width"] == 48 and run["reopened"]["unsaved"] == []


def test_the_player_walks_onto_the_new_ground_up_to_its_new_edge(run: dict) -> None:
    walk = run["walk"]
    assert walk["world_bounds_walking"] and walk["ground_east_edge"] == 1536.0  # (the cottage: its walls and floors)
    assert 1280.0 + 64 < walk["end_x"] <= 1536.0  # past the old edge, stopped at the new one
    assert walk["tilemap_size"] == [48, 36] and walk["camera_bounds"] == [0.0, 0.0, 1536.0, 1152.0]
