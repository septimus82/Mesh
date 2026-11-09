"""M17-L4-2: an AI sets an HD-2D room's colour grade and vignette through the authoring API (as the MCP server's
propose/apply tools do): the same stored settings as Studio's operation, the review names the change, bad values are
refused naming the key, and only that room's ``post`` key changes. Integration: it makes a project from the HD-2D
template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import authoring
from engine import project_ops as ops

pytestmark = pytest.mark.integration


def test_ai_sets_reviews_and_turns_off_the_picture_treatment(tmp_path: Path) -> None:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    others = {key: project.scene(key) for key, *_rest in project.rooms() if key != room}
    before = project.scene(room)
    authoring.apply(project, [{"op": "set_hd2d_post", "room": room, "preset": "golden_hour", "strength": 0.7,
                               "vignette": 0.2}])
    after = project.scene(room)
    studio_op = ops.set_hd2d_post(ops.set_hd2d_post(before, preset="golden_hour"), strength=0.7, vignette=0.2)
    assert after == studio_op  # (the AI's change and Studio's write the same room)
    assert after["settings"]["hd2d"]["post"] == {"preset": "golden_hour", "strength": 0.7, "vignette": 0.2}
    rest = json.loads(json.dumps(after))
    del rest["settings"]["hd2d"]["post"]
    assert rest == before and all(project.scene(n) == doc for n, doc in others.items())  # nothing else changed
    lines = authoring.summarize({"rooms": {room: before}}, {"rooms": {room: after}})
    assert any("picture treatment golden hour (strength 0.7, vignette 0.2)" in line for line in lines), lines
    with pytest.raises(authoring.ChangeError, match="strength"):
        authoring.apply(project, [{"op": "set_hd2d_post", "room": room, "strength": 3}])
    with pytest.raises(authoring.ChangeError, match="Picture preset must be one of"):
        authoring.apply(project, [{"op": "set_hd2d_post", "room": room, "preset": "morning_mist"}])
    authoring.apply(project, [{"op": "set_hd2d_post", "room": room, "preset": "off"}])
    assert project.scene(room) == before
    off_lines = authoring.summarize({"rooms": {room: after}}, {"rooms": {room: before}})
    assert any("picture treatment off" in line for line in off_lines), off_lines
