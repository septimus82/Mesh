"""Loading a lit 2D room again frees the previous room's light layer at once (post-M16 health check). The layer's
lights point back at it, so before, each load left its textures, framebuffers and programs for Python's cycle
collector. Hidden window. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import gc
import json
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

REPO = Path(__file__).resolve().parents[1]
SCENE = "packs/core_regions/scenes/start.json"


def test_reloading_a_lit_room_frees_the_old_light_layer(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "tooling"))
    from hd2d_demo import HiddenGame

    from engine.project_scaffold import create_project

    project = tmp_path / "lit"
    create_project(project, "lit", "blank")
    scene = json.loads((project / SCENE).read_text(encoding="utf-8"))
    scene["lights"] = [{"id": "a", "x": 200, "y": 200, "radius": 150, "color": "#ffb060", "mode": "soft"}]
    scene.setdefault("settings", {})["lighting_enabled"] = True
    (project / SCENE).write_text(json.dumps(scene), encoding="utf-8")
    game = HiddenGame(project)
    try:
        ctx = game.window.ctx
        game.load(SCENE)
        assert game.window.lighting._layer is not None, "the room is lit"

        def live() -> tuple[int, ...]:
            ctx.gc()
            return tuple(getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in ("texture", "framebuffer", "program"))

        gc.collect()
        gc.disable()  # only explicit releases and reference counting may free anything now
        try:
            before = live()
            old = game.window.lighting._layer
            for _ in range(5):
                game.load(SCENE)
                game.step(1)
            after = live()
        finally:
            gc.enable()
        assert after == before, f"live (textures, framebuffers, programs) {before} -> {after}"
        assert old._lights == [] and old._fbo.color_attachments[0]._glo.value == 0, "the old layer was released"
    finally:
        game.close()
