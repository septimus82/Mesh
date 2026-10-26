"""Milestone 18A: a room's environmental particles (engine.scene_particles), headless: the settings, the seeds, the
box they fill, the pictures, and how a room load hands them out. The GPU drawing is tests/test_scene_particles_gpu.py."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from engine import scene_particles as sp

pytestmark = pytest.mark.fast


def test_presets_fill_in_what_a_room_leaves_out() -> None:
    rain, snow, wind = sp.parse_particles([{"preset": "rain"}, {"preset": "snow", "count": 50, "wind": [-1, 0.5]},
                                           {"preset": "wind", "gust": 0.9, "seed": 4, "enabled": False}])
    assert (rain.preset, rain.count, rain.wind, rain.enabled) == ("rain", sp.PRESETS["rain"].count, (0.8, 0.0), True)
    assert (snow.count, snow.wind) == (50, (-1.0, 0.5))
    assert (wind.gust, wind.seed, wind.enabled, wind.lifetime) == (0.9, 4, False, 6.0)
    assert sp.parse_particles(None) == () and sp.parse_particles([]) == ()


@pytest.mark.parametrize(("raw", "message"), [
    ({"preset": "rain"}, "list of effects"),
    ([{"preset": "hail"}], "preset must be one of"),
    ([{"preset": "rain", "count": 20001}], "count"),
    ([{"preset": "rain", "count": -1}], "count"),
    ([{"preset": "rain", "count": 2.5}], "count"),
    ([{"preset": "rain", "speed": float("nan")}], "speed"),
    ([{"preset": "rain", "wind": [1]}], "wind"),
    ([{"preset": "rain", "wind": [99, 0]}], "wind"),
    ([{"preset": "rain", "opacity": 2}], "opacity"),
    ([{"preset": "rain", "area": [1, 2]}], "area"),
    ([{"preset": "rain", "colour": "red"}], "unknown setting"),
    ([{"preset": "rain", "enabled": "yes"}], "enabled"),
    ([{"preset": "rain"}] * 5, "at most"),
])
def test_bad_settings_are_refused_with_the_reason(raw: Any, message: str) -> None:
    with pytest.raises(sp.SceneParticlesError, match=message):
        sp.parse_particles(raw)


def test_seeds_are_deterministic_and_in_range() -> None:
    effect = sp.parse_particles([{"preset": "wind", "count": 500, "seed": 9}])[0]
    a, b = sp.seeds(effect), sp.seeds(effect)
    assert a == b and len(a) == 500 * 6
    other = sp.seeds(sp.parse_particles([{"preset": "wind", "count": 500, "seed": 10}])[0])
    assert other != a, "another seed, another pattern"
    rows = [a[i:i + 6] for i in range(0, len(a), 6)]
    assert all(0 <= v < 1 for row in rows for v in row[:4])
    assert {int(row[4]) for row in rows} == set(range(len(sp.PRESETS["wind"].variants)))
    assert all(0.8 <= row[5] <= 1.2 for row in rows)


def test_the_box_follows_the_camera_and_reaches_south_for_high_particles() -> None:
    lo, size = sp.box_for_3d((20.0, 10.0, 0.8), 30.0, (30.0, 34.0, 12.0), ground=0.0)
    assert lo[0] == 5.0 and size[0] == 30.0 and lo[2] == 0.0 and size[2] == 12.0
    back = 12.0 / math.tan(math.radians(30.0))
    assert lo[1] == pytest.approx(10.0 - 17.0 - back) and size[1] == pytest.approx(34.0 + back)
    lo2, size2 = sp.box_for_2d((40.0, 20.0), (40.0, 22.5), (30.0, 34.0, 12.0))
    assert size2[0] == 44.0 and lo2[0] == 18.0, "a 2D room's box covers its view, whatever the area"
    assert size2[1] == pytest.approx(34.0 + 12.0)


def test_the_atlas_is_pixel_art() -> None:
    image = sp.atlas_image()
    assert image.size == (32, 24)
    alphas = set(image.getchannel("A").getdata())
    assert alphas <= {0, 255}, "binary alpha"
    for preset in sp.PRESETS.values():
        for x, y, w, h in preset.variants:
            box = image.crop((x, y, x + w, y + h)).getchannel("A")
            assert box.getbbox() is not None, (preset, (x, y, w, h))


class _Renderer:
    def __init__(self) -> None:
        self.effects: Any = None

    def set_particles(self, effects: Any, bounds: Any = None) -> None:
        self.effects, self.bounds = effects, bounds


def test_a_room_load_hands_particles_to_its_renderer_or_keeps_2d_rooms_untouched() -> None:
    hd2d = SimpleNamespace(hd2d_renderer=_Renderer(), ctx=None, scene_particles=None)
    sp.configure(hd2d, {"particles": [{"preset": "snow"}]})
    assert [e.preset for e in hd2d.hd2d_renderer.effects] == ["snow"] and hd2d.scene_particles is None

    plain = SimpleNamespace(hd2d_renderer=None, ctx=None, scene_particles=None)
    sp.configure(plain, {"world_width": 640})
    assert plain.scene_particles is None and plain.scene_particles_error is None, "a room without them: nothing"

    broken = SimpleNamespace(hd2d_renderer=None, ctx=None, scene_particles=None)
    sp.configure(broken, {"particles": [{"preset": "hail"}]})
    assert broken.scene_particles is None and "preset must be one of" in broken.scene_particles_error

    class _NoDriver:
        def set_particles(self, effects: Any, bounds: Any = None) -> None:
            raise RuntimeError("shader didn't compile")

    no_gl = SimpleNamespace(hd2d_renderer=_NoDriver(), ctx=None, scene_particles=None)
    sp.configure(no_gl, {"particles": [{"preset": "rain"}]})
    assert "didn't compile" in no_gl.scene_particles_error, "a driver that can't build them: the room still loads"


class _FakeGL:
    """A GL context whose ``fail_at``-th allocation fails; it records every object made and whether it was freed."""

    NEAREST, TRIANGLE_STRIP = 0, 5

    def __init__(self, fail_at: int) -> None:
        self.fail_at, self.made = fail_at, []

    def _make(self, kind: str) -> Any:
        if len(self.made) == self.fail_at:
            raise RuntimeError(f"no {kind} (driver)")
        obj = SimpleNamespace(kind=kind, freed=False, size=24, width=32, height=24)
        obj.delete = obj.flush = lambda o=obj: setattr(o, "freed", True)
        self.made.append(obj)
        return obj

    def program(self, **_: Any) -> Any:
        return self._make("program")

    def texture(self, *_: Any, **__: Any) -> Any:
        return self._make("texture")

    def buffer(self, **_: Any) -> Any:
        return self._make("buffer")

    def geometry(self, *_: Any, **__: Any) -> Any:
        return self._make("geometry")


_GL_MODULE = SimpleNamespace(BufferDescription=lambda *a, **k: None)


def test_a_layer_that_fails_part_way_frees_what_it_had_made() -> None:
    effects = sp.parse_particles([{"preset": "rain", "count": 10}, {"preset": "snow", "count": 0},
                                  {"preset": "wind", "count": 10}])
    whole = _FakeGL(fail_at=-1)
    layer = sp.ParticleLayer(whole, effects, gl=_GL_MODULE)  # program, texture, quad, 2 x (buffer, geometry)
    assert [o.kind for o in whole.made] == ["program", "texture", "buffer", "buffer", "geometry", "buffer", "geometry"]
    layer.release()
    layer.release()  # a second release does nothing
    assert all(o.freed for o in whole.made)
    for stage in range(7):  # the program, the texture, the quad, each seed buffer and each geometry failing
        gl = _FakeGL(fail_at=stage)
        with pytest.raises(RuntimeError, match="driver"):
            sp.ParticleLayer(gl, effects, gl=_GL_MODULE)
        assert len(gl.made) == stage and all(o.freed for o in gl.made), (stage, [(o.kind, o.freed) for o in gl.made])


def test_a_2d_room_whose_particles_fail_on_the_gpu_still_loads_without_them() -> None:
    window = SimpleNamespace(hd2d_renderer=None, ctx=_FakeGL(fail_at=2), scene_particles=None)
    sp.configure(window, {"particles": [{"preset": "snow", "count": 10}]})
    assert window.scene_particles is None and "driver" in window.scene_particles_error
    assert all(o.freed for o in window.ctx.made)


def test_a_room_s_particles_are_authored_checked_and_saved_in_its_settings() -> None:
    from engine import authoring
    from engine import project_ops as ops

    scene = {"settings": {"world_width": 640}, "entities": []}
    rainy = ops.set_particles(scene, [{"preset": "rain", "count": 1200}])
    assert rainy["settings"]["particles"] == [{"preset": "rain", "count": 1200}] and "particles" not in scene["settings"]
    with pytest.raises(ops.OpError, match="preset must be one of"):
        ops.set_particles(scene, [{"preset": "hail"}])
    assert "particles" not in ops.set_particles(rainy, [])["settings"], "an empty list removes them"
    assert "settings" not in ops.set_particles({"entities": []}, []), "and adds nothing to a room without settings"
    with pytest.raises(ops.OpError, match="aren't readable"):
        ops.set_particles({"settings": "odd"}, [{"preset": "rain"}])
    assert "set_particles" in authoring.operations(), "AI and Studio author them through the same checked edit"


# --- Milestone 18B: where rain and snow meet the world ------------------------------------------------------------


def test_precipitation_maps_are_keyed_by_the_fall_direction_quantised() -> None:
    from engine.hd2d.precipitation import STEP_DEG, direction_of, key_for

    assert key_for((0.0, 0.0, -9.0)) == (0.0, 0.0), "straight down"
    assert key_for((0.8, 0.0, -9.0)) == key_for((0.801, 0.0, -9.0)), "a hair's difference shares a map"
    assert key_for((0.8, 0.0, -9.0)) != key_for((1.0, 0.0, -9.0)), "a real change of wind makes another"
    assert key_for((0.8, 0.0, -9.0)) != key_for((-0.8, 0.0, -9.0)), "... and so does the wind turning"
    for fall in ((0.8, 0.0, -9.0), (4.0, 1.0, -9.0), (-3.0, 2.0, -1.1)):
        d = direction_of(key_for(fall))
        n = math.sqrt(sum(c * c for c in fall))
        angle = math.degrees(math.acos(sum(a * b / n for a, b in zip(d, fall))))
        assert angle <= STEP_DEG, (fall, angle)


def test_what_falls_and_how_far_its_impact_reaches() -> None:
    rain, snow, leaves, still = sp.parse_particles([{"preset": "rain", "wind": [1.0, 0.0]}, {"preset": "snow"},
                                                    {"preset": "wind"}, {"preset": "rain", "speed": 0}])
    assert sp.fall_of(rain) == (1.0, 0.0, -9.0) and sp.fall_of(snow) == (0.3, 0.0, -1.1)
    assert sp.fall_of(leaves) is None and sp.fall_of(still) is None, "leaves are carried, not falling"
    assert sp.impact_reach(rain) > 1.6 and sp.impact_reach(leaves) == 0.0
    assert sp.PRESETS["rain"].impact == 0.15 and sp.PRESETS["snow"].impact == 1.5 and sp.PRESETS["wind"].impact == 0.0


def test_the_splash_frames_are_pixel_art_in_the_atlas() -> None:
    image = sp.atlas_image()
    for x, y, w, h in sp.SPLASH:
        box = image.crop((x, y, x + w, y + h)).getchannel("A")
        assert box.getbbox() is not None and set(box.getdata()) <= {0, 255}


def test_an_indoor_room_gets_no_weather_and_says_why() -> None:
    assert sp.parse_exposure(None) == "outdoor" and sp.parse_exposure("indoor") == "indoor"
    with pytest.raises(sp.SceneParticlesError, match="weather_exposure"):
        sp.parse_exposure("cellar")
    hd2d = SimpleNamespace(hd2d_renderer=_Renderer(), ctx=None, scene_particles=None)
    sp.configure(hd2d, {"particles": [{"preset": "rain"}, {"preset": "snow"}], "weather_exposure": "indoor"})
    assert hd2d.hd2d_renderer.effects == () and "its rain and snow are not shown" in hd2d.scene_particles_notice
    bad = SimpleNamespace(hd2d_renderer=_Renderer(), ctx=None, scene_particles=None)
    sp.configure(bad, {"particles": [{"preset": "rain"}], "weather_exposure": "cellar"})
    assert "weather_exposure must be one of" in bad.scene_particles_error


def test_a_2d_room_keeps_its_particles_inside_its_map() -> None:
    window = SimpleNamespace(hd2d_renderer=None, ctx=_FakeGL(fail_at=-1), scene_particles=None)
    sp.configure(window, {"particles": [{"preset": "snow", "count": 0}], "world_width": 640, "world_height": 320})
    assert window.scene_particles.bounds == (0.0, 0.0, 20.0, 10.0)
    tilemap = {"width": 24, "height": 16, "tilewidth": 32, "tileheight": 32}
    sp.configure(window, {"particles": [{"preset": "snow", "count": 0}]}, {"tilemap": tilemap})
    assert window.scene_particles.bounds == (0.0, 0.0, 24.0, 16.0), "or its map's"
    sp.configure(window, {"particles": [{"preset": "snow", "count": 0}]})
    assert window.scene_particles.bounds is None, "no size at all: no rectangle to keep to"


def test_weather_changes_are_authored_checked_and_told_in_words() -> None:
    from engine import authoring
    from engine import project_ops as ops

    scene = {"settings": {"world_width": 640}, "entities": []}
    rainy = ops.set_particles(scene, [{"preset": "rain", "count": 3000, "wind": [0.8, -1]}])
    inside = ops.set_weather_exposure(rainy, "indoor")
    assert inside["settings"]["weather_exposure"] == "indoor"
    assert "weather_exposure" not in ops.set_weather_exposure(inside, "outdoor")["settings"], "outdoor: the default"
    with pytest.raises(ops.OpError, match="weather_exposure must be one of"):
        ops.set_weather_exposure(scene, "cellar")
    assert "set_weather_exposure" in authoring.operations()
    lines = authoring.summarize({"rooms": {"start": scene}}, {"rooms": {"start": inside}})
    assert "start: weather none -> rain x3000 (wind 0.8 east, 1 south m/s)" in lines, lines
    assert "start: weather exposure outdoor -> indoor" in lines


def test_an_hd2d_room_keeps_its_weather_inside_its_own_rectangle() -> None:
    hd2d = SimpleNamespace(hd2d_renderer=_Renderer(), ctx=None, scene_particles=None)
    sp.configure(hd2d, {"particles": [{"preset": "rain"}], "world_width": 1280, "world_height": 960})
    assert hd2d.hd2d_renderer.bounds == (0.0, 0.0, 40.0, 30.0), "the room's size, not only what it's built of"
    sp.configure(hd2d, {"particles": [{"preset": "rain"}]})
    assert hd2d.hd2d_renderer.bounds is None, "no size given: the renderer decides (its structures and ground)"


def test_a_bad_exposure_is_told_even_in_a_room_without_weather() -> None:
    window = SimpleNamespace(hd2d_renderer=None, ctx=None, scene_particles=None)
    sp.configure(window, {"weather_exposure": "cellar"})
    assert "weather_exposure must be one of" in window.scene_particles_error


def test_weather_changes_the_summary_words_leave_out_are_named() -> None:
    from engine import authoring

    lines = authoring._weather_lines("V", {"particles": [{"preset": "rain", "count": 4000}]},
                                     {"particles": [{"preset": "rain", "count": 4000, "opacity": 0.3}]})
    assert lines == ["V: weather rain x4000: changes opacity"]
    assert authoring._weather_lines("V", {}, {"particles": [{"preset": "wind", "count": 200, "wind": [0, 0]}]}) == [
        "V: weather none -> leaves x200 (no wind)"]


@pytest.mark.parametrize(("asked", "kept", "named"), [
    (["rain"], [], "its rain is not shown"),
    (["snow"], [], "its snow is not shown"),
    (["wind"], ["wind"], None),
    (["rain", "wind", "snow"], ["wind"], "its rain and snow are not shown"),
])
def test_indoors_only_rain_and_snow_are_kept_out(asked: list[str], kept: list[str], named: str | None) -> None:
    effects = [{"preset": p, "count": 0} for p in asked]
    hd2d = SimpleNamespace(hd2d_renderer=_Renderer(), ctx=None, scene_particles=None)
    sp.configure(hd2d, {"particles": effects, "weather_exposure": "indoor"})
    assert [e.preset for e in hd2d.hd2d_renderer.effects] == kept, "HD-2D: only what isn't precipitation stays"
    assert (hd2d.scene_particles_notice is None) if named is None else (named in hd2d.scene_particles_notice)
    flat = SimpleNamespace(hd2d_renderer=None, ctx=_FakeGL(fail_at=-1), scene_particles=None)
    sp.configure(flat, {"particles": effects, "weather_exposure": "indoor"})
    layer = flat.scene_particles
    assert ([e.preset for e in layer.effects] if layer is not None else []) == kept, "2D: the same"
    outside = SimpleNamespace(hd2d_renderer=_Renderer(), ctx=None, scene_particles=None)
    sp.configure(outside, {"particles": effects})
    assert [e.preset for e in outside.hd2d_renderer.effects] == asked and outside.scene_particles_notice is None
