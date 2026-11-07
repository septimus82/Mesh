"""Milestone 16 Stage 3 review: large moves can't pass through thin walls, railings or gaps; overlapping floors
resolve to the right height; characters on different floors at the same x/y don't collide; rooms without HD-2D
floors keep the 2D physics. Headless."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.hd2d.glb import Collider, Model, load_glb
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import World

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
CROSSING = REPO / "tooling" / "hd2d_assets" / "stone_crossing.glb"


def _box_top(name: str, kind: str, x0: float, y0: float, x1: float, y1: float, z0: float, z1: float) -> Collider:
    top = [((x0, y0, z1), (x1, y0, z1), (x1, y1, z1)), ((x0, y0, z1), (x1, y1, z1), (x0, y1, z1))]
    return Collider(name, kind, [] if kind == "wall" else top, (x0, y0, z0), (x1, y1, z1))


def _world(*colliders: Collider) -> World:
    settings = parse_hd2d({"structures": [{"id": "s", "model": "m.glb", "x": 0, "y": 0}],
                           "ground": {"from": [-320, -320], "to": [320, 320]}})  # ground: -10 .. 10 m
    return World(settings, {"m.glb": Model(Path("m.glb"), [], list(colliders))})


def _walker(x_m: float, y_m: float, elevation_m: float = 0.0, *, solid: bool = False) -> SimpleNamespace:
    """A 32 x 48 px character whose feet box (the bottom quarter, 60% wide: 0.6 x 0.375 m) is centred at (x, y)."""
    return SimpleNamespace(center_x=x_m * 32, center_y=y_m * 32 + 18, width=32.0, height=48.0, scale_x=1.0,
                           solid=solid, mesh_entity_data={"elevation": elevation_m * 32,
                                                          "components": {"collider": {"kind": "box", "auto": True}}})


def _feet_y(sprite: SimpleNamespace) -> float:
    return (sprite.center_y - 18) / 32


@pytest.mark.parametrize("delta_m", [0.5, 1.0, 3.0, 8.0])
def test_a_large_move_does_not_pass_through_a_thin_wall(delta_m: float) -> None:
    world = _world(_box_top("thin_wall", "wall", -5, 1.0, 5, 1.05, 0, 3))  # 5 cm thick, on open ground
    hero = _walker(0, 0)
    world.move(hero, (0, delta_m * 32), [])
    assert _feet_y(hero) < 1.0 - 0.18, f"a {delta_m} m step went through the wall"


@pytest.mark.parametrize("delta_m", [1.0, 3.0])
def test_a_large_move_does_not_pass_through_the_bridge_railing_or_jump_a_gap(delta_m: float) -> None:
    world = _world(_box_top("west", "solid", -6, -2, -0.5, 2, 0, 2), _box_top("east", "solid", 0.5, -2, 6, 2, 0, 2),
                   _box_top("rail", "wall", -6, 1.2, 6, 1.3, 2, 2.6))  # a 1 m gap; a 10 cm railing on both
    across = _walker(-1.0, 0, 2.0)
    world.move(across, (delta_m * 32, 0), [])  # east over the 1 m gap at 2 m up: no floor in between
    assert across.center_x / 32 < -0.5 and across.mesh_entity_data["elevation"] == 64.0, "jumped the gap"
    railing = _walker(-3.0, 0.8, 2.0)
    world.move(railing, (0, delta_m * 32), [])  # north into the railing (beyond it the platform continues)
    assert _feet_y(railing) < 1.2 - 0.18, "passed through the railing"


def test_a_large_move_off_a_platform_edge_stops_at_the_edge() -> None:
    world = World(parse_hd2d({"structures": [{"id": "crossing", "model": "c.glb", "x": 512, "y": 384}],
                              "ground": {"to": [1024, 768]}}), {"c.glb": load_glb(CROSSING)})
    hero = _walker(10.0, 12.0, 2.0)  # on the west platform (x 7 .. 13)
    world.move(hero, (-6 * 32, 0), [])
    assert hero.center_x / 32 >= 7.0 - 0.01 and hero.mesh_entity_data["elevation"] == 64.0


@pytest.mark.parametrize(("z", "expected"), [(0.0, 0.0), (0.3, 0.0), (2.0, 2.0), (1.8, 2.0), (1.0, None)])
def test_where_floors_overlap_the_standing_height_follows_the_character(z: float, expected: float | None) -> None:
    world = World(parse_hd2d({"structures": [{"id": "crossing", "model": "c.glb", "x": 512, "y": 384}],
                              "ground": {"to": [1024, 768]}}), {"c.glb": load_glb(CROSSING)})
    got = world.stand(16.0, 12.0, z, 0.3, 0.19)  # under / on the bridge deck
    assert (None if got is None else got[0]) == (None if expected is None else pytest.approx(expected))


def test_characters_on_different_floors_at_the_same_xy_do_not_collide() -> None:
    world = World(parse_hd2d({"structures": [{"id": "crossing", "model": "c.glb", "x": 512, "y": 384}],
                              "ground": {"to": [1024, 768]}}), {"c.glb": load_glb(CROSSING)})
    below, above = _walker(16.0, 10.5), _walker(16.0, 12.0, 2.0, solid=True)  # under the deck; on it
    for _ in range(40):  # north under the solid character standing on the bridge
        world.move(below, (0, 2.5), [above])
    assert _feet_y(below) > 13.0 and below.mesh_entity_data["elevation"] == 0.0
    blocker = _walker(16.0, 14.0, 0.0, solid=True)
    walker = _walker(16.0, 12.5)
    for _ in range(40):  # but a solid character on the same floor still blocks
        world.move(walker, (0, 2.5), [blocker])
    assert _feet_y(walker) < 14.0 - 0.3


def _controller_window(world: object) -> MagicMock:
    window = MagicMock()
    window.hd2d_world = world
    window.player_input_blocked.return_value = False
    window.is_input_locked.return_value = False
    window.dialogue_blocks_input.return_value = False
    window.dialogue_box = None
    window.ui_controller.dialogue_box = None
    window.input.get_axis.side_effect = lambda negative, positive: 1.0 if positive == "move_right" else 0.0
    window.scene_controller.solid_sprites = []
    return window


@pytest.mark.parametrize("world", [None, "mock"])
def test_rooms_without_hd2d_floors_move_with_the_2d_physics(world: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.behaviours.player_controller import PlayerController

    calls: list[tuple] = []
    monkeypatch.setattr("engine.physics_runtime.move_entity_with_physics", lambda e, d, s: calls.append(d))
    window = _controller_window(None if world is None else MagicMock())  # a mock world is not an HD-2D World
    PlayerController(_walker(0, 0), window, speed=100.0).update(0.1)
    assert calls and calls[0][0] == pytest.approx(10.0), "the unchanged 2D sweep moved it"


def test_an_hd2d_room_moves_through_its_world() -> None:
    from engine.behaviours.player_controller import PlayerController

    world = _world()
    hero = _walker(0, 0)
    PlayerController(hero, _controller_window(world), speed=100.0).update(0.1)
    assert hero.center_x == pytest.approx(10.0) and getattr(hero, "mesh_hd2d_floor", None) == "ground"
