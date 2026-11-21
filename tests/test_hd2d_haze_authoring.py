"""M17-L4-3: an AI sets an HD-2D room's haze through the authoring API (as the MCP server's propose/apply tools do): the
same stored settings as Studio's operation, the review names the change, bad values are refused naming the key, and
only that room's ``haze`` key changes. Integration: it makes a project from the HD-2D template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops

pytestmark = pytest.mark.integration


def test_ai_sets_reviews_and_turns_off_the_haze(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    others = {key: project.scene(key) for key, *_rest in project.rooms() if key != room}
    before = project.scene(room)
    authoring.apply(project, [{"op": "set_hd2d_haze", "room": room, "preset": "evening", "strength": 0.2,
                               "falloff": 30}])
    after = project.scene(room)
    assert after == ops.set_hd2d_haze(ops.set_hd2d_haze(before, preset="evening"), strength=0.2, falloff=30)
    assert after["settings"]["hd2d"]["haze"] == {"preset": "evening", "strength": 0.2, "falloff": 30}
    rest = json.loads(json.dumps(after))
    del rest["settings"]["hd2d"]["haze"]
    assert rest == before and all(project.scene(n) == doc for n, doc in others.items())  # nothing else changed
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: after}})
    assert any("haze evening (strength 0.2, falloff 30 m)" in line for line in lines), lines
    documents = json.dumps(project.all_documents(), sort_keys=True)
    for change, message in (({"strength": 3}, "strength"), ({"preset": "fog"}, "Haze preset must be one of"),
                            ({"preset": ["evening"]}, "Haze preset must be one of")):
        with pytest.raises(authoring.ChangeError, match=message):
            authoring.dry_run(project, [{"op": "set_hd2d_haze", "room": room, **change}])
        with pytest.raises(authoring.ChangeError, match=message):
            authoring.apply(project, [{"op": "set_hd2d_haze", "room": room, "start": 9}, {"op": "set_hd2d_haze",
                                                                                         "room": room, **change}])
        assert json.dumps(project.all_documents(), sort_keys=True) == documents  # (all or none)
    authoring.apply(project, [{"op": "set_hd2d_haze", "room": room, "preset": "off"}])
    assert project.scene(room) == before
