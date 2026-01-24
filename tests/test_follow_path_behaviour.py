from __future__ import annotations

import math


def test_follow_path_behaviour_reaches_goal_and_stops() -> None:
    from engine.behaviours.follow_path import FollowPathBehaviour
    from engine.pathfinding import NavGrid

    class _Entity:
        def __init__(self) -> None:
            self.center_x = 8.0
            self.center_y = 8.0

    class _Scene:
        def __init__(self, grid: NavGrid) -> None:
            self._grid = grid

        def get_nav_grid(self) -> NavGrid:
            return self._grid

        def move_entity_with_collision(self, entity: _Entity, dx: float, dy: float) -> None:
            entity.center_x += float(dx)
            entity.center_y += float(dy)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

    grid = NavGrid(width=6, height=2, tile_w=16, tile_h=16, blocked=frozenset())
    scene = _Scene(grid)
    window = _Window(scene)
    entity = _Entity()

    goal_x, goal_y = grid.tile_center_world((2, 0))
    beh = FollowPathBehaviour(
        entity,
        window,
        goal_x=goal_x,
        goal_y=goal_y,
        speed=64.0,
        repath_interval=0.0,
        arrive_dist=0.5,
        diag=False,
    )

    for _ in range(20):
        beh.update(0.1)

    assert math.isclose(entity.center_x, goal_x, abs_tol=0.75)
    assert math.isclose(entity.center_y, goal_y, abs_tol=0.75)

    x0, y0 = entity.center_x, entity.center_y
    beh.update(0.1)
    beh.update(0.1)
    assert entity.center_x == x0
    assert entity.center_y == y0

