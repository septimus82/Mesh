"""A collider that already overlaps a wall can always walk out of it, and never goes deeper (or through).

Found by the remediation programme's final acceptance smoke: a door's arrival spot put the player's feet 8 px into the
wall tile below. Pressing up (toward the door) snapped the feet to that wall's far (bottom) edge, deep inside it, and
from there every move up snapped them back: stuck for good. Movement now resolves only against walls a move enters.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.physics_model import Aabb, MoveRequest, sweep_axis_separate

pytestmark = pytest.mark.fast

WALL = Aabb(720, 176, 32, 32)  # y 160..192 (the smoke's wall tile under the arrival spot)


def _query(*walls: Aabb):
    return lambda box: [w for w in walls if box.intersection(w)]


def _move(box: Aabb, delta: tuple[float, float], *walls: Aabb):
    result = sweep_axis_separate(MoveRequest("p", (box.x, box.y), delta, box), _query(*walls))
    return Aabb(result.final_pos[0], result.final_pos[1], box.w, box.h), result


def test_feet_in_the_wall_below_walk_up_and_out() -> None:
    feet = Aabb(720, 190, 19, 12)  # y 184..196: 8 px into the wall
    for _ in range(4):
        moved, result = _move(feet, (0.0, 3.0), WALL)
        assert moved.y == pytest.approx(feet.y + 3.0) and not result.hit_y, "moving away from a wall it is in is free"
        feet = moved
    assert feet.bottom >= WALL.top, "out of the wall"


def test_feet_in_the_wall_below_cannot_go_deeper_or_slide_through() -> None:
    feet = Aabb(720, 190, 19, 12)
    for delta in (-3.0, -400.0):  # a long move is cut into pieces: none may cross the wall
        moved, result = _move(feet, (0.0, delta), WALL)
        assert result.hit_y and moved.bottom == pytest.approx(WALL.top), \
            "moving into a wall it is in stays blocked: flush on the side it came from (as approaching it)"


def test_the_same_on_the_x_axis() -> None:
    wall = Aabb(200, 100, 32, 32)  # x 184..216
    body = Aabb(180, 100, 20, 20)  # x 170..190: 6 px into the wall on its right (still in after a 3 px step)
    moved, result = _move(body, (-3.0, 0.0), wall)
    assert moved.x == pytest.approx(177.0) and not result.hit_x, "it used to snap across, to the wall's far side"
    moved, result = _move(body, (3.0, 0.0), wall)
    assert result.hit_x and moved.right == pytest.approx(wall.left)
    moved, result = _move(Aabb(220, 100, 20, 20), (-3.0, 0.0), wall)  # 6 px in on its right side: right walks out
    assert result.hit_x and moved.left == pytest.approx(wall.right)
    moved, result = _move(Aabb(220, 100, 20, 20), (3.0, 0.0), wall)
    assert moved.x == pytest.approx(223.0) and not result.hit_x


def test_walking_along_a_single_wall_centred_on_it_is_free() -> None:
    feet = Aabb(720, 190, 19, 12)  # the one wall's centre is straight below: sideways goes no deeper
    moved, result = _move(feet, (3.0, 0.0), WALL)
    assert moved.x == pytest.approx(723.0) and not result.hit_x


def test_more_than_half_way_in_by_its_leading_edge_it_is_still_pushed_back_out() -> None:
    """The centre decides, not the leading edge: a box whose top is past the wall's centre (51%+ in by its leading edge)
    while its own centre is still below the wall's centre, moving further in, ends flush below the wall."""
    tall = Aabb(720, 150, 20, 60)  # y 120..180: top 20 px into the wall (y 160..192, centre 176); centre 150 < 176
    for delta in (3.0, 200.0):
        moved, result = _move(tall, (0.0, delta), WALL)
        assert result.hit_y and moved.top == pytest.approx(WALL.bottom), (delta, moved)
    side = Aabb(690, 176, 60, 20)  # x 660..720: right edge 16 px into the wall (x 704..736, centre 720); centre 690
    moved, result = _move(side, (3.0, 0.0), WALL)
    assert result.hit_x and moved.right == pytest.approx(WALL.left)


def _row(y: float, x0: float, count: int) -> list[Aabb]:
    return [Aabb(x0 + 16 + 32 * i, y, 32, 32) for i in range(count)]


def test_along_a_row_of_tiles_it_is_in_it_is_pinned_but_never_deeper_and_can_leave() -> None:
    """Recorded behaviour, not the ideal (follow-up: push out along the shallower axis): feet 8 px into a floor row,
    walking right stop flush against the next tile and stay there, as deep as before; moving up frees them."""
    floor = _row(176.0, 0.0, 8)  # y 160..192, tiles x 0..256
    feet = Aabb(100, 190, 19, 12)  # x 90.5..109.5, y 184..196: over the tiles at x 64..96 and 96..128
    first, _ = _move(feet, (3.0, 0.0), *floor)
    assert first.right == pytest.approx(96.0) and first.y == feet.y, "flush with the next tile, no deeper"
    assert feet.x - first.x < 32, "never a whole tile back (it used to jump ~32 px back every frame)"
    held = first
    for _ in range(5):
        held, result = _move(held, (3.0, 0.0), *floor)
        assert result.hit_x and held.x == pytest.approx(first.x) and held.y == feet.y, "pinned, still 8 px in"
    up, result = _move(held, (0.0, 3.0), *floor)
    assert up.y == pytest.approx(feet.y + 3.0) and not result.hit_y, "leaving the row is free"
    column = [Aabb(116, 16 + 32 * i, 32, 32) for i in range(8)]  # a side wall column x 100..132
    side = Aabb(105, 100, 12, 19)  # x 99..111: 11 px into the column
    held, _ = _move(side, (0.0, 3.0), *column)
    assert held.x == side.x and side.y - held.y < 32
    out, result = _move(held, (-3.0, 0.0), *column)
    assert out.x == pytest.approx(side.x - 3.0) and not result.hit_x


@pytest.mark.parametrize("step", [10.0, 100.0, 5000.0])  # one piece; several; the capped many
def test_approaching_a_wall_still_stops_flush_without_tunnelling(step: float) -> None:
    thin = Aabb(300, 100, 4, 200)  # x 298..302
    moved, result = _move(Aabb(282, 100, 20, 20), (step, 0.0), thin)
    assert result.hit_x and moved.right == pytest.approx(thin.left)
    moved, result = _move(Aabb(318, 100, 20, 20), (-step, 0.0), thin)
    assert result.hit_x and moved.left == pytest.approx(thin.right)
    floor = Aabb(300, 0, 400, 4)  # y -2..2
    moved, result = _move(Aabb(300, 18, 20, 20), (0.0, -step), floor)
    assert result.hit_y and moved.bottom == pytest.approx(floor.top)
    moved, result = _move(Aabb(300, -18, 20, 20), (0.0, step), floor)
    assert result.hit_y and moved.top == pytest.approx(floor.bottom)


def test_flush_against_a_wall_it_slides_along_and_steps_away() -> None:
    body = Aabb(WALL.left - 10, WALL.y, 20, 20)  # touching the wall's left side
    moved, result = _move(body, (5.0, 0.0), WALL)
    assert moved.x == body.x and result.hit_x
    moved, result = _move(body, (0.0, 5.0), WALL)
    assert moved.y == pytest.approx(body.y + 5.0) and not result.hit_y
    moved, result = _move(body, (-5.0, 0.0), WALL)
    assert moved.x == pytest.approx(body.x - 5.0) and not result.hit_x


class _Sprite:
    """What the SceneController mover reads from an Arcade sprite (enemies, patrols, followers, cutscene moves)."""

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.center_x, self.center_y, self.width, self.height = x, y, w, h

    left = property(lambda s: s.center_x - s.width / 2)
    right = property(lambda s: s.center_x + s.width / 2)
    bottom = property(lambda s: s.center_y - s.height / 2)
    top = property(lambda s: s.center_y + s.height / 2)


def _overlap(a: _Sprite, others: list[_Sprite]) -> list[_Sprite]:
    return [o for o in others if a.right > o.left and a.left < o.right and a.top > o.bottom and a.bottom < o.top]


def test_the_scene_controller_mover_walks_out_of_a_wall_too(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core
    from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision

    monkeypatch.setattr(core.optional_arcade, "arcade", SimpleNamespace(check_for_collision_with_list=_overlap))
    wall = _Sprite(720, 176, 32, 32)
    controller = SimpleNamespace(solid_sprites=[wall])
    enemy = _Sprite(720, 196, 20, 20)  # y 186..206: 6 px into the wall below (still in after a 3 px step)
    move_entity_with_collision(controller, enemy, 0.0, 3.0)
    assert enemy.center_y == pytest.approx(199.0), "away is free (it used to snap to the wall's far edge, y 150)"
    enemy.center_y = 196.0
    move_entity_with_collision(controller, enemy, 0.0, -3.0)
    assert enemy.bottom == pytest.approx(wall.top), "deeper stays blocked, flush on the side it came from"
    enemy.center_y = 230.0
    move_entity_with_collision(controller, enemy, 0.0, -100.0)
    assert enemy.bottom == pytest.approx(wall.top), "approaching still stops flush"
    side = _Sprite(600, 176, 20, 20)
    move_entity_with_collision(controller, side, 500.0, 0.0)
    assert side.right == pytest.approx(wall.left), "and a fast move still can't tunnel through"
