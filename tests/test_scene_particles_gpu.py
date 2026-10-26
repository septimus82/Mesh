"""Milestone 18A: environmental particles in the real renderer, hidden windows (GL-gated: MESH_GL_SMOKE=1).

In the HD-2D RPG template's village with rain: the particles are drawn in its 3D world (one draw call), depth-tested
(the buildings and characters in front of a particle hide it), anchored to the world as the camera moves (not a screen
overlay), the same picture for the same time, and their GPU objects are freed on every room change. A 2D room that
asks for snow draws it; one that doesn't is untouched."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _with_particles(project: Path, room: str, effects: list[dict]) -> None:
    path = project / "packs" / "core_regions" / "scenes" / room
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene.setdefault("settings", {})["particles"] = effects
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")


def _mask(a: Any, b: Any) -> list[bool]:
    return [pa != pb for pa, pb in zip(a.getdata(), b.getdata())]


@pytest.fixture(scope="module")
def village(tmp_path_factory: pytest.TempPathFactory) -> Any:
    import hd2d_visual_study as study

    out = tmp_path_factory.mktemp("particles")
    project = study.new_project(out, "project", stage6a=False)
    _with_particles(project, "start.json", [{"preset": "rain", "count": 3000, "seed": 3}])
    game = study.HiddenGame(project, size=study.SIZE)
    game.load(f"{study.SCENES}/start.json")
    game.step(90)
    yield game
    game.close()


def test_rain_is_drawn_in_the_world_depth_tested_in_one_draw_call(village: Any) -> None:
    hd = village.window.hd2d_renderer
    layer = hd.particles
    assert layer is not None and hd.stats()["particles"] == 3000
    with_rain = village.draw().convert("RGB")
    calls_with = hd.stats()["draw_calls"]
    layer.set_enabled(0, False)
    try:
        dry = village.draw().convert("RGB")
        calls_without = hd.stats()["draw_calls"]
    finally:
        layer.set_enabled(0, True)
    layer.depth_test = False
    try:
        no_depth = village.draw().convert("RGB")
    finally:
        layer.depth_test = True
    assert calls_with - calls_without == 1, "every particle in one draw call"
    shown, unhidden = _mask(with_rain, dry), _mask(no_depth, dry)
    drawn, hidden = sum(shown), sum(1 for s, u in zip(shown, unhidden) if u and not s)
    assert drawn > 5000, "rain is drawn"
    assert hidden > 500, "particles behind buildings, hills and characters are hidden by them"
    assert village.draw().convert("RGB").tobytes() == with_rain.tobytes(), "the same time, the same picture"


def test_particles_stay_put_in_the_world_as_the_camera_moves(village: Any) -> None:
    import hd2d_visual_study as study

    hd = village.window.hd2d_renderer
    layer, camera = hd.particles, hd.camera
    base = camera.target

    def frame(dx: float) -> tuple[list[bool], float]:
        camera.target = (base[0] + dx, base[1], base[2])
        layer.set_enabled(0, False)
        dry = village.draw().convert("RGB")
        layer.set_enabled(0, True)
        wet = village.draw().convert("RGB")
        vp = camera.view_projection(study.SIZE[0] / study.SIZE[1])
        p = (base[0], base[1], 2.0, 1.0)  # a world point: where it shows in this picture
        c = [sum(vp[r][k] * p[k] for k in range(4)) for r in range(4)]
        return _mask(wet, dry), (c[0] / c[3] * 0.5 + 0.5) * study.SIZE[0]

    try:
        (a, xa), (b, xb) = frame(0.0), frame(0.15)
    finally:
        camera.target = base
    shift = round(xb - xa)  # the world moves this many pixels across the picture
    assert shift <= -8, "the camera moved east, so the world moves west in the picture"
    w = study.SIZE[0]

    def overlap(dx: int, slack: int = 3) -> float:
        """How many of the first picture's particle pixels, moved ``dx`` across, land within ``slack`` px of one in
        the second (a near particle moves a little more than a far one: perspective)."""
        hits = total = 0
        for i, on in enumerate(a):
            if not on:
                continue
            x = i % w + dx
            if slack <= x < w - slack:
                total += 1
                row = i - i % w
                hits += any(b[row + x + d] for d in range(-slack, slack + 1))
        return hits / max(1, total)

    assert overlap(shift) > 0.8, "the particles moved with the world"
    assert overlap(0) < 0.3, "not a screen overlay: staying put on screen doesn't match"


def test_room_changes_free_every_particle_gl_object(village: Any) -> None:
    import hd2d_visual_study as study
    from hd2d_demo import _gl_counts

    ctx = village.window.ctx
    counts = []
    for _ in range(4):
        village.load(f"{study.SCENES}/cottage.json")  # no particles indoors
        village.step(5)
        village.draw()
        assert village.window.hd2d_renderer.particles is None
        village.load(f"{study.SCENES}/start.json")
        village.step(5)
        village.draw()
        ctx.gc()
        counts.append({k: v for k, v in _gl_counts(ctx).items() if k != "buffer"})
    assert counts[1:] == counts[:-1], f"textures, programs and framebuffers stable over room changes: {counts}"
    layer = village.window.hd2d_renderer.particles
    objects = layer.gl_objects()
    village.window.hd2d_renderer.set_particles(())
    assert village.window.hd2d_renderer.particles is None and all(getattr(o, "_glo", None) in (None, 0) or
                                                                   getattr(getattr(o, "_glo", None), "value", 0) == 0
                                                                   for o in objects), "released"
    layer.release()  # a second release does nothing


def test_a_2d_room_draws_particles_only_when_it_asks(tmp_path: Path) -> None:
    from hd2d_demo import HiddenGame

    from engine.project_scaffold import create_project

    project = tmp_path / "Plain"
    create_project(project, "Plain", template_id="blank")
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load("packs/core_regions/scenes/start.json")
        game.step(30)
        assert getattr(game.window, "scene_particles", None) is None, "a 2D room without particles: untouched"
        plain = game.draw().convert("RGB")
        _with_particles(project, "start.json", [{"preset": "snow", "count": 1500}])
        game.load("packs/core_regions/scenes/start.json")
        game.step(30)
        layer = game.window.scene_particles
        assert layer is not None
        snowy = game.draw().convert("RGB")
        layer.set_enabled(0, False)
        cleared = game.draw().convert("RGB")
    finally:
        game.close()
    assert sum(_mask(snowy, cleared)) > 1000, "a 2D room that asks for snow draws it over its map"
    assert cleared.tobytes() == plain.tobytes() or sum(_mask(cleared, plain)) < 50, "and nothing else changes"
