"""M17-L4-4: an AI sets an HD-2D room's bloom through the authoring API (as the MCP server's propose/apply tools do):
the same stored settings as Studio's operation, the review names the change, a dry run changes nothing, bad values are
refused naming the key (all or none), and only that room's ``bloom`` key changes. Integration: it makes a project from
the HD-2D template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops

pytestmark = pytest.mark.integration


def test_ai_sets_reviews_and_turns_off_the_bloom(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    others = {key: project.scene(key) for key, *_rest in project.rooms() if key != room}
    before = project.scene(room)
    assert "bloom" not in before["settings"]["hd2d"]  # (a new project's rooms: off)
    documents = json.dumps(project.all_documents(), sort_keys=True)
    authoring.dry_run(project, [{"op": "set_hd2d_bloom", "room": room, "preset": "warm"}])
    assert json.dumps(project.all_documents(), sort_keys=True) == documents  # (a dry run changes nothing)
    authoring.apply(project, [{"op": "set_hd2d_bloom", "room": room, "preset": "warm", "strength": 1.5,
                               "spread": 0.5}])
    after = project.scene(room)
    assert after == ops.set_hd2d_bloom(ops.set_hd2d_bloom(before, preset="warm"), strength=1.5, spread=0.5)
    assert after["settings"]["hd2d"]["bloom"] == {"preset": "warm", "strength": 1.5, "spread": 0.5}
    rest = json.loads(json.dumps(after))
    del rest["settings"]["hd2d"]["bloom"]
    assert rest == before and all(project.scene(n) == doc for n, doc in others.items())  # nothing else changed
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: after}})
    assert any("bloom warm (strength 1.5, spread 0.5)" in line for line in lines), lines
    documents = json.dumps(project.all_documents(), sort_keys=True)
    for change, message in (({"strength": 9}, "strength"), ({"preset": "glow"}, "Bloom preset must be one of"),
                            ({"preset": ["warm"]}, "Bloom preset must be one of")):
        with pytest.raises(authoring.ChangeError, match=message):
            authoring.dry_run(project, [{"op": "set_hd2d_bloom", "room": room, **change}])
        with pytest.raises(authoring.ChangeError, match=message):
            authoring.apply(project, [{"op": "set_hd2d_bloom", "room": room, "threshold": 0.5},
                                      {"op": "set_hd2d_bloom", "room": room, **change}])
        assert json.dumps(project.all_documents(), sort_keys=True) == documents  # (all or none)
    authoring.apply(project, [{"op": "set_hd2d_bloom", "room": room, "preset": "off"}])
    assert project.scene(room) == before
