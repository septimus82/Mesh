"""M17-W1: an AI makes a waterfall through the authoring API (as the MCP server's propose/apply tools do): the same
stored river as Studio's operations, the review names it, a dry run changes nothing, impossible waterfalls are refused
saying why (all or none), and removing it gives the room back as it was. Integration: it makes a project from the
HD-2D template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops

pytestmark = pytest.mark.integration

# a 2 m stream falling 2 m from its second point to its third (1.25 m on), then running on
COURSE = [[200.0, 200.0, 64.0, 64.0], [200.0, 400.0, 64.0, 64.0], [200.0, 440.0, 64.0, 0.0], [200.0, 600.0, 64.0, 0.0]]


def test_ai_makes_reviews_refuses_and_removes_a_waterfall(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    authoring.apply(project, [{"op": "add_river", "room": room, "river_id": "falls", "points": COURSE}])
    before = project.scene(room)
    documents = json.dumps(project.all_documents(), sort_keys=True)
    authoring.dry_run(project, [{"op": "set_waterfall", "room": room, "river_id": "falls", "point": 1}])
    assert json.dumps(project.all_documents(), sort_keys=True) == documents  # (a dry run changes nothing)
    authoring.apply(project, [{"op": "set_waterfall", "room": room, "river_id": "falls", "point": 1, "spray": 0.2}])
    after = project.scene(room)
    assert after == ops.set_waterfall(before, "falls", 1, spray=0.2)
    assert ops.rivers(after)[0]["falls"] == [{"from": 1, "spray": 0.2}]
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: after}})
    assert any("changes river 'falls' (waterfall from point 2 to 3 (spray 0.2))" in line for line in lines), lines
    documents = json.dumps(project.all_documents(), sort_keys=True)
    for change, message in (({"point": 0}, "needs water above and below it"),
                            ({"point": 1, "foam": 2}, "foam must be a number from 0 to 1"),
                            ({"point": 2}, "ordinary water between them|needs water above and below it")):
        with pytest.raises(authoring.ChangeError, match=message):
            authoring.dry_run(project, [{"op": "set_waterfall", "room": room, "river_id": "falls", **change}])
        with pytest.raises(authoring.ChangeError, match=message):
            authoring.apply(project, [{"op": "set_waterfall", "room": room, "river_id": "falls", "point": 1,
                                       "foam": 0.2},
                                      {"op": "set_waterfall", "room": room, "river_id": "falls", **change}])
        assert json.dumps(project.all_documents(), sort_keys=True) == documents  # (all or none)
    shallow = [list(p) for p in COURSE]
    shallow[2][3] = 56.0  # a quarter metre under the top
    with pytest.raises(authoring.ChangeError, match="drops 0.25 m"):
        authoring.apply(project, [{"op": "set_river", "room": room, "river_id": "falls", "points": shallow}])
    authoring.apply(project, [{"op": "remove_waterfall", "room": room, "river_id": "falls", "point": 1}])
    assert project.scene(room) == before
