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


def test_walking_along_a_wall_it_is_in_is_free() -> None:
    feet = Aabb(720, 190, 19, 12)  # the wall's centre is straight below: sideways goes no deeper
    moved, result = _move(feet, (3.0, 0.0), WALL)
    assert moved.x == pytest.approx(723.0) and not result.hit_x


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
