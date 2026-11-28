"""A collider that already overlaps a wall can always walk out of it, and never goes deeper (or through).

Found by the remediation programme's final acceptance smoke: a door's arrival spot put the player's feet 8 px into the
wall tile below. Pressing up (toward the door) snapped the feet to that wall's far (bottom) edge, deep inside it, and
from there every move up snapped them back: stuck for good. Movement now resolves only against walls a move enters
(#762), and a move first pushes a collider out of the walls it overlaps along its shallower axis, so it slides along a
row of tiles it is partly in instead of pinning against the next tile (engine.physics_model.depenetrate, #764).
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from engine.physics_model import Aabb, EntityBox, MoveRequest, _sweep, depenetrate, sweep_axis_separate

pytestmark = pytest.mark.fast

WALL = Aabb(720, 176, 32, 32)  # y 160..192 (the smoke's wall tile under the arrival spot)


def _query(*walls: Aabb):
    return lambda box: [w for w in walls if box.intersection(w)]


def _move(box: Aabb, delta: tuple[float, float], *walls: Aabb, bounds=None):
    result = sweep_axis_separate(MoveRequest("p", (box.x, box.y), delta, box), _query(*walls), bounds)
    return Aabb(result.final_pos[0], result.final_pos[1], box.w, box.h), result


def test_feet_in_the_wall_below_walk_up_and_out() -> None:
    feet = Aabb(720, 190, 19, 12)  # y 184..196: 8 px into the wall
    moved, result = _move(feet, (0.0, 3.0), WALL)
    assert moved.bottom == pytest.approx(WALL.top + 3.0) and not result.hit_y, "lifted out (8 px), then the move"
    for _ in range(3):
        again, result = _move(moved, (0.0, 3.0), WALL)
        assert again.y == pytest.approx(moved.y + 3.0) and not result.hit_y
        moved = again


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
    assert moved.right == pytest.approx(wall.left - 3.0) and not result.hit_x, \
        "out (6 px), then the move (it used to snap across, to the wall's far side)"
    moved, result = _move(body, (3.0, 0.0), wall)
    assert result.hit_x and moved.right == pytest.approx(wall.left)
    moved, result = _move(Aabb(220, 100, 20, 20), (-3.0, 0.0), wall)  # 6 px in on its right side: right walks out
    assert result.hit_x and moved.left == pytest.approx(wall.right)
    moved, result = _move(Aabb(220, 100, 20, 20), (3.0, 0.0), wall)
    assert moved.left == pytest.approx(wall.right + 3.0) and not result.hit_x


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


def test_along_a_row_of_tiles_it_is_in_it_slides_freely_and_ends_out_of_the_row() -> None:
    """Feet 8 px into a floor row, holding right: lifted out of the row on the first frame (8 px, the shallower axis),
    then 3 px a frame along its top, flush and no longer in it. (Before #764 they stopped flush against the next tile
    and stayed pinned there, still 8 px in; before #763 they jumped ~32 px back every frame.)"""
    floor = _row(176.0, 0.0, 8)  # y 160..192, tiles x 0..256
    feet = Aabb(100, 190, 19, 12)  # x 90.5..109.5, y 184..196: over the tiles at x 64..96 and 96..128
    held = feet
    for frame in range(1, 31):
        held, result = _move(held, (3.0, 0.0), *floor)
        assert not result.hit_x and held.x == pytest.approx(feet.x + 3.0 * frame), "slides along, never pinned"
        assert held.bottom == pytest.approx(192.0) and not any(held.intersection(t) for t in floor), "on the row"
    held = feet
    for frame in range(1, 21):  # and to the left
        held, result = _move(held, (-3.0, 0.0), *floor)
        assert not result.hit_x and held.x == pytest.approx(feet.x - 3.0 * frame) and held.bottom == pytest.approx(192.0)


def test_along_a_side_column_it_is_in_it_slides_freely_too() -> None:
    column = [Aabb(116, 16 + 32 * i, 32, 32) for i in range(8)]  # a side wall column x 100..132
    side = Aabb(105, 100, 12, 19)  # x 99..111: 11 px into the column (its centre left of the column's)
    held = side
    for frame in range(1, 31):
        held, result = _move(held, (0.0, 3.0), *column)
        assert not result.hit_y and held.y == pytest.approx(side.y + 3.0 * frame), "slides along, never pinned"
        assert held.right == pytest.approx(100.0) and not any(held.intersection(t) for t in column)
    held, result = _move(side, (0.0, -3.0), *column)
    assert held.y == pytest.approx(side.y - 3.0) and held.right == pytest.approx(100.0)


def test_pushing_into_the_row_it_is_in_still_stops_flush() -> None:
    floor = _row(176.0, 0.0, 8)
    for delta in ((0.0, -3.0), (0.0, -400.0), (2.0, -3.0)):
        moved, result = _move(Aabb(100, 190, 19, 12), delta, *floor)
        assert result.hit_y and moved.bottom == pytest.approx(192.0), (delta, moved)
    column = [Aabb(116, 16 + 32 * i, 32, 32) for i in range(8)]
    moved, result = _move(Aabb(105, 100, 12, 19), (3.0, 0.0), *column)
    assert result.hit_x and moved.right == pytest.approx(100.0)


@pytest.mark.parametrize("centre", [288.5, 292.0, 296.0, 299.0, 299.9])  # ever nearer the wall's centre (x 300)
def test_a_thin_wall_is_never_crossed(centre: float) -> None:
    """A box partly over a thin wall is pushed out on its own side (the wall's extent decides), never the far one."""
    thin = Aabb(300, 100, 4, 200)  # x 298..302, y 0..200
    for delta in ((3.0, 0.0), (0.0, 3.0), (0.0, -3.0), (-3.0, 0.0), (100.0, 0.0), (3.0, 3.0)):
        moved, _ = _move(Aabb(centre, 100, 20, 20), delta, thin)
        assert moved.right <= thin.left + 1e-9, (centre, delta, moved)
        mirrored, _ = _move(Aabb(600 - centre, 100, 20, 20), (-delta[0], delta[1]), thin)  # the same from the right
        assert mirrored.left >= thin.right - 1e-9, (centre, delta, mirrored)


ROOM = (0.0, 0.0, 768.0, 512.0)
EDGE_WALL = Aabb(26, 100, 32, 32)  # x 10..42, y 84..116: a wall near the room's left edge
NEAR_EDGE = Aabb(11, 114, 12, 12)  # x 5..17 (7 px in from the wall's left), y 108..120 (8 px in from its top)


def test_near_the_room_edge_the_push_stays_inside() -> None:
    """The shallowest way out (7 px left) would put the box past the room's left edge (x -2): inside the room it goes
    up (8 px) instead, as a wall there would make it (keep_inside's rectangle)."""
    assert depenetrate(NEAR_EDGE, _query(EDGE_WALL)) == Aabb(4, 114, 12, 12), "an open map: the shallower push, left"
    assert depenetrate(NEAR_EDGE, _query(EDGE_WALL), ROOM) == Aabb(11, 122, 12, 12), "never past the room's edge"
    moved, result = _move(NEAR_EDGE, (0.0, -3.0), EDGE_WALL, bounds=ROOM)  # the sweep passes the room on
    assert result.hit_y and (moved.left, moved.bottom) == (5.0, pytest.approx(EDGE_WALL.top))


def test_inside_the_corner_of_an_l_it_is_pushed_out_of_both_walls() -> None:
    """Feet at the inside corner of a floor row and a side column, in both: one push takes them out of both (3.5 px
    right, 8 px up), then they walk on either way, and into the column stays flush."""
    row = _row(176.0, 0.0, 8)  # y 160..192, x 0..256
    column = [Aabb(16, 208 + 32 * i, 32, 32) for i in range(4)]  # x 0..32, from y 192 up
    walls = row + column
    feet = Aabb(38, 190, 19, 12)  # x 28.5..47.5 (3.5 px into the column), y 184..196 (8 px into the row)
    right, result = _move(feet, (3.0, 0.0), *walls)
    assert (right.left, right.bottom) == (pytest.approx(35.0), pytest.approx(192.0)) and not result.hit_x
    up, result = _move(feet, (0.0, 3.0), *walls)
    assert (up.left, up.bottom) == (pytest.approx(32.0), pytest.approx(195.0)) and not result.hit_y
    assert not any(m.intersection(w) for m in (right, up) for w in walls)
    left, result = _move(feet, (-3.0, 0.0), *walls)
    assert result.hit_x and left.left == pytest.approx(32.0) and left.bottom == pytest.approx(192.0), "flush, no deeper"


def test_exactly_as_deep_on_both_axes_it_goes_out_along_x() -> None:
    wall = Aabb(16, 16, 32, 32)  # x 0..32, y 0..32
    corner = Aabb(35, 35, 10, 10)  # x 30..40, y 30..40: 2 px in on each axis
    moved, _ = _move(corner, (0.0, 1.0), wall)
    assert (moved.x, moved.y) == (pytest.approx(37.0), pytest.approx(36.0))


def test_deep_inside_a_wall_it_is_not_teleported_but_can_still_walk_out() -> None:
    block = Aabb(100, 100, 96, 96)  # x/y 52..148: a big solid
    inside = Aabb(100, 130, 12, 12)  # y 124..136, wholly inside: the way out (24 px up) is longer than the box
    assert depenetrate(inside, _query(block)) is inside, "no push longer than the box"
    moved, result = _move(inside, (3.0, 0.0), block)
    assert (moved.x, moved.y) == (pytest.approx(103.0), 130.0) and not result.hit_x
    moved, result = _move(inside, (0.0, 3.0), block)
    assert moved.y == pytest.approx(133.0) and not result.hit_y, "axis_stop's walk-out rule still frees it"


def test_a_way_out_that_ends_in_another_wall_is_not_taken() -> None:
    below, above = Aabb(16, 16, 32, 32), Aabb(16, 58, 32, 32)  # y 0..32 and 42..74: a 10 px gap
    feet = Aabb(16, 34, 20, 12)  # y 28..40: 4 px into the wall below; out (y 32..44) it would be in the one above
    assert depenetrate(feet, _query(below, above)) is feet


def _random_walls(rng: random.Random) -> list[Aabb]:
    return [Aabb(16 + 32 * i, 16 + 32 * j, 32, 32) for i in range(10) for j in range(10) if rng.random() < 0.3]


def test_a_move_starting_clear_of_walls_is_bit_identical_to_before() -> None:
    """_sweep is the sweep as it was before #764 (unchanged): with no overlap at the start, the result is the same,
    from the same wall queries."""
    rng = random.Random(764)
    checked = 0
    while checked < 3000:
        walls = _random_walls(rng)
        box = Aabb(rng.uniform(0, 320), rng.uniform(0, 320), rng.uniform(6, 40), rng.uniform(6, 40))
        if rng.random() < 0.3 and walls:  # flush against a wall's side
            w = rng.choice(walls)
            box = Aabb(w.left - box.w / 2, w.y, box.w, box.h)
        if any(box.intersection(w) for w in walls):
            continue
        delta = (rng.choice([0.0, rng.uniform(-60, 60)]), rng.choice([0.0, rng.uniform(-60, 60)]))
        req = MoveRequest("p", (box.x, box.y), delta, box)
        bounds = rng.choice([None, (0.0, 0.0, 320.0, 320.0)])
        asked: list[list[Aabb]] = [[], []]

        def counted(log: list[Aabb]):
            return lambda aabb: (log.append(aabb), _query(*walls)(aabb))[1]

        assert sweep_axis_separate(req, counted(asked[0]), bounds) == _sweep(req, counted(asked[1])), (box, delta)
        assert asked[0] == asked[1], "no extra wall query (the first step's answer is reused)"
        checked += 1


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


def _overlap(a: _Sprite, others: list[_Sprite]) -> list[_Sprite]:  # as Arcade's check_for_collision_with_list
    return [o for o in others
            if o is not a and a.right > o.left and a.left < o.right and a.top > o.bottom and a.bottom < o.top]


def test_the_scene_controller_mover_walks_out_of_a_wall_too(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_controller_core as core
    from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision

    monkeypatch.setattr(core.optional_arcade, "arcade", SimpleNamespace(check_for_collision_with_list=_overlap))
    wall = _Sprite(720, 176, 32, 32)
    controller = SimpleNamespace(solid_sprites=[wall])
    enemy = _Sprite(720, 196, 20, 20)  # y 186..206: 6 px into the wall below (still in after a 3 px step)
    move_entity_with_collision(controller, enemy, 0.0, 3.0)
    assert enemy.center_y == pytest.approx(205.0), "out (6 px), then away (it used to snap to the wall's far edge, y 150)"
    enemy.center_y = 196.0
    move_entity_with_collision(controller, enemy, 0.0, -3.0)
    assert enemy.bottom == pytest.approx(wall.top), "deeper stays blocked, flush on the side it came from"
    enemy.center_y = 230.0
    move_entity_with_collision(controller, enemy, 0.0, -100.0)
    assert enemy.bottom == pytest.approx(wall.top), "approaching still stops flush"
    side = _Sprite(600, 176, 20, 20)
    move_entity_with_collision(controller, side, 500.0, 0.0)
    assert side.right == pytest.approx(wall.left), "and a fast move still can't tunnel through"


class _Solid(_Sprite):
    """A solid entity: entity data, with a box collider of its own size (so the player mover reads it without Arcade).
    Map collision tiles carry no entity data (_Sprite, _tile_row)."""

    def __init__(self, x: float, y: float, w: float = 32.0, h: float = 32.0) -> None:
        super().__init__(x, y, w, h)
        self.mesh_entity_data = {"id": "solid", "components": {"collider": {"kind": "box", "w": w, "h": h}}}


def _tile_row() -> list[_Sprite]:
    return [_Sprite(16 + 32 * i, 176.0, 32.0, 32.0) for i in range(8)]  # map collision tiles: y 160..192, x 0..256


def test_the_player_mover_slides_along_a_tile_row_even_when_solid_and_keeps_the_room_on_a_push() -> None:
    """move_entity_with_physics (the player; World.move's default sweep). A solid mover is in the solids list itself:
    its own collider is an entity it is already in, so it is neither pushed out of nor in the way of a push."""
    from engine.physics_runtime import move_entity_with_physics

    feet = _Solid(100, 190, 19, 12)
    solids = _tile_row() + [feet]
    for _ in range(10):
        move_entity_with_physics(feet, (3.0, 0.0), solids)
    assert (feet.center_x, feet.bottom) == (pytest.approx(130.0), pytest.approx(192.0))
    box = _Solid(NEAR_EDGE.x, NEAR_EDGE.y, 12, 12)
    move_entity_with_physics(box, (0.0, -3.0), [_Sprite(EDGE_WALL.x, EDGE_WALL.y, 32, 32)], ROOM)
    assert (box.left, box.bottom) == (5.0, pytest.approx(EDGE_WALL.top)), "pushed up, not out of the room"


def _scene_controller(monkeypatch: pytest.MonkeyPatch, solids: list, room=None) -> SimpleNamespace:
    import engine.scene_controller_core as core

    monkeypatch.setattr(core.optional_arcade, "arcade", SimpleNamespace(check_for_collision_with_list=_overlap))
    window = SimpleNamespace(camera_controller=SimpleNamespace(world_rect=lambda: room))
    return SimpleNamespace(solid_sprites=solids, window=window)


def test_the_scene_controller_mover_slides_along_a_tile_row_and_keeps_the_room_too(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision

    enemy = _Solid(100, 190, 19, 12)
    controller = _scene_controller(monkeypatch, _tile_row() + [enemy])  # (Arcade skips the mover itself)
    for _ in range(10):
        move_entity_with_collision(controller, enemy, 3.0, 0.0)
    assert (enemy.center_x, enemy.bottom) == (pytest.approx(130.0), pytest.approx(192.0))
    box = _Sprite(NEAR_EDGE.x, NEAR_EDGE.y, 12, 12)
    controller = _scene_controller(monkeypatch, [_Sprite(EDGE_WALL.x, EDGE_WALL.y, 32, 32)], ROOM)
    move_entity_with_collision(controller, box, 0.0, -3.0)
    assert (box.left, box.bottom) == (5.0, pytest.approx(EDGE_WALL.top)), "pushed up, not out of the room"


def test_both_movers_agree_on_random_moves_overlapping_or_not(monkeypatch: pytest.MonkeyPatch) -> None:
    """The player's sweep and the SceneController mover share axis_stop and depenetrate: same walls, same ends."""
    from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision

    rng = random.Random(7640)
    overlapping = 0
    for _ in range(1500):
        walls = _random_walls(rng)
        # Quarter-pixel values and one-piece moves keep the arithmetic exact: the two movers' float noise at a flush
        # contact differs (as before #764), which is not what this compares.
        box = Aabb(rng.randrange(1280) / 4, rng.randrange(1280) / 4, rng.randrange(12, 80) / 2, rng.randrange(12, 80) / 2)
        overlapping += any(box.intersection(w) for w in walls)
        delta = (rng.choice([0.0, rng.randrange(-int(box.w), int(box.w) + 1) / 2]),
                 rng.choice([0.0, rng.randrange(-int(box.h), int(box.h) + 1) / 2]))
        moved, _ = _move(box, delta, *walls)
        sprite = _Sprite(box.x, box.y, box.w, box.h)
        controller = _scene_controller(monkeypatch, [_Sprite(w.x, w.y, w.w, w.h) for w in walls])
        move_entity_with_collision(controller, sprite, *delta)
        assert (sprite.center_x, sprite.center_y) == (moved.x, moved.y), (box, delta)
    assert overlapping > 300, "the sample must include many starts inside walls"


def test_the_network_mover_slides_along_a_tile_row_even_in_its_own_solids() -> None:
    """mesh_net.scene_room.move (the authority and a client's prediction run this one step): its tile bodies carry no
    entity data; an enemy walking a route is an entity in the solids it walks through."""
    from mesh_net.scene_room import Body, move

    row = [Body(16 + 32 * i, 176.0, 32, 32, {}) for i in range(8)]
    walker = Body(100, 190, 19, 12, {"id": "walker"})
    for _ in range(10):
        move(walker, (3.0, 0.0), row + [walker])
    assert (walker.center_x, walker.center_y) == (pytest.approx(130.0), pytest.approx(198.0))


HERO = Aabb(100, 100, 19, 12)  # x 90.5..109.5
NPC = Aabb(110, 100, 32, 32)  # x 94..126: a solid NPC 15.5 px into the hero from its right


def test_a_solid_entity_the_mover_overlaps_never_pushes_it_sideways(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only wall tiles are pushed out of (#764 is about rows of them): an NPC walking through the player must not
    shove it aside when it moves. axis_stop's walk-out rule frees it (walking up is free; walking into it stops)."""
    from engine.physics_runtime import move_entity_with_physics
    from engine.scene_controller_parts.gameplay_runtime import move_entity_with_collision
    from mesh_net.scene_room import Body, move

    moved, _ = _move(HERO, (0.0, 3.0), EntityBox(NPC.x, NPC.y, NPC.w, NPC.h))
    assert (moved.x, moved.y) == (HERO.x, HERO.y + 3.0), "pure model: an EntityBox is never pushed out of"
    assert _move(HERO, (0.0, 3.0), NPC)[0].x == pytest.approx(HERO.x - 15.5), "(a wall tile there would be)"

    hero = _Solid(HERO.x, HERO.y, HERO.w, HERO.h)
    move_entity_with_physics(hero, (0.0, 3.0), [_Solid(NPC.x, NPC.y, NPC.w, NPC.h)])
    assert (hero.center_x, hero.center_y) == (HERO.x, HERO.y + 3.0), "the player mover"

    sprite = _Sprite(HERO.x, HERO.y, HERO.w, HERO.h)
    move_entity_with_collision(_scene_controller(monkeypatch, [_Solid(NPC.x, NPC.y, NPC.w, NPC.h)]), sprite, 0.0, 3.0)
    assert (sprite.center_x, sprite.center_y) == (HERO.x, HERO.y + 3.0), "the SceneController mover"

    walker = Body(HERO.x, HERO.y, HERO.w, HERO.h, {"id": "hero"})
    move(walker, (0.0, 3.0), [Body(NPC.x, NPC.y, NPC.w, NPC.h, {"id": "npc"})])
    assert (walker.center_x, walker.center_y) == (HERO.x, HERO.y + 3.0), "the network mover"


@pytest.mark.parametrize("overlap", [2.0, 3.0, 6.0])
def test_in_hd2d_a_push_into_a_world_wall_is_dropped_so_the_player_still_walks_along_it(overlap: float) -> None:
    """Feet flush against a World wall (floor geometry, which the 2D push doesn't know), a wall tile `overlap` px into
    them from the other side: the push (into the World wall) ends where World._step's floors refuse it. The step goes
    again without the push, so the player walks along the wall as before #764 instead of being refused every frame."""
    from pathlib import Path

    from engine.hd2d.glb import Collider, Model
    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import World
    from engine.physics_model import entity_aabb

    settings = parse_hd2d({"structures": [{"id": "s", "model": "m.glb", "x": 0, "y": 0}],
                           "ground": {"from": [-320, -320], "to": [320, 320]}})
    for d in (3.0, -3.0):
        world = World(settings, {"m.glb": Model(Path("m.glb"), [], [Collider("w", "wall", [], (1.0, -5, 0),
                                                                              (1.05, 5, 3))])})  # x 32..33.6 px
        hero = SimpleNamespace(center_x=22.5, center_y=18.0, width=32.0, height=48.0, scale_x=1.0,
                               mesh_entity_data={"elevation": 0.0, "components": {"collider": {"kind": "box", "auto": True}}})
        hero.center_x += 32.0 - entity_aabb(hero).right  # feet flush against the World wall
        feet = entity_aabb(hero)
        tile = SimpleNamespace(center_x=feet.left + overlap - 16.0, center_y=feet.y, width=32.0, height=32.0)
        start = (hero.center_x, hero.center_y)
        for _ in range(5):
            world.move(hero, (0.0, d), [tile])
        assert (hero.center_x, hero.center_y) == (start[0], pytest.approx(start[1] + 5 * d)), (overlap, d)
