"""Milestone 20E: the room's wind (engine.wind) and its decoration's motion (engine.hd2d.motion): settings, the shared
gust fronts, how plants lean and flutter (the shader's twin), frames, the motion tables, the ops and their words."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine import project_ops as ops
from engine.hd2d import motion as m
from engine.hd2d.scatter import ASSETS, FIRST_MOTION, SLOTS
from engine.wind import CALM, PERIOD, W1, W2, W3, Wind, WindError, gust_wave, parse_wind, speed_at

pytestmark = pytest.mark.fast


def _room(**settings: object) -> dict:
    return {"settings": {"hd2d": {}, **settings}, "entities": []}


# ---------------------------------------------------------------------- the wind
def test_wind_settings_are_checked_and_calm_by_default() -> None:
    assert parse_wind(None) is CALM and CALM.calm
    wind = parse_wind({"speed": 4, "direction": 90, "gust": 0.5})
    assert wind.vector[0] == pytest.approx(0.0, abs=1e-9) and wind.vector[1] == pytest.approx(4.0)
    assert parse_wind({"speed": 2, "direction": -90}).direction == 270.0
    for bad in ({"speed": 31}, {"gust": 2}, {"speed": "fast"}, {"speed": True}, {"blow": 1}, [1, 2]):
        with pytest.raises(WindError):
            parse_wind(bad)


def test_gusts_are_fronts_moving_with_the_wind_bounded_and_seamless_at_the_wrap() -> None:
    wind = Wind(5.0, 30.0, 0.8)
    d = (math.cos(math.radians(30)), math.sin(math.radians(30)))
    for t in (0.0, 3.7, 120.0):
        g = gust_wave(10.0, 4.0, t, wind)
        assert -1.0 <= g <= 1.0
        # a front 10 m downwind arrives there 10 / 5 s later
        assert gust_wave(10.0 + 10 * d[0], 4.0 + 10 * d[1], t + 2.0, wind) == pytest.approx(g, abs=1e-9)
        assert gust_wave(3.0, 9.0, t + PERIOD, wind) == pytest.approx(gust_wave(3.0, 9.0, t, wind), abs=1e-6)
    assert [w * PERIOD / (2 * math.pi) for w in (W1, W2, W3)] == pytest.approx([401, 649, 1440])
    assert abs(W1 - 0.7) < 1e-3  # (the particles' swell)
    speeds = [speed_at(0.0, 0.0, t * 0.5, wind) for t in range(400)]
    assert min(speeds) >= 0.0 and sum(speeds) / len(speeds) == pytest.approx(5.0, rel=0.1)
    assert speed_at(0.0, 0.0, 5.0, CALM) == 0.0


def test_particles_take_the_rooms_wind_unless_they_have_their_own() -> None:
    from engine.scene_particles import PRESETS, parse_particles

    room = Wind(4.0, 180.0, 0.3)
    own, inherit = parse_particles([{"preset": "rain", "wind": [1.0, 0.0], "gust": 0.1}, {"preset": "snow"}], room)
    assert own.wind == (1.0, 0.0) and own.gust == 0.1
    assert inherit.wind[0] == pytest.approx(-4.0) and inherit.gust == 0.3
    # a calm room (every room before 20E): the presets', as before
    (old,) = parse_particles([{"preset": "rain"}], CALM)
    assert old.wind == PRESETS["rain"].wind and old.gust == PRESETS["rain"].gust
    assert parse_particles([{"preset": "rain"}]) == (old,)


# ---------------------------------------------------------------------- motion settings
def test_motion_settings_are_checked_and_off_without_a_block() -> None:
    assert m.parse_motion(None) == m.OFF and not m.OFF.enabled
    on = m.parse_motion({})
    assert on.enabled and on.sway == 1.0
    tuned = m.parse_motion({"sway": 1.5, "assets": {"torch": {"fps": 12, "loop": "pingpong", "phase": 0}}})
    assert tuned.of("torch") == m.AssetMotion(fps=12.0, loop="pingpong", phase=0.0) and tuned.of("reeds") == m.AssetMotion()
    for bad in ({"sway": 3}, {"speed": 0.1}, {"enabled": 1}, {"assets": {"oak": {}}}, {"assets": {"torch": {"fps": 0}}},
                {"assets": {"torch": {"loop": "bounce"}}}, {"jitter": 1}, []):
        with pytest.raises(m.MotionError):
            m.parse_motion(bad)


def test_old_rooms_parse_as_still_and_a_bad_block_is_set_aside_leniently() -> None:
    from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

    assert parse_hd2d({}).motion == m.OFF
    lenient = parse_hd2d({"motion": {"sway": 9}}, lenient=True)
    assert lenient.motion == m.OFF and "sway" in (lenient.motion_error or "")
    with pytest.raises(Hd2dSettingsError):
        parse_hd2d({"motion": {"sway": 9}})


# ---------------------------------------------------------------------- how a plant moves
def test_a_plant_is_still_when_motion_is_off_and_never_leans_into_the_ground() -> None:
    wind = Wind(30.0, 40.0, 1.0)
    assert m.angle(1.0, 2.0, 50.0, 1.0, 0.3, wind, m.OFF) == (0.0, 0.0)
    wild = m.Motion(enabled=True, sway=2.0, wind=2.0, speed=3.0)
    angles = [m.angle(x * 0.7, 0.0, t * 0.13, 1.0, (x * 0.37) % 1, wind, wild) for x in range(20) for t in range(300)]
    assert max(abs(a) for a, _d in angles) <= m.MAX_ANGLE and max(abs(d) for _a, d in angles) <= m.MAX_DEPTH
    # the tip of a plant on the steepest slope a plant may stand on (35 degrees), leaning downhill as far as it can
    # both ways at once, stays above it
    across, depth = m.MAX_ANGLE, m.MAX_DEPTH
    reach = math.hypot(math.sin(across), math.sin(depth))
    assert math.cos(across) * math.cos(depth) > reach * math.tan(math.radians(35.0))


def test_plants_lean_with_the_wind_as_the_camera_sees_it() -> None:
    on = m.Motion(enabled=True)
    sideways, toward_camera = Wind(9.0, 0.0, 0.0), Wind(9.0, 270.0, 0.0)
    across, depth = m.angle(0.0, 0.0, 3.0, 1.0, 0.0, sideways, on)
    assert across > 0.15 and depth == 0.0
    across, depth = m.angle(0.0, 0.0, 3.0, 1.0, 0.0, toward_camera, on)
    assert abs(across) < 0.15 and -m.MAX_DEPTH <= depth < -0.1  # (toward the camera: a little, never squashed)
    # the camera turned a quarter (its right is north): the north wind now leans plants across the picture
    across, depth = m.angle(0.0, 0.0, 3.0, 1.0, 0.0, Wind(9.0, 90.0, 0.0), on, right=(0.0, 1.0))
    assert across > 0.15 and abs(depth) < 1e-9


def test_the_clock_wraps_seamlessly_at_any_speed() -> None:
    for speed in (0.25, 1.0, 1.1, 1.5, 3.0):
        for seed in (0.0, 0.31, 0.77, 0.999):
            turns = m.flutter_rate(seed, speed) * PERIOD
            assert turns == pytest.approx(round(turns), abs=1e-6)
    for fps, frames, pingpong in ((9 * 1.234, 4, False), (2.0 * 1.1, 3, True), (6.0, 4, False), (1.5, 2, False)):
        safe = m.wrap_safe_fps(fps, frames, pingpong)
        assert abs(safe - fps) * PERIOD < 2 * frames  # (under a cycle an hour)
        f = [m.frame(t, 0.4, frames, safe, 1.0, pingpong) for t in (0.0, PERIOD)]
        assert f[0] == f[1]


def test_neighbours_move_out_of_step_and_grass_moves_more_than_a_tree_later() -> None:
    on = m.Motion(enabled=True)
    breeze = Wind(4.0, 0.0, 0.5)
    seeds = [m.seed_of(x, 320) for x in range(320, 352, 4)]
    assert len({round(s, 4) for s in seeds}) == len(seeds)  # (each its own)

    def series(x: float, flex: float, seed: float) -> list[float]:
        return [m.angle(x, 10.0, t / 30, flex, seed, CALM, on)[0] for t in range(600)]

    a, b = series(10.0, 1.0, seeds[0]), series(10.125, 1.0, seeds[1])
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    cov = sum((p - mean_a) * (q - mean_b) for p, q in zip(a, b))
    norm = math.sqrt(sum((p - mean_a) ** 2 for p in a) * sum((q - mean_b) ** 2 for q in b))
    assert abs(cov / norm) < 0.9  # (two tufts 12 cm apart don't sway together)
    grass = [abs(m.angle(10.0, 10.0, t / 30, ASSETS["grass_tall"].flex, 0.4, breeze, on)[0]) for t in range(900)]
    tree = [abs(m.angle(10.0, 10.0, t / 30, ASSETS["tree_small"].parts[0].flex, 0.4, breeze, on)[0])
            for t in range(900)]
    assert sum(grass) > 2 * sum(tree)
    assert m.lag(ASSETS["tree_small"].parts[0].flex) > m.lag(ASSETS["reeds"].flex)
    # stronger wind, further over
    assert m.lean(9.0) > m.lean(3.0) > m.lean(0.0) == 0.0


def test_frames_loop_or_ping_pong() -> None:
    assert [m.frame(t / 4, 0.0, 4, 4.0, 0.0, False) for t in range(9)] == [0, 1, 2, 3, 0, 1, 2, 3, 0]
    assert [m.frame(t / 3, 0.0, 3, 3.0, 0.0, True) for t in range(7)] == [0, 1, 2, 1, 0, 1, 2]
    assert m.frame(5.0, 0.5, 1, 9.0, 1.0, False) == 0
    # phase variation 0: all together; 1: offsets by where they stand
    assert {m.frame(1.0, s, 4, 4.0, 0.0, False) for s in (0.1, 0.5, 0.9)} == {0}
    assert len({m.frame(1.0, s, 4, 4.0, 1.0, False) for s in (0.1, 0.4, 0.6, 0.9)}) > 1


def test_the_clock_is_the_sum_of_the_steps_at_any_frame_rate() -> None:
    from engine.hd2d.renderer import Hd2dRenderer

    class Clock:  # (the renderer's clock alone)
        motion_time = Hd2dRenderer.motion_time
        advance_motion = Hd2dRenderer.advance_motion

        def __init__(self) -> None:
            self.window = SimpleNamespace(motion_time=0.0)

    totals = []
    for rate in (30, 60, 144):
        clock = Clock()
        for _ in range(rate * 10):
            clock.advance_motion(1 / rate)
        totals.append(clock.window.motion_time)
    assert totals == pytest.approx([10.0] * 3, abs=1e-9)


# ---------------------------------------------------------------------- assets, sheets and the shader's tables
def test_every_sprite_part_has_a_slot_and_its_frames_are_in_the_sheets() -> None:
    from PIL import Image

    from engine.hd2d.scatter import KIT, MOTION_SHEET, SHEET
    from engine.repo_root import bundled_file

    first, second = (Image.open(bundled_file(p)) for p in (SHEET, MOTION_SHEET))
    assert first.width // 48 == FIRST_MOTION  # (20D's sheet: exactly as it was)
    cells = FIRST_MOTION + second.width // 48
    for asset in ASSETS.values():
        for number, part in asset.sprite_parts():
            assert (asset.id, number) in SLOTS
            cell, frames = ((asset.cell or (0,))[-1], asset.frames) if part is None else (part.cell, part.frames)
            assert cell + frames <= cells, asset.id
        if asset.model:
            assert bundled_file(asset.model) is not None and asset.model.startswith(KIT)
    assert sorted(SLOTS.values()) == list(range(len(SLOTS)))


def test_the_motion_tables_carry_each_parts_motion_and_the_rooms_own_settings() -> None:
    from engine.hd2d.scatter_layer import ScatterLayer

    def tables(motion: m.Motion, wind: Wind = CALM) -> list[list[tuple[float, ...]]]:
        out = ScatterLayer._slot_tables(cast(Any, SimpleNamespace(motion=motion, wind=wind)))
        return [[t[i:i + 4] for i in range(0, len(t), 4)] for t in out]

    a, b, c = tables(m.Motion(enabled=True, speed=2.0))
    flame = SLOTS[("torch", 1)]
    assert a[flame] == (0.45, 6.0, 20.0, 1.0) and b[flame] == (1.0, 0.0, 1.0, 0.0)
    assert c[flame] == (1.0, 0.05, 0.0, 0.0)  # (20E's sheet; drawn nearer the camera than the post)
    assert c[SLOTS[("tree_small", 1)]][2] == 1.2 and c[SLOTS[("banner", 1)]][3] == 4.0  # (canopy light; limp cell)
    assert c[SLOTS[("grass_tuft", 0)]] == (0.0, 0.0, 0.0, 0.0)  # (20D's: as it was)
    banner = SLOTS[("banner", 1)]
    assert tables(m.Motion(enabled=True), Wind(10.0))[0][banner][2] > tables(m.Motion(enabled=True), Wind(2.0))[0][banner][2]
    assert b[SLOTS[("banner", 1)]][3] == 1.0 and b[SLOTS[("bellflowers", 0)]][1] == 1.0
    assert a[SLOTS[("torch", 0)]][1] == 1.0  # (the post: no frames)
    tuned = m.parse_motion({"assets": {"torch": {"fps": 5, "enabled": False, "loop": "pingpong", "phase": 0},
                                       "reeds": {"sway": 2}}})
    a, b, _c = tables(tuned)
    assert a[flame] == (0.45, 6.0, 5.0, 0.0) and b[flame][1:3] == (1.0, 0.0)
    assert a[SLOTS[("reeds", 0)]][0] == pytest.approx(2 * ASSETS["reeds"].flex)


# ---------------------------------------------------------------------- the ops and their words
def test_set_wind_and_set_motion_write_only_what_differs_from_an_old_room() -> None:
    from engine.authoring import _motion_lines

    room = _room()
    windy = ops.set_wind(room, speed=6, direction=45, gust=0.5)
    assert windy["settings"]["wind"] == {"speed": 6.0, "direction": 45.0, "gust": 0.5}
    assert "wind" not in ops.set_wind(windy, speed=0)["settings"]
    with pytest.raises(ops.OpError):
        ops.set_wind(room, speed=40)
    on = ops.set_motion(room, enabled=True)
    assert on["settings"]["hd2d"]["motion"] == {}
    tuned = ops.set_motion(on, sway=1.4, assets={"torch": {"fps": 12}})
    assert tuned["settings"]["hd2d"]["motion"] == {"sway": 1.4, "assets": {"torch": {"fps": 12}}}
    off = ops.set_motion(tuned, enabled=False)
    assert off["settings"]["hd2d"]["motion"]["enabled"] is False  # (its settings kept for when it's on again)
    assert "motion" not in ops.set_motion(on, enabled=False)["settings"]["hd2d"]  # (nothing set: as older rooms)
    with pytest.raises(ops.OpError):
        ops.set_motion(room, assets={"oak": {}})
    with pytest.raises(ops.OpError):
        ops.set_motion({"settings": {}, "entities": []}, enabled=True)
    assert _motion_lines("Hills", room["settings"], windy["settings"]) == [
        "Hills: wind 6 m/s toward 45 degrees, gusts 0.5"]
    assert _motion_lines("Hills", room["settings"], tuned["settings"]) == [
        "Hills: decoration animation on (sway 1.4); own settings for torch"]
    assert _motion_lines("Hills", tuned["settings"], off["settings"]) == ["Hills: decoration animation off"]


def test_a_bad_room_wind_leaves_the_rain_falling() -> None:
    from engine import scene_particles

    window = SimpleNamespace(ctx=None, hd2d_renderer=None)
    scene_particles.configure(window, {"particles": [{"preset": "rain"}], "wind": {"speed": 4, "gust": 1.5}})
    assert window.scene_particles_error is None


def test_a_tree_keeps_its_canopy_clear_of_structures() -> None:
    from engine.hd2d.scatter import Ground, Rules, allowed

    near_wall = Ground(surface=lambda x, y: (0.0, 1.0), structure=lambda x, y: x > 40.0)  # (a wall from x = 40 px)
    assert allowed(ASSETS["grass_tuft"], 20.0, 0.0, near_wall, Rules(on=("grass",)))
    assert not allowed(ASSETS["tree_small"], 20.0, 0.0, near_wall, Rules(on=("grass",)))  # (its canopy would)
    assert allowed(ASSETS["tree_small"], -40.0, 0.0, near_wall, Rules(on=("grass",)))
