"""Milestone 18B: rain and snow meet the starter village (hidden windows, GL-gated: MESH_GL_SMOKE=1).

Shelter is judged in world space, not in pictures: a probe (tooling/m18b_weather_study.py) reads back every drawn
particle's world position with the camera's depth test off, and ray casts along each effect's own fall against the
village's real triangles check that no falling drop is under anything, that every splash or settling flake sits on a
surface with open sky above, and which surfaces they land on. With shelter switched off (Stage 18A's behaviour) the
same probe finds drops under the roofs and the bridge's deck: the negative control. Also: the dry cottage interior,
impacts that stay put as the camera moves, the maps' cache (invalidated by structure edits, a new one for a new
wind), failure recovery, the GL objects across room changes, and Mesh Studio's weather preview."""

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
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
SPOTS = [(8.0, 10.0, 1.0), (20.0, 22.0, 1.0)]  # the cottage and its terraces; the bridge, its stairs and underpass


def _game(out: Path, name: str, effects: list[dict]) -> Any:
    import hd2d_visual_study as study
    import m18_particles_study as m18

    game = study.HiddenGame(m18.make_project(out, name, effects), size=study.SIZE)
    game.load(f"{study.SCENES}/start.json")
    game.step(30)
    return game


def _judged(game: Any, *, shelter: bool = True) -> dict[str, Any]:
    import m18b_weather_study as weather

    hd = game.window.hd2d_renderer
    tris, owner, names = weather.triangles(hd)
    total: dict[str, Any] = {"landed_on": {}}
    for spot in SPOTS:
        hd.camera.target = spot
        for t in (5.0, 5.4):
            hd.particles.time = t
            for k, v in weather.judge(weather.probe(game, shelter=shelter), tris, owner, names).items():
                if isinstance(v, int):
                    total[k] = total.get(k, 0) + v
                elif k == "landed_on":
                    for s, n in v.items():
                        total["landed_on"][s] = total["landed_on"].get(s, 0) + n
    return total


@pytest.mark.parametrize("wind", [(0.8, 0.0), (4.0, 1.0)])
def test_rain_stops_at_roofs_and_decks_and_splashes_on_what_it_hits(tmp_path: Path, wind: tuple) -> None:
    game = _game(tmp_path, "rain", [{"preset": "rain", "count": 6000, "seed": 2, "wind": list(wind)}])
    try:
        sheltered = _judged(game)
        open_sky = _judged(game, shelter=False)  # Stage 18A: the negative control
    finally:
        game.close()
    assert open_sky["falling_under_shelter"] > 100, "18A: drops fall under the roofs and the bridge's deck"
    assert sheltered["falling"] > 5000 and sheltered["falling_under_shelter"] == 0, "18B: none under shelter"
    assert sheltered["landed"] > 500 and sheltered["landed_under_shelter"] == 0
    assert sheltered["landed_on_a_surface"] >= 0.99 * sheltered["landed"], "splashes sit on surfaces"
    on = sheltered["landed_on"]
    for surface in ("ground", "cottage", "bridge_6m", "platform_4m", "stairs"):  # roof, deck, terraces, steps
        assert on.get(surface, 0) > 0, (surface, on)


def test_snow_settles_on_surfaces_at_their_height_and_never_under_shelter(tmp_path: Path) -> None:
    game = _game(tmp_path, "snow", [{"preset": "snow", "count": 4000, "seed": 2}])
    try:
        snow = _judged(game)
    finally:
        game.close()
    assert snow["falling_under_shelter"] == 0 and snow["landed_under_shelter"] == 0
    assert snow["landed"] > 300 and snow["landed_on_a_surface"] >= 0.99 * snow["landed"]
    assert snow["landed_on"].get("cottage", 0) > 0 and snow["landed_on"].get("ground", 0) > 0


def test_impacts_stay_put_in_the_world_as_the_camera_moves(tmp_path: Path) -> None:
    import m18b_weather_study as weather

    game = _game(tmp_path, "anchor", [{"preset": "rain", "count": 6000, "seed": 2}])
    try:
        hd = game.window.hd2d_renderer
        hd.particles.time = 7.0
        hd.camera.target = (10.0, 12.0, 1.0)
        a = weather.probe(game)
        hd.camera.target = (11.5, 12.6, 1.0)
        b = weather.probe(game)
        hd.particles.time = 7.05
        c = weather.probe(game)
    finally:
        game.close()
    pa, pb, pc = (dict(zip(s["landed_ids"].tolist(), s["landed"])) for s in (a, b, c))
    both = [i for i in pa if i in pb]
    assert len(both) > 100 and all(abs(pa[i] - pb[i]).max() < 1e-4 for i in both), "the camera moved: same places"
    later = [i for i in pb if i in pc]
    assert len(later) > 50 and all(abs(pb[i] - pc[i]).max() < 0.03 for i in later), "a splash doesn't slide"


def test_the_cottage_interior_stays_dry(tmp_path: Path) -> None:
    import hd2d_visual_study as study

    project = study.new_project(tmp_path, "inside", stage6a=False)
    path = project / study.SCENES / "cottage.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    assert scene["settings"]["weather_exposure"] == "indoor", "the template's interior is indoors"
    scene["settings"]["particles"] = [{"preset": "rain"}, {"preset": "snow"}]
    path.write_text(json.dumps(scene), encoding="utf-8")
    game = study.HiddenGame(project, size=study.SIZE)
    try:
        game.load(f"{study.SCENES}/cottage.json")
        game.step(10)
        assert game.window.hd2d_renderer.particles is None
        assert "indoors" in game.window.scene_particles_notice
    finally:
        game.close()


def test_maps_are_cached_invalidated_by_structure_edits_and_made_anew_for_a_new_wind(tmp_path: Path) -> None:
    from hd2d_demo import _gl_counts

    from engine.scene_particles import parse_particles

    game = _game(tmp_path, "cache", [{"preset": "rain", "count": 3000}])
    try:
        hd, ctx = game.window.hd2d_renderer, game.window.ctx
        for _ in range(5):
            game.draw()
        assert hd.precipitation.builds == 1 and len(hd.precipitation.maps) == 1, "made once, then cached"
        st = hd.settings.structures[0]
        hd.set_live_ids([st.id])  # Studio starts dragging it
        game.draw()
        hd.set_live(st.id, st.x + 64, st.y, st.elevation, st.rotation, st.scale)
        game.draw()
        assert hd.precipitation.builds == 3, "each change to the structures draws the map again"
        before = set(hd.precipitation.maps)
        hd.set_particles(parse_particles([{"preset": "rain", "count": 3000, "wind": [5.0, 0.0]}]))
        game.draw()
        assert set(hd.precipitation.maps) != before and len(hd.precipitation.maps) == 1, "another wind, another map"
        ctx.gc()
        live = _gl_counts(ctx)
        hd.set_particles(())
        game.draw()
        ctx.gc()
        gone = _gl_counts(ctx)
        assert not hd.precipitation.maps and gone["texture"] == live["texture"] - 3, "map (2) and atlas (1) freed"
    finally:
        game.close()


def test_a_map_that_cant_be_made_leaves_the_rain_falling_as_in_18a(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hd2d_demo import _gl_counts

    game = _game(tmp_path, "fail", [{"preset": "rain", "count": 3000}])
    try:
        hd, ctx = game.window.hd2d_renderer, game.window.ctx
        hd.particles.set_enabled(0, False)
        game.draw()  # the frame's own target made (no map: nothing falls)
        hd.particles.set_enabled(0, True)
        ctx.gc()
        base = _gl_counts(ctx)
        real = ctx.framebuffer

        def broken(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("out of GPU memory (injected)")

        monkeypatch.setattr(ctx, "framebuffer", broken)
        picture = game.draw()
        monkeypatch.setattr(ctx, "framebuffer", real)
        assert picture is not None and hd.particles.draw_calls == 1, "the rain still falls"
        assert "injected" in hd.stats()["precipitation_error"] and not hd.precipitation.maps
        ctx.gc()
        assert _gl_counts(ctx)["texture"] == base["texture"], "what the failed map made is freed"
        game.draw()
        assert not hd.precipitation.maps, "not retried every frame"
        hd.precipitation.invalidate()  # e.g. the next structure edit
        game.draw()
        assert len(hd.precipitation.maps) == 1 and hd.stats()["precipitation_error"] is None
    finally:
        game.close()


def test_room_changes_keep_gpu_objects_level(tmp_path: Path) -> None:
    import hd2d_visual_study as study
    from hd2d_demo import _gl_counts

    game = _game(tmp_path, "rooms", [{"preset": "rain", "count": 3000}, {"preset": "snow", "count": 1000}])
    try:
        ctx, counts = game.window.ctx, []
        for _ in range(4):
            game.load(f"{study.SCENES}/cottage.json")
            game.step(3)
            game.draw()
            game.load(f"{study.SCENES}/start.json")
            game.step(3)
            game.draw()
            assert len(game.window.hd2d_renderer.precipitation.maps) == 2, "rain and snow: a map each"
            ctx.gc()
            counts.append({k: v for k, v in _gl_counts(ctx).items() if k != "buffer"})
        assert counts[1:] == counts[:-1], counts
    finally:
        game.close()


def test_studio_previews_the_weather_as_play_shows_it(tmp_path: Path) -> None:
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    import hd2d_studio_demo
    import m18_particles_study as m18

    project = m18.make_project(tmp_path, "studio", [{"preset": "rain", "count": 4000}])
    driver = hd2d_studio_demo.StudioDriver(project)
    try:
        hd = driver.renderer
        assert hd.particles is not None and driver.studio.hd2d.weather and driver.has_button("Preview weather: on")
        t0 = hd.particles.time
        wet = driver.frame(3).convert("RGB")
        assert hd.particles.time > t0, "the weather moves while editing"
        assert hd.precipitation.maps and hd.particles.draw_calls == 1, "drawn in the editing view, with shelter"
        driver.button("Preview weather: on")
        assert driver.has_button("Preview weather: off")
        hd.particles.time = t0  # the same moment, without the weather
        dry = driver.frame().convert("RGB")
        assert hd.particles.draw_calls == 0
        changed = sum(1 for p, q in zip(wet.getdata(), dry.getdata()) if p != q)
        assert changed > 2000, "the preview showed the rain"
        # the same renderer and camera draw the same weather in Studio's preview as in play (the pictures differ only
        # where play opens a cutaway round the player): each view's weather pixels, the same moment
        cam = driver.studio.hd2d.camera
        hd.weather_preview, hd.particles.time = True, 3.0

        def weather_pixels(camera: Any) -> set[int]:
            wet = hd.draw(camera=camera, read=True)
            hd.particles.set_enabled(0, False)
            dry = hd.draw(camera=camera, read=True)
            hd.particles.set_enabled(0, True)
            return {i for i in range(0, len(wet), 3) if wet[i:i + 3] != dry[i:i + 3]}

        studio_view = weather_pixels(cam)
        hd.camera.target, hd.camera.pitch, hd.camera.yaw = cam.target, cam.pitch, cam.yaw
        hd.camera.fov, hd.camera.distance, hd.camera.ortho = cam.fov, cam.distance, cam.ortho
        hd._camera_ready = True
        play_view = weather_pixels(None)
        same = len(studio_view & play_view) / max(1, len(studio_view | play_view))
        assert len(studio_view) > 2000 and same > 0.95, f"Studio's preview is play's weather ({same:.3f})"
    finally:
        driver.close()
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_studio_says_what_is_wrong_with_a_room_s_weather(tmp_path: Path) -> None:
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    import hd2d_studio_demo
    import m18_particles_study as m18

    project = m18.make_project(tmp_path, "bad", [{"preset": "hail"}])
    driver = hd2d_studio_demo.StudioDriver(project)
    try:
        driver.frame(2)
        assert not driver.studio.message_ok and "preset must be one of" in driver.studio.message
        assert "preset must be one of" in driver.studio._status_label.text
    finally:
        driver.close()
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_a_2d_room_s_rain_lands_on_its_ground_and_stays_on_its_map(tmp_path: Path) -> None:
    import numpy as np
    from hd2d_demo import HiddenGame

    from engine import scene_particles
    from engine.project_scaffold import create_project

    project = tmp_path / "Plain"
    create_project(project, "Plain", template_id="blank")
    path = project / "packs" / "core_regions" / "scenes" / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene.setdefault("settings", {})["particles"] = [{"preset": "rain", "count": 6000, "seed": 3}]
    path.write_text(json.dumps(scene), encoding="utf-8")
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load("packs/core_regions/scenes/start.json")
        game.step(60)
        game.draw()
        window, layer = game.window, game.window.scene_particles
        x0, y0, x1, y1 = layer.bounds
        ctx = window.ctx

        def probe() -> Any:
            colour = ctx.texture((1280, 720), components=4, dtype="f4")
            fbo = ctx.framebuffer(color_attachments=[colour])
            previous = ctx.active_framebuffer
            try:
                fbo.use()
                fbo.clear(color_normalized=(0.0, 0.0, 0.0, 1e9))
                layer.probe = True
                scene_particles.draw_2d(window)
                data = np.frombuffer(fbo.read(components=4, dtype="f4"), dtype=np.float32).reshape(-1, 4)
            finally:
                layer.probe = False
                previous.use()
                fbo.delete()
                colour.delete()
            return data[data[:, 3] < 1e8]

        kept = probe()
        layer.bounds = None  # the negative control: Stage 18A's 2D rain covered the whole view
        loose = probe()
        layer.bounds = (x0, y0, x1, y1)
    finally:
        game.close()
    flat = np.stack([kept[:, 0], kept[:, 1] + kept[:, 2]], axis=1)
    assert len(kept) > 500 and ((flat >= [x0 - 0.05, y0 - 0.05]) & (flat <= [x1 + 0.05, y1 + 0.05])).all(), "on the map"
    loose_flat = np.stack([loose[:, 0], loose[:, 1] + loose[:, 2]], axis=1)
    assert ((loose_flat < [x0, y0]) | (loose_flat > [x1, y1])).any(axis=1).sum() > 50, "18A: also off the map"
    landed = kept[kept[:, 3] < 0]
    assert len(landed) > 20 and np.allclose(landed[:, 2], 0.0, atol=1e-4), "splashes on the ground"
