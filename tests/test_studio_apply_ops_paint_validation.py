"""A-05b: ``apply_ops`` paint_tiles on a Studio project refuses what the direct path refuses, cleanly.

Before: ``int(cell["col"])`` raised a raw ValueError/TypeError on non-numeric input, floats and bools were truncated
(``int(2.7)`` -> 2, ``int(True)`` -> 1), and the batch size was uncapped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.ai_ops import MAX_PAINT_TILE_OPS
from engine.mcp_server import tools
from engine.project_scaffold import create_project

pytestmark = pytest.mark.integration
SCENE = "packs/core_regions/scenes/start.json"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _paint(*cells: dict) -> list[dict]:
    return [{"type": "paint_tiles", "scene_path": SCENE, "ops": list(cells)}]


BAD = {
    "non-numeric col": [{"layer": "ground", "col": "x", "row": 0, "gid": 1}],
    "float col": [{"layer": "ground", "col": 2.7, "row": 0, "gid": 1}],
    "bool row": [{"layer": "ground", "col": 0, "row": True, "gid": 1}],
    "negative gid": [{"layer": "ground", "col": 0, "row": 0, "gid": -1}],
    "null layer": [{"layer": None, "col": 0, "row": 0, "gid": 1}],
    "empty layer": [{"layer": "", "col": 0, "row": 0, "gid": 1}],
    "not an object": ["nope"],
    "oversized batch": [{"layer": "ground", "col": 0, "row": 0, "gid": 1}] * (MAX_PAINT_TILE_OPS + 1),
}


@pytest.mark.parametrize("cells", BAD.values(), ids=BAD.keys())
def test_invalid_paint_cells_are_refused_cleanly(root: Path, cells: list) -> None:
    before = (root / SCENE).read_bytes()
    result = tools.apply_ops(_paint(*cells), root=str(root))
    assert result["ok"] is False
    assert "paint_tiles" in result["message"]
    assert (root / SCENE).read_bytes() == before


def test_valid_batch_still_paints(root: Path) -> None:
    before = (root / SCENE).read_bytes()
    result = tools.apply_ops(_paint({"layer": "ground", "col": 1, "row": 1, "gid": 3}), root=str(root))
    assert result["ok"], result
    assert (root / SCENE).read_bytes() != before
