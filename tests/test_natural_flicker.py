"""Milestone 12.1: lights flicker like flames, not like a breathing pulse.

The old flicker eased between one random value per beat and moved only a light's reach: a regular swell
in and out. These tests pin what replaced it (engine/lighting/flicker.py): no regular cycle, brightness
moving more than reach for candles and torches, independent neighbours, the same frames at any frame
rate, a faulty lamp that never strobes, a calmer accessibility mode, and older settings that still mean
what they meant.
"""

from __future__ import annotations

import statistics

import pytest

from engine.lighting import flicker as fl

pytestmark = pytest.mark.fast

RATE = 60


def _series(name: str, seed: int = 5, seconds: float = 20.0, reduced: bool = False) -> tuple[list[float], list[float]]:
    pairs = [fl.flicker_sample(fl.FLICKER_PRESETS[name], seed, i / RATE, 1.0, reduced) for i in range(int(seconds * RATE))]
    return [b for b, _r in pairs], [r for _b, r in pairs]


def _peak_gaps(values: list[float]) -> list[int]:
    peaks = [i for i in range(1, len(values) - 1) if values[i - 1] < values[i] >= values[i + 1]]
    return [b - a for a, b in zip(peaks, peaks[1:])]


@pytest.mark.parametrize("name", ["candle", "torch", "fire"])
def test_flames_have_no_regular_beat(name: str) -> None:
    gaps = _peak_gaps(_series(name)[0])
    spread = statistics.pstdev(gaps) / statistics.mean(gaps)
    assert spread > 0.35, f"{name}: the time between brightness peaks is too regular ({spread:.2f})"


def test_the_old_flicker_had_one():
    """For the record: the old noise peaks only on its beat (every 12 frames here: what owners saw as pulsing)."""
    noise = fl.FlickerNoise(3)
    values = [noise.sample(i / RATE * 5.0) for i in range(20 * RATE)]
    assert all(gap % 12 == 0 for gap in _peak_gaps(values))
    assert not all(gap % 12 == 0 for gap in _peak_gaps(_series("torch")[0]))


@pytest.mark.parametrize("name", ["candle", "torch"])
def test_candles_and_torches_flicker_in_brightness_more_than_in_reach(name: str) -> None:
    brightness, reach = _series(name)
    assert statistics.pstdev(brightness) > 3 * statistics.pstdev(reach), name


def test_presets_get_livelier_from_candle_to_fire() -> None:
    spread = {name: statistics.pstdev(_series(name)[0]) for name in ("candle", "torch", "fire")}
    assert spread["candle"] < spread["torch"] < spread["fire"], spread


def test_two_torches_do_not_flicker_together() -> None:
    a, b = _series("torch", seed=11)[0], _series("torch", seed=12)[0]
    assert abs(statistics.correlation(a, b)) < 0.4


def test_the_same_seed_and_time_give_the_same_light() -> None:
    profile = fl.FLICKER_PRESETS["fire"]
    assert fl.flicker_sample(profile, 9, 12.345) == fl.flicker_sample(profile, 9, 12.345)


def test_a_faulty_lamp_never_strobes() -> None:
    """At most three drop-outs in any second (photosensitivity guidance), each a dip, not a flash."""
    brightness, _ = _series("faulty", seconds=60.0)
    dark = [b < 0.7 for b in brightness]
    starts = [i for i in range(1, len(dark)) if dark[i] and not dark[i - 1]]
    worst = max(sum(1 for s in starts if t <= s < t + RATE) for t in range(0, len(dark), RATE // 4))
    assert starts, "a faulty lamp drops out now and then"
    assert worst <= 3, f"{worst} drop-outs within a second"
    assert sum(dark) / len(dark) < 0.1, "mostly steady"


def test_calmer_flickering_is_calmer_and_has_no_drop_outs() -> None:
    assert statistics.pstdev(_series("torch", reduced=True)[0]) < 0.6 * statistics.pstdev(_series("torch")[0])
    assert min(_series("faulty", seconds=60.0, reduced=True)[0]) > 0.6


def test_older_settings_keep_their_meaning() -> None:
    """A light from before presets: flicker_amount for brightness and reach, flicker_speed as its speed."""
    profile = fl.flicker_profile({"flicker_enabled": True, "flicker_amount": 0.2, "flicker_speed": 5.0})
    assert profile is not None and profile.brightness == 0.2 and profile.reach == 0.2 and profile.speed == 5.0
    assert fl.flicker_profile({"flicker_enabled": False, "flicker_preset": "torch"}) is None
    assert fl.flicker_profile({"flicker_enabled": True, "flicker_preset": "candle"}) == fl.FLICKER_PRESETS["candle"]


class _Light:
    def __init__(self) -> None:
        self.radius = 100.0
        self._color = (200, 180, 160)
        self._light_layer = None


def test_brightness_flicker_reaches_the_light_and_stops_at_its_base() -> None:
    """Before, a light's colour was never changed (Arcade keeps it private): only its reach moved."""
    light = _Light()
    state = fl.flicker_state(light, 100.0, (200, 180, 160, 255), {"flicker_preset": "fire"}, seed=4)
    colours = set()
    for i in range(120):
        fl.apply_flicker(state, i / RATE)
        colours.add(light._color)
    assert len(colours) > 20, "the light's brightness changes"
    assert all(abs(c[0] - 200) < 120 for c in colours)


def test_any_frame_rate_reaches_the_same_light_at_the_same_moment() -> None:
    a, b = _Light(), _Light()
    sa = fl.flicker_state(a, 100.0, (200, 180, 160, 255), {"flicker_preset": "torch"}, seed=2)
    sb = fl.flicker_state(b, 100.0, (200, 180, 160, 255), {"flicker_preset": "torch"}, seed=2)
    t_a = t_b = 0.0
    for _ in range(30):
        t_a += 1 / 30
        fl.apply_flicker(sa, t_a)
    for _ in range(144):
        t_b += 1 / 144
        fl.apply_flicker(sb, t_b)
    assert abs(t_a - t_b) < 1e-9 or (a.radius, a._color) == (b.radius, b._color)
    fl.apply_flicker(sa, 1.0)
    fl.apply_flicker(sb, 1.0)
    assert (a.radius, a._color) == (b.radius, b._color)
