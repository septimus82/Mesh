"""#462 R3 with Mesh Studio's own River tool, in a hidden Studio window driven by its own input events (GL-gated:
MESH_GL_SMOKE=1): a river drawn, removed with Delete, and another drawn gets a new id, never the removed one's.
The tool picks a new river's id before the river is saved (``RiverTool._new_id``, when the first point is clicked),
outside the edit that saves it, so this is the tool's own path. Everything else: tests/test_studio_object_identity.py.
"""

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
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def test_the_river_tool_never_gives_a_removed_rivers_id_to_the_next_one(tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    import r1_river_study as r1
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
    project = r1.make_project(tmp_path, "identity", rivers=False)  # the beds, sculpted; no river yet
    d = StudioDriver(project)
    try:
        k, view = d.arcade.key, d.studio.hd2d
        terrain = d.renderer.terrain

        def draw() -> str:
            for x, y, _w, _l in r1.NORTH:  # clicked on the bed, upstream to downstream; Enter finishes
                d.click(*d.screen((x / 32, y / 32, terrain.surface_at(x, y)[0] / 32)))
            d.key(k.ENTER)
            d.advance(2)
            (river,) = ops.rivers(d.studio.project.scene())
            return str(river["id"])

        d.button("Terrain")
        d.button("River")
        view.camera.target = (20.0, 24.0, 0.0)
        d.advance(2)
        drawn: list[str] = []
        for _ in range(3):
            drawn.append(draw())
            assert view.river.selected == drawn[-1]  # (the river just drawn is selected: Delete removes it)
            d.key(k.DELETE)
            d.advance(2)
            assert ops.rivers(d.studio.project.scene()) == []
        assert drawn == ["river", "river-2", "river-3"], drawn
        assert d.studio.project.undo()  # the last removal undone: that very river, its id, back
        assert [r["id"] for r in ops.rivers(d.studio.project.scene())] == ["river-3"]
    finally:
        d.close()
