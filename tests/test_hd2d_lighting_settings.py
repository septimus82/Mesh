"""Milestone 16 Stage 4: HD-2D lighting settings. The sun keeps its old form, lamps are the scene's ordinary
``lights`` (with an HD-2D height), the room's 2D shadow settings carry over, and the budgets hold. Headless."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.hd2d.settings import (
    LAMP_HEIGHT_PX,
    MAX_LIGHTS,
    MAX_SHADOW_LIGHTS,
    Hd2dSettingsError,
    parse_hd2d,
    parse_scene_lights,
    rgb,
)

pytestmark = pytest.mark.fast
REPO = Path(__file__).resolve().parents[1]


def test_old_scenes_read_as_before_with_shadows_on() -> None:
    s = parse_hd2d({"sun": [-0.45, -0.55, 0.7], "ambient": 0.55})
    assert s.sun == (-0.45, -0.55, 0.7) and s.sun_color == (1.0, 1.0, 1.0) and s.sun_intensity == 1.0
    assert s.shadows is True and s.shadow_resolution == 2048 and s.lights == ()


def test_the_sun_can_be_coloured_and_shadows_configured() -> None:
    s = parse_hd2d({"sun": {"direction": [0.3, 0.5, 0.8], "color": "#ff8000", "intensity": 0.6},
                    "shadows": False, "shadow_resolution": 4096})
    assert s.sun == (0.3, 0.5, 0.8) and s.sun_color == pytest.approx((1.0, 128 / 255, 0.0)) and s.sun_intensity == 0.6
    assert s.shadows is False and s.shadow_resolution == 4096


@pytest.mark.parametrize(("raw", "message"), [
    ({"sun": {"direction": [0, 0, 1], "colour": "#fff"}}, "sun has unknown keys: colour"),
    ({"sun": {"direction": [0, 0, 1], "color": "sunny"}}, "sun.color must be a colour"),
    ({"shadows": "yes"}, "shadows must be true or false"),
    ({"shadow_resolution": 3000}, "shadow_resolution must be 1024, 2048 or 4096"),
])
def test_bad_lighting_settings_name_the_key(raw: dict, message: str) -> None:
    with pytest.raises(Hd2dSettingsError, match=message):
        parse_hd2d(raw)


def test_lamps_are_the_scenes_ordinary_lights() -> None:
    lights = [
        {"type": "ambient", "color": [40, 50, 90], "mode": "soft"},
        {"id": "lamp", "x": 288, "y": 128, "elevation": 60, "radius": 224, "color": "#ffb060", "intensity": 1.6,
         "mode": "soft"},
        {"id": "2d_only", "x": 10, "y": 10, "radius": 100, "color": [255, 255, 255], "mode": "sharp", "shadows": False},
        {"id": "off", "x": 0, "y": 0, "radius": 50, "color": "#ffffff", "mode": "soft", "enabled": False},
    ]
    out = parse_scene_lights(lights, {"lighting_shadow_softness": "softer", "lighting_shadow_strength": 0.5})
    assert out["ambient_color"] == pytest.approx((40 / 255, 50 / 255, 90 / 255))
    lamp, plain = out["lights"]
    assert (lamp.x, lamp.y, lamp.elevation, lamp.radius, lamp.intensity, lamp.shadows) == (288, 128, 60, 224, 1.6, True)
    assert plain.elevation == LAMP_HEIGHT_PX and plain.shadows is False, "a 2D light keeps working: default height"
    assert out["shadow_softness"] == "softer" and out["shadow_strength"] == 0.5


def test_the_lamp_and_shadow_budgets_hold() -> None:
    many = [{"x": i * 10, "y": 0, "radius": 64, "color": "#ffffff", "mode": "soft"} for i in range(12)]
    lamps = parse_scene_lights(many, {})["lights"]
    assert len(lamps) == MAX_LIGHTS and sum(lamp.shadows for lamp in lamps) == MAX_SHADOW_LIGHTS


def test_colours_read_as_the_2d_lighting_writes_them() -> None:
    assert rgb("#ff0080") == pytest.approx((1.0, 0.0, 128 / 255)) and rgb("#ff008080") == pytest.approx((1.0, 0.0, 128 / 255))
    assert rgb([300, -5, 51, 255]) == pytest.approx((1.0, 0.0, 0.2)) and rgb("red") is None


def test_the_scene_schema_documents_the_lamp_height() -> None:
    schema = json.loads((REPO / "engine/schemas/scene.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["light"]["properties"]["elevation"]["type"] == "number"
