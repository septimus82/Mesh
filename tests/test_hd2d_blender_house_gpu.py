"""M2-1 in a hidden window: the Blender house imported into a new HD-2D RPG project, placed twice and drawn, then
reimported after its Blender edit and drawn again (tooling/hd2d_assets/house_reimport_evidence.py). Both copies'
roofs turn from slate to terracotta, only the model's three files change, and a cut-off export is refused with the
project unchanged. GL-gated: set MESH_GL_SMOKE=1."""

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
]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tooling" / "hd2d_assets"))


def _roofs(path: Path) -> tuple[int, int]:
    """Pixels of the lit slate roof (about 79, 83, 93) and of the lit terracotta roof (about 167, 77, 45)."""
    from PIL import Image

    with Image.open(path) as image:
        pixels = list(image.convert("RGB").getdata())
    slate = sum(1 for r, g, b in pixels if abs(r - 79) < 20 and abs(g - 83) < 20 and r < b < r + 30)
    terracotta = sum(1 for r, g, b in pixels if r > 140 and r - g > 70 and r - b > 90)
    return slate, terracotta


def test_the_reimported_house_is_drawn_with_its_edit(tmp_path: Path) -> None:
    import house_reimport_evidence as evidence

    scratch = tmp_path / "user"
    scratch.mkdir()
    with pytest.MonkeyPatch.context() as env:  # the snapshot changes folder and settings paths: undone after
        env.chdir(tmp_path)
        for name in ("MESH_USER_DIR", "MESH_PROJECTS_DIR", "APPDATA"):
            env.setenv(name, str(scratch))
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        report = evidence.check(tmp_path / "run")

    slate, terracotta = _roofs(tmp_path / "run" / "before.png")
    assert slate > 10_000 and terracotta == 0, (slate, terracotta)
    slate, terracotta = _roofs(tmp_path / "run" / "after.png")
    assert slate == 0 and terracotta > 20_000, (slate, terracotta)
    assert report["reimport_changed"] == ["assets/models/catalog.json", "assets/models/house.glb",
                                          "assets/models/previews/house.png"]
    assert "Collider 'col_wall_north' (wall) changed shape." in report["plan"]["changes"]
    assert report["plan"]["wrote"] == []
    assert report["broken"]["refused"] and report["broken"]["project_unchanged"]
