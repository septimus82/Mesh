import pytest

from engine.day_night import DayNightCycle
from engine.lighting import LightManager


class StubLighting(LightManager):
    def __init__(self):
        # Bypass LightManager init; we only need ambient_color field and setter
        self.enabled = True
        self.available = False
        self.ambient_color = (0, 0, 0, 255)
        self._dynamic_handles = []

    def set_ambient_rgb(self, r: int, g: int, b: int, a: int | None = None) -> None:
        self.ambient_color = (int(r), int(g), int(b), self.ambient_color[3] if a is None else int(a))


def test_day_night_advances_time():
    lighting = StubLighting()
    dn = DayNightCycle(lighting, enabled=True, start_hour=0.0, cycle_length_seconds=120.0)
    dn.update(60.0)
    assert pytest.approx(dn.hour, rel=1e-3) == 12.0


def test_day_night_wraps():
    lighting = StubLighting()
    dn = DayNightCycle(lighting, enabled=True, start_hour=23.0, cycle_length_seconds=240.0)
    dn.update(30.0)  # 30/240 *24 = 3h; wraps to ~2
    assert 0.0 <= dn.hour < 3.5


def test_compute_ambient_rgb_interpolates():
    lighting = StubLighting()
    dn = DayNightCycle(lighting, enabled=True, start_hour=6.0, cycle_length_seconds=600.0)
    dn.set_hour(6.0)
    r, g, b = dn.compute_ambient_rgb()
    # Dawn colors should be between night and day defaults
    assert 10 <= r <= 200
    assert 10 <= g <= 200
    assert 30 <= b <= 220


@pytest.mark.fast
def test_switched_off_it_leaves_the_projects_ambient_alone() -> None:
    """Found by the capability lab: constructing it always applied the 21:00 colour, so a project's
    lighting_ambient_color never showed while day/night was off."""
    from types import SimpleNamespace

    lighting = SimpleNamespace(ambient_color=(255, 255, 255, 255))
    DayNightCycle(lighting, enabled=False, start_hour=21.0)
    assert lighting.ambient_color == (255, 255, 255, 255)
