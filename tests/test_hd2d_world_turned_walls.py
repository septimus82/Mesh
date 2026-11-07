"""A structure turned off the axes keeps its walls where they are: a walkway turned 74 degrees between two railings
can be walked along, and its railings still stop a walker crossing them (Lakeside Village: Studio's Turn field and
+15 button allow any turn; each railing's box round its turned corners used to cover the whole walkway). Headless."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from engine.hd2d.glb import Model
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import World
from tests.test_hd2d_world_tunnelling import _box_top, _feet_y, _walker

pytestmark = pytest.mark.fast


def _railed_walkway(turn: float) -> World:
    """Two 6 m railings 2 m apart (local y = +-1), on open ground, turned ``turn`` degrees about the origin."""
    settings = parse_hd2d({"structures": [{"id": "s", "model": "m.glb", "x": 0, "y": 0, "rotation": turn}],
                           "ground": {"from": [-320, -320], "to": [320, 320]}})
    rails = [_box_top("rail_north", "wall", -3, 0.95, 3, 1.05, 0, 1), _box_top("rail_south", "wall", -3, -1.05, 3, -0.95, 0, 1)]
    return World(settings, {"m.glb": Model(Path("m.glb"), [], rails)})


@pytest.mark.parametrize("turn", [74.0, 15.0, 45.0, -30.0])
def test_a_turned_walkway_can_be_walked_along_and_its_railings_still_stop_a_crossing(turn: float) -> None:
    world = _railed_walkway(turn)
    a = math.radians(turn)
    along, across = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    walker = _walker(-2.0 * along[0], -2.0 * along[1])  # on the walkway, 2 m from its middle
    for _ in range(16):  # 4 m along it, in steps
        world.move(walker, (along[0] * 8, along[1] * 8), [])
    feet = (walker.center_x / 32, (walker.center_y - 18) / 32)
    assert math.dist(feet, (2.0 * along[0], 2.0 * along[1])) < 0.2, f"stopped at {feet} walking along a {turn} deg walkway"
    crossing = _walker(0.0, 0.0)
    for _ in range(12):  # 3 m across it, toward a railing
        world.move(crossing, (across[0] * 8, across[1] * 8), [])
    sideways = (crossing.center_x / 32) * across[0] + ((crossing.center_y - 18) / 32) * across[1]
    assert sideways < 0.95, f"crossed a railing of a {turn} deg walkway ({sideways:.2f} m out)"


@pytest.mark.parametrize("turn", [0.0, 90.0, 180.0, -90.0, 270.0])
def test_a_wall_turned_by_a_right_angle_stays_one_exact_box(turn: float) -> None:
    assert len(_railed_walkway(turn).walls) == 2


def _water(x0: float, y0: float, x1: float, y1: float, level_m: float) -> object:
    """A water surface that blocks (Walk through it: Off): a solid sprite the water's size, at its level."""
    from types import SimpleNamespace

    return SimpleNamespace(center_x=(x0 + x1) / 2 * 32, center_y=(y0 + y1) / 2 * 32, width=(x1 - x0) * 32,
                           height=(y1 - y0) * 32, scale_x=1.0, solid=True, mesh_behaviours=["WaterSurface"],
                           mesh_entity_data={"elevation": level_m * 32,
                                             "components": {"collider": {"kind": "box", "auto": True}}})


def test_a_footbridge_deck_crosses_water_that_blocks_and_the_bank_does_not() -> None:
    """A deck 0.6 m up over water that blocks, its surface level with the bank: a walker on the deck crosses it; one
    on the bank is stopped at the water (Lakeside Village's inlet blocked its own footbridge: a solid within a body's
    height counted, a water surface below the deck too)."""
    settings = parse_hd2d({"structures": [{"id": "s", "model": "m.glb", "x": 0, "y": 0}],
                           "ground": {"from": [-320, -320], "to": [320, 320]}})
    world = World(settings, {"m.glb": Model(Path("m.glb"), [], [_box_top("deck", "floor", -1, -1, 1, 6, 0.5, 0.6)])})
    water = _water(-6, 1.5, 6, 3.5, 0.0)
    on_deck = _walker(0.0, 0.0, 0.6)
    for _ in range(20):  # 5 m north along the deck, over the water
        world.move(on_deck, (0, 8), [water])
    assert _feet_y(on_deck) > 4.5 and on_deck.mesh_entity_data["elevation"] == 0.6 * 32
    on_bank = _walker(3.0, 0.0)
    for _ in range(20):  # north on the ground beside the deck, into the water
        world.move(on_bank, (0, 8), [water])
    assert _feet_y(on_bank) < 1.5, "walked into water that blocks"


def _block(turn: float, half: float, scale: float = 1.0) -> World:
    """A solid square wall block ``2 * half`` m across (times ``scale``), turned ``turn`` degrees about the origin."""
    settings = parse_hd2d({"structures": [{"id": "s", "model": "m.glb", "x": 0, "y": 0, "rotation": turn, "scale": scale}],
                           "ground": {"from": [-960, -960], "to": [960, 960]}})
    block = [_box_top("block", "wall", -half, -half, half, half, 0, 3)]
    return World(settings, {"m.glb": Model(Path("m.glb"), [], block)})


@pytest.mark.parametrize(("turn", "half", "scale"), [(45.0, 1.0, 1.0), (30.0, 10.0, 1.0), (45.0, 2.0, 2.5)])
def test_a_broad_turned_wall_is_one_collider_that_fits_its_turned_footprint(turn: float, half: float, scale: float) -> None:
    """A broad or scaled turned wall stays one collider (it used to be cut into 0.25 m slices both ways: a 20 m block
    turned 30 degrees was 6,400 boxes and a 40 m route past it took 15 s to plan), and it stops a character exactly
    at its turned sides: blocked just inside, free just outside, though both are inside the box round its corners."""
    world = _block(turn, half, scale)
    assert len(world.walls) == 1
    a, side = math.radians(turn), half * scale
    feet = (0.05, 0.05)
    for along in (-0.8, 0.0, 0.8):  # points along the wall's +x side, in its own frame
        for out, blocked in ((-0.1, True), (0.1, False)):
            lx, ly = side + feet[0] + out, along * side  # local: just inside / outside the side, by the feet box
            x, y = lx * math.cos(a) - ly * math.sin(a), lx * math.sin(a) + ly * math.cos(a)
            assert (world.stand(x, y, 0.0, *feet) is None) is blocked, f"{(lx, ly)} local, turn {turn}"
    gap = (0.8 * side, 0.8 * side)  # inside the box round its corners, outside the turned block
    assert world.walls[0].hi[0] > gap[0] and world.walls[0].hi[1] > gap[1]
    assert world.stand(*gap, 0.0, *feet) is not None

