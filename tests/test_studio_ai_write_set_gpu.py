"""#462 S1 in Mesh Studio's own window (hidden): an AI's stale proposal can't put back what the person moved.

The person drags the player east in the 3D view after an AI proposed moving it north (``move_entity`` with the x it
read). Clicking Studio's Accept used to apply it and silently put the player back at the old x. Now it is refused as
a conflict, the person's position kept and nothing else changed; a proposal that doesn't write what the person
changed (a rename) is accepted on top of the drag, undoes as one step, and saves. GL-gated: set MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import copy
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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


@pytest.fixture
def driver(tmp_path: Path) -> Iterator[Any]:
    import hd2d_floors_demo
    from hd2d_studio_demo import StudioDriver

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"  # no loopback server: the proposal is staged as the bridge stages it
    project = hd2d_floors_demo.build(tmp_path / "HD-2D studio")
    d = StudioDriver(project)
    try:
        yield d
    finally:
        d.close()
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def _player(d: Any) -> dict[str, Any]:
    pid = d.game.player().mesh_entity_data["id"]
    return next(e for e in d.studio.project.scene()["entities"] if e.get("id") == pid)


def _drag_player_east(d: Any, metres: float = 2.0) -> None:
    """The person drags the player east in the 3D view, as a person does (mouse press, drag, release)."""
    from hd2d_studio_demo import PX

    sprite = d.game.player()
    z = sprite.mesh_entity_data.get("elevation", 0.0) / PX
    grab = d.screen((sprite.center_x / PX, sprite.bottom / PX, z + 0.75))
    d.click(*grab)  # (selected first: the drag moves what is selected)
    ground = d.studio.hd2d.ground_px(*grab, 0.0)
    assert ground is not None
    d.drag(grab, d.screen(((ground[0] + metres * PX) / PX, ground[1] / PX, 0.0)))


def _stage(d: Any, changes: list[dict[str, Any]]) -> Any:
    """An AI reads the project and proposes ``changes`` against what it read (what the MCP tools send)."""
    read = d.studio.ai.read_live_scene()
    proposal = d.studio.ai.stage_proposal_payload({"title": "Tidy the start", "source": "a test AI",
                                                   "changes": changes, "base_revision": read["revision"]})
    assert not isinstance(proposal, dict), proposal
    return proposal


def test_accept_in_studio_refuses_a_stale_move_and_takes_a_rename_on_top_of_the_drag(driver: Any) -> None:
    d, studio = driver, driver.studio
    k = d.arcade.key
    _drag_player_east(d)  # (on the grid first: a drag snaps it, so the next one changes only its x)
    player = _player(d)
    pid, x0, y0 = player["id"], float(player["x"]), float(player["y"])

    # the AI proposes moving the player north, giving the x it read; the person then drags it east
    stale = _stage(d, [{"op": "move_entity", "entity_id": pid, "x": x0, "y": y0 + 64}])
    _drag_player_east(d)
    dragged = _player(d)
    assert float(dragged["x"]) > x0 + 32 and float(dragged["y"]) == y0, ("the drag moved it east only", x0, y0, dragged)
    before, revision = copy.deepcopy(studio.project.all_documents()), studio.project.revision

    studio.open_ai()
    d.advance()
    d.button("Accept")

    assert (float(_player(d)["x"]), float(_player(d)["y"])) == (float(dragged["x"]), float(dragged["y"])), \
        "the person's position kept"
    assert stale.status == "conflict" and studio.project.revision == revision
    assert studio.project.all_documents() == before, "nothing applied"
    shown = " ".join(d.texts())
    assert "Not applied" in shown and "proposed" in shown, "Studio shows the conflict"
    d.button("Reject")
    assert stale.status == "rejected" and studio.project.all_documents() == before

    # a proposal that doesn't write what the person changed: accepted on top of the drag
    rename = _stage(d, [{"op": "rename_entity", "entity_id": pid, "name": "Hero"}])
    _drag_player_east(d)
    moved = _player(d)
    studio.open_ai()  # (the panel went back to the inspector when nothing was waiting)
    d.advance()
    d.button("Accept")
    assert rename.status == "accepted"
    assert _player(d)["name"] == "Hero" and float(_player(d)["x"]) == float(moved["x"]), "both survive"
    # one undo step takes back the AI's rename only; redo brings it back
    ctrl = k.MOD_CTRL
    d.key(k.Z, ctrl)
    assert _player(d)["name"] != "Hero" and float(_player(d)["x"]) == float(moved["x"])
    d.key(k.Y, ctrl)
    assert _player(d)["name"] == "Hero"
    # saved, and read back from disk as written
    d.key(k.S, ctrl)
    assert not studio.project.is_dirty
    from engine.studio_project import Project

    again = Project(studio.project.root, studio.project.world_file)
    on_disk = next(e for e in again.scene()["entities"] if e.get("id") == pid)
    assert on_disk["name"] == "Hero" and float(on_disk["x"]) == float(moved["x"])
