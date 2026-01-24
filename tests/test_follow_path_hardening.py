from __future__ import annotations


def test_follow_path_unreachable_goal_stable() -> None:
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

    width, height = 4, 2
    goal_tile = (2, 0)
    blocked = {goal_tile[1] * width + goal_tile[0]}
    grid = NavGrid(width=width, height=height, tile_w=16, tile_h=16, blocked=frozenset(blocked))
    scene = _Scene(grid)
    window = _Window(scene)
    entity = _Entity()

    goal_x, goal_y = grid.tile_center_world(goal_tile)
    beh = FollowPathBehaviour(
        entity,
        window,
        goal_x=goal_x,
        goal_y=goal_y,
        speed=64.0,
        repath_interval=0.0,
        repath_min_ticks=1,
        no_path_repath_ticks=50,
        arrive_dist=0.5,
        diag=False,
    )

    for _ in range(20):
        beh.update(0.1)

    assert beh.state == "no_path"
    assert beh.repath_count == 1
    assert entity.center_x == 8.0
    assert entity.center_y == 8.0


def test_follow_path_moving_target_repath_throttled() -> None:
    from engine.behaviours.follow_path import FollowPathBehaviour
    from engine.pathfinding import NavGrid

    class _Entity:
        def __init__(self, x: float, y: float, name: str) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_name = name

    class _Scene:
        def __init__(self, grid: NavGrid) -> None:
            self._grid = grid

        def get_nav_grid(self) -> NavGrid:
            return self._grid

        def move_entity_with_collision(self, *_a, **_k) -> None:
            return

    class _Window:
        def __init__(self, scene: _Scene, target: _Entity) -> None:
            self.scene_controller = scene
            self._target = target

        def find_sprite_by_name(self, name: str):  # noqa: ANN001
            if name == self._target.mesh_name:
                return self._target
            return None

    grid = NavGrid(width=10, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    scene = _Scene(grid)
    target = _Entity(*grid.tile_center_world((1, 0)), name="Target")
    window = _Window(scene, target)
    follower = _Entity(*grid.tile_center_world((0, 0)), name="Follower")

    beh = FollowPathBehaviour(
        follower,
        window,
        target_name="Target",
        speed=64.0,
        repath_interval=0.0,
        repath_min_ticks=3,
        no_path_repath_ticks=10,
        arrive_dist=0.5,
        diag=False,
    )

    for _ in range(5):
        beh.update(0.1)
    assert beh.repath_count == 1

    target.center_x, target.center_y = grid.tile_center_world((2, 0))
    for _ in range(2):
        beh.update(0.1)
    assert beh.repath_count == 1

    beh.update(0.1)
    assert beh.repath_count == 2

    target.center_x, target.center_y = grid.tile_center_world((4, 0))
    for _ in range(3):
        beh.update(0.1)
    assert beh.repath_count == 3

