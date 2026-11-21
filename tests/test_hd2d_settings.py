"""Milestone 16 Stage 2: a scene's ``settings.hd2d`` is validated with errors naming the key, the optional
``elevation`` is HD-2D-only (2D ignores it; ``depth_z`` stays draw order), and 2D scenes never touch the 3D code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d

pytestmark = pytest.mark.fast
REPO = Path(__file__).resolve().parents[1]


def test_settings_parse_with_defaults_in_mesh_pixels() -> None:
    s = parse_hd2d({"structures": [{"model": "assets/models/outpost.glb", "x": 384, "y": 256}], "ground": {}},
                   map_size_px=(768.0, 512.0))
    assert s.structures[0].model == "assets/models/outpost.glb" and (s.structures[0].x, s.structures[0].y) == (384, 256)
    assert s.ground is not None and s.ground.hi == (768.0, 512.0), "the ground covers the map by default"
    assert (s.camera.pitch, s.camera.fov, s.camera.distance, s.camera.follow) == (32.0, 30.0, 15.0, "player")


@pytest.mark.parametrize(("raw", "message"), [
    ([], "must be an object"),
    ({"structurez": []}, "unknown keys: structurez"),
    ({"structures": [{"model": "outpost.obj"}]}, r"structures\[0\].model must be a project-relative .glb"),
    ({"structures": [{"model": "a.glb", "x": "east"}]}, r"structures\[0\].x must be a finite number"),
    ({"structures": [{"model": "a.glb", "scale": 0}]}, r"structures\[0\].scale must be between"),
    ({"camera": {"pitch": 95}}, "camera.pitch must be between"),
    ({"ground": {"to": [1]}}, r"ground.to must be \[x, y\]"),
    ({"sun": [0, 0, 0]}, "sun must be a direction"),
    ({"ambient": 2}, "ambient must be between"),
])
def test_bad_settings_are_refused_naming_the_key(raw: object, message: str) -> None:
    with pytest.raises(Hd2dSettingsError, match=message):
        parse_hd2d(raw)


def test_elevation_is_a_known_entity_field_and_depth_z_is_still_draw_order() -> None:
    import json

    from engine.scene_loader import KNOWN_ENTITY_FIELDS

    assert "elevation" in KNOWN_ENTITY_FIELDS
    schema = json.loads((REPO / "engine/schemas/entity.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["elevation"]["type"] == "number"
    assert schema["properties"]["depth_z"] == {"type": "number"}, "depth_z unchanged"


def test_elevation_survives_a_save() -> None:
    from engine.scene_runtime.persistence import _remove_runtime_only_entity_fields

    entity = {"id": "keeper", "prefab_id": "person", "x": 426.0, "y": 264.0, "elevation": 32.0}
    _remove_runtime_only_entity_fields(entity)
    assert entity["elevation"] == 32.0


def test_a_2d_scene_gets_no_renderer_and_a_broken_hd2d_scene_still_loads_drawn_2d(caplog) -> None:
    from engine.hd2d.runtime import configure_scene

    window = SimpleNamespace(hd2d_renderer=None)
    configure_scene(window, {"world_width": 768})
    assert window.hd2d_renderer is None and window.hd2d_error is None
    configure_scene(window, {"hd2d": {"structures": [{"model": "nowhere/missing.glb"}]}})
    assert window.hd2d_renderer is None
    assert "missing.glb" in window.hd2d_error and "can't be read" in window.hd2d_error
    configure_scene(window, {"hd2d": {"camera": {"fov": 1}}})
    assert "camera.fov" in window.hd2d_error


def test_2d_games_never_import_the_3d_renderer() -> None:
    code = ("import sys; import engine.scene_lifecycle_controller, engine.game_runtime.tick; "
            "print('engine.hd2d.renderer' in sys.modules, 'engine.hd2d.glb' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert out.split() == ["False", "False"]
