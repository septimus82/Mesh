"""#460 Phase B: an AI sets an HD-2D room's depth of field through the authoring API (as the MCP server's
propose/apply tools do) and the review names the change; bad values are refused naming the key. Integration: it
makes a project from the HD-2D template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops

pytestmark = pytest.mark.integration


def test_ai_sets_and_reviews_the_depth_of_field(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    before = project.scene(room)
    assert "set_depth_of_field" in authoring.operations() and "depth_of_field_of" not in authoring.operations()
    authoring.apply(project, [{"op": "set_depth_of_field", "room": room, "enabled": True, "max_blur": 3}])
    after = project.scene(room)
    assert after["settings"]["hd2d"]["depth_of_field"] == {"enabled": True, "max_blur": 3.0}
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: after}})
    assert any("depth of field on (max blur 3)" in line for line in lines), lines
    off = ops.set_depth_of_field(after, enabled=False)
    assert any("depth of field off" in line for line in authoring.summarize(
        {"rooms": {room: after}}, {"rooms": {room: off}})), "the AI review names the change"
    with pytest.raises(authoring.ChangeError, match="max_blur"):
        authoring.apply(project, [{"op": "set_depth_of_field", "room": room, "max_blur": 40}])
