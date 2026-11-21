"""B-07 in a real (hidden) GameWindow: a RangedAttackAI entity with the player in range finds the player through the
scene controller (as every working behaviour does) and fires. GL-gated: MESH_GL_SMOKE=1. Silent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, hero, make_window

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]


def _archer(x: float) -> dict[str, Any]:
    return {"id": "archer", "name": "Archer", "x": x, "y": 50, "sprite": PIC, "layer": "entities",
            "behaviours": ["RangedAttackAI"],
            "behaviour_config": {"RangedAttackAI": {"attack_range": 250.0, "attack_cooldown": 0.5}}}


def _shots(tmp_path: Path, archer_x: float) -> int:
    window = make_window()
    try:
        arena = Arena(window, tmp_path)
        arena.write_room(hero(), _archer(archer_x))
        arena.enter()
        fired: list[Any] = []
        window.event_bus.subscribe("projectile_fired", lambda *a, **kw: fired.append((a, kw)))
        for _ in range(30):
            window.on_update(1 / 60)
        return len(fired)
    finally:
        close_window(window)


def test_an_archer_in_range_of_the_player_fires(tmp_path: Path) -> None:
    assert _shots(tmp_path, 150.0) >= 1


def test_an_archer_out_of_range_of_the_player_holds_fire(tmp_path: Path) -> None:
    assert _shots(tmp_path, 900.0) == 0
