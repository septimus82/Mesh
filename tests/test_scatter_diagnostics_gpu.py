"""Milestone 22C: Lakeside Village's scatter problem in Mesh Studio, with its own input events in a hidden window
(tooling/scatter_diagnostics_studio.py): a dense meadow, then small trees and rocks dragged over it, the meadow again,
and a thinning stroke where nothing is; what Studio says, and that a stroke placing nothing changes nothing.
GL-gated: MESH_GL_SMOKE=1."""

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
    import scatter_diagnostics_studio

    out = tmp_path_factory.mktemp("m22c")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        result: dict = scatter_diagnostics_studio.studio(out)
        return result
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_trees_over_a_dense_meadow_say_the_meadow_leaves_no_room_and_change_nothing(run: dict) -> None:
    meadow, trees = run["meadow"], run["trees_over_meadow"]
    assert meadow["message"].startswith("Scattered ") and meadow["undo_steps_added"] == 1
    assert trees["message"].startswith("Added nothing (Small tree). Held back: the Meadow already there leaves too "
                                       "little room (")
    assert trees["message"].endswith("Thin it first (Ctrl+drag) or scatter these before it.")
    assert not trees["rows_changed"] and trees["undo_steps_added"] == 0 and not trees["message_ok"]


def test_rocks_over_it_are_added_with_why_fewer(run: dict) -> None:
    rocks = run["rocks_over_meadow"]
    assert rocks["message"].startswith("Scattered ") and "(Rocks): one undo step. Held back: the Meadow already there" \
        in rocks["message"]
    assert rocks["rows_changed"] and rocks["undo_steps_added"] == 1


def test_the_meadow_again_and_thinning_bare_ground_say_why_and_change_nothing(run: dict) -> None:
    again, thin = run["meadow_again"], run["thin_where_nothing_is"]
    assert again["message"] == ("Added nothing (Meadow). Already as dense as Per m² asks here. Raise Per m² or "
                                "brush somewhere sparser.")
    assert thin["message"] == "Nothing under the brush to thin out."
    for step in (again, thin):
        assert not step["rows_changed"] and step["undo_steps_added"] == 0
