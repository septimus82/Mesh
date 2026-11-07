"""Route checking for "Walk between points" (Milestone 11's visual patrol editor)."""

from __future__ import annotations

import pytest

from engine import project_ops as ops
from engine.route_check import route_problems

pytestmark = pytest.mark.fast


def _room() -> dict:
    """A 10 x 8 map with a wall down column 5, rows 0-5 (a gap at rows 6 and 7, the bottom two)."""
    scene, _path, _doc = ops.add_map({"name": "R", "entities": []}, "packs/x/scenes/r.json", width=10, height=8)
    return ops.paint_tiles(scene, ops.WALLS, [(5, r) for r in range(6)], 9)


def cell(col: int, row: int) -> tuple[float, float]:
    return col * 32 + 16.0, (8 - row) * 32 - 16.0


def test_a_clear_route_has_no_problems() -> None:
    assert route_problems(_room(), cell(1, 1), [cell(2, 1), cell(3, 4)]) == []


def test_a_wall_across_the_way_is_reported_with_a_way_round() -> None:
    problems = route_problems(_room(), cell(2, 2), [cell(2, 2), cell(8, 2)])
    assert [p.kind for p in problems] == ["blocked"]
    assert problems[0].leg == (0, 1) and "way round" in problems[0].text  # through the gap at the bottom


def test_points_inside_walls_or_outside_the_map_are_named() -> None:
    problems = route_problems(_room(), None, [cell(5, 2), (900.0, 50.0)])
    assert [(p.kind, p.point) for p in problems] == [("wall", 0), ("outside", 1)]
    assert problems[0].text.startswith("Point 1 is inside a wall")


def test_the_way_from_where_it_starts_counts_too() -> None:
    problems = route_problems(_room(), cell(8, 1), [cell(2, 1), cell(2, 3)])
    assert [p.leg for p in problems] == [(None, 0)] and "from where it starts" in problems[0].text


def test_solid_objects_block_but_the_walker_itself_does_not() -> None:
    room = _room()
    room["entities"] = [{"id": "crate", "x": cell(3, 1)[0], "y": cell(3, 1)[1], "solid": True},
                        {"id": "guard", "x": cell(1, 1)[0], "y": cell(1, 1)[1], "solid": True}]
    assert [p.kind for p in route_problems(room, cell(1, 1), [cell(1, 1), cell(4, 1)], ignore="guard")] == ["blocked"]
    assert route_problems(room, cell(1, 1), [cell(1, 1), cell(1, 3)], ignore="guard") == []
