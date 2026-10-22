"""`input_bindings: {}` gets the engine default keys, like a missing value does.

EngineConfig defaults input_bindings to {}, and the runtime used to apply its
defaults only for None, so such projects had arrows/E/Esc only: no WASD, no F4.
Uses real arcade key codes (arcade_fallback's key table hid this bug).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.config import EngineConfig, load_config
from engine.input_controller import InputController

pytestmark = [pytest.mark.fast]

arcade = pytest.importorskip("arcade")
KEY = arcade.key


def _bindings(cfg: EngineConfig) -> dict[str, list[int]]:
    return InputController(SimpleNamespace(engine_config=cfg)).manager.get_bindings()


def _project_config(tmp_path: Path, **extra: object) -> EngineConfig:
    payload = {"width": 640, "height": 360, "title": "t", "start_scene": "s.json", **extra}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_config(str(path))


@pytest.mark.parametrize("extra", [{"input_bindings": {}}, {}], ids=["empty-map", "missing"])
def test_unconfigured_bindings_get_wasd_and_f4(tmp_path: Path, extra: dict) -> None:
    bound = _bindings(_project_config(tmp_path, **extra))
    assert KEY.W in bound["move_up"] and KEY.A in bound["move_left"]
    assert KEY.S in bound["move_down"] and KEY.D in bound["move_right"]
    assert KEY.F4 in bound["toggle_editor"]


def test_key_name_cache_is_not_shared_with_arcade_fallback() -> None:
    # A map cached from arcade_fallback's small key table used to answer for real arcade,
    # so "I" became an unknown key name for every later test in the session.
    from engine import arcade_fallback
    from engine.input_runtime.bindings import _ensure_key_maps

    _ensure_key_maps(arcade_fallback)
    name_to_code, _ = _ensure_key_maps(arcade)
    assert name_to_code["I"] == KEY.I


def test_non_empty_map_keeps_exactly_what_it_set(tmp_path: Path) -> None:
    bound = _bindings(_project_config(tmp_path, input_bindings={"move_up": ["I"], "attack": ["J"]}))
    assert KEY.I in bound["move_up"] and KEY.W not in bound["move_up"]
    assert KEY.J in bound["attack"]
    assert "toggle_editor" not in bound
