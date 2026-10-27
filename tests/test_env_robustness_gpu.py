"""Post-M20 repository health checkpoint, in the real renderer (hidden windows, GL-gated: MESH_GL_SMOKE=1): a room
whose 3D build fails part-way (a ground texture missing) plays 2D with the reason kept and leaves no GPU objects
behind; a scattered model that can't be read is set aside, the room stays 3D; a stroke of a casting model has the
lamps' shadow maps drawn again."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _project(tmp_path: Path, name: str, change: Callable[[dict, Path], None]) -> Path:
    import hd2d_visual_study as study

    project: Path = study.new_project(tmp_path, name, stage6a=False)
    path = project / study.SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    change(scene, project)
    path.write_text(json.dumps(scene), encoding="utf-8")
    return project


def test_a_room_whose_3d_build_fails_plays_2d_and_leaks_nothing(tmp_path: Path) -> None:
    from hd2d_demo import SCENES, HiddenGame, _gl_counts

    def missing_texture(scene: dict, _project: Path) -> None:
        scene["settings"]["hd2d"]["ground"]["texture"] = "assets/textures/not_here.png"

    game = HiddenGame(_project(tmp_path, "missing", missing_texture))
    try:
        counts = []
        for _ in range(5):
            game.load(f"{SCENES}/start.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            assert game.window.hd2d_renderer is None
            assert "not_here.png" in (game.window.hd2d_error or "")
            game.window.ctx.gc()
            counts.append(_gl_counts(game.window.ctx))
        assert counts[3:] == counts[2:-1], counts  # (steady from the third load: a cache fills once, nothing leaks)
    finally:
        game.close()


def test_an_unreadable_scattered_model_is_set_aside_and_lamps_follow_strokes(tmp_path: Path) -> None:
    from hd2d_demo import SCENES, HiddenGame

    def broken_boulder(scene: dict, project: Path) -> None:
        kit = project / "assets" / "hd2d_starter" / "scatter"
        kit.mkdir(parents=True, exist_ok=True)
        (kit / "boulder.glb").write_bytes(b"not a model")
        scene["settings"]["hd2d"]["scatter"] = {"grass_tuft": [[300, 200, 0, 100], [340, 210, 0, 100]],
                                                "boulder": [[420, 260, 0, 100]]}

    game = HiddenGame(_project(tmp_path, "broken", broken_boulder))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(2)
        game.window.dispatch_event("on_draw")
        hd = game.window.hd2d_renderer
        assert hd is not None and hd.scatter is not None and hd.scatter.count() == 3
        assert "boulder.glb" in (game.window.hd2d_scatter_error or "")
        assert hd.scatter.sprite_draws  # (the grass is drawn)
        hd.lighting._lamp_maps_ready = True
        hd.scatter.apply([("rock_medium", (380, 220, 0, 100), True)])  # (a casting model, as a stroke adds)
        assert hd.lighting._lamp_maps_ready is False
    finally:
        game.close()
