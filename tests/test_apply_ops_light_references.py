"""A-07: ``apply_ops`` on a Studio project addresses lights by the batch's own order (``@N``), never by the room's
light count before the batch.

Before: an ``add_light`` carrying extra settings was followed by a ``set_light`` at ``len(lights)`` of the room as it
was before the batch, so a second ``add_light`` in the same batch had its settings written onto the first one's light
(and a ``delete_light`` earlier in the batch shifted the target again). Reached through the real MCP tool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.mcp_server import tools
from engine.project_scaffold import create_project

pytestmark = pytest.mark.integration  # (files on disk, the real MCP path)
SCENE = "packs/core_regions/scenes/start.json"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _lights(root: Path) -> list[dict]:
    return json.loads((root / SCENE).read_text(encoding="utf-8")).get("lights", [])


def _add(x: int, **extra: object) -> dict:
    return {"type": "add_light", "scene_path": SCENE, "light": {"x": x, "y": 10, **extra}}


def test_two_added_lights_each_keep_their_own_settings(root: Path) -> None:
    result = tools.apply_ops([_add(100, elevation=77), _add(200, elevation=88)], root=str(root))
    assert result["ok"], result
    lights = _lights(root)
    assert [(lt["x"], lt.get("elevation")) for lt in lights] == [(100.0, 77.0), (200.0, 88.0)]


def test_an_added_light_with_settings_after_a_delete_keeps_them(root: Path) -> None:
    assert tools.apply_ops([_add(1), _add(2), _add(3)], root=str(root))["ok"]
    result = tools.apply_ops([{"type": "delete_light", "scene_path": SCENE, "index": 0},
                              _add(400, elevation=99)], root=str(root))
    assert result["ok"], result
    assert [(lt["x"], lt.get("elevation")) for lt in _lights(root)] == [(2.0, None), (3.0, None), (400.0, 99.0)]


def test_a_batch_with_a_refused_light_setting_changes_no_file(root: Path) -> None:
    assert tools.apply_ops([_add(1)], root=str(root))["ok"]
    before = (root / SCENE).read_bytes()
    result = tools.apply_ops([_add(2, elevation=5), _add(3, elevation="nope")], root=str(root))
    assert not result["ok"]
    assert (root / SCENE).read_bytes() == before
