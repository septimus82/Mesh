from __future__ import annotations

import math


def test_patrol_chase_patrols_when_no_target() -> None:
    from engine.behaviours.patrol_chase import PatrolChaseBehaviour
    from engine.pathfinding import NavGrid

    class _Entity:
        def __init__(self, x: float, y: float, *, entity_id: str, tag: str) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_tag = tag
            self.mesh_entity_data = {"id": entity_id}

    class _Scene:
        def __init__(self, grid: NavGrid, sprites: list[_Entity]) -> None:
            self._grid = grid
            self._sprites = sprites

        def get_nav_grid(self) -> NavGrid:
            return self._grid

        def get_all_entities(self) -> list[_Entity]:
            return list(self._sprites)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

        def move_entity_with_collision(self, sprite: _Entity, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG002
            sprite.center_x += float(dx)
            sprite.center_y += float(dy)

    grid = NavGrid(width=20, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((15, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = PatrolChaseBehaviour(
        chaser,
        window,
        patrol_points=[{"x": 0.0, "y": 8.0}, {"x": 80.0, "y": 8.0}],
        patrol_speed=40.0,
        target_tag="player",
        acquire_radius_tiles=2,
        leash_radius_tiles=4,
        chase_speed=80.0,
    )

    x0 = chaser.center_x
    for _ in range(10):
        beh.update(0.1)
    assert beh.state == "patrol"
    assert chaser.center_x > x0


def test_patrol_chase_switches_to_chase_and_back_to_patrol_on_leash_break() -> None:
    from engine.behaviours.patrol_chase import PatrolChaseBehaviour
    from engine.pathfinding import NavGrid

    class _Entity:
        def __init__(self, x: float, y: float, *, entity_id: str, tag: str) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_tag = tag
            self.mesh_entity_data = {"id": entity_id}

    class _Scene:
        def __init__(self, grid: NavGrid, sprites: list[_Entity]) -> None:
            self._grid = grid
            self._sprites = sprites

        def get_nav_grid(self) -> NavGrid:
            return self._grid

        def get_all_entities(self) -> list[_Entity]:
            return list(self._sprites)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

        def move_entity_with_collision(self, sprite: _Entity, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG002
            sprite.center_x += float(dx)
            sprite.center_y += float(dy)

    grid = NavGrid(width=50, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((20, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = PatrolChaseBehaviour(
        chaser,
        window,
        patrol_points=[{"x": 0.0, "y": 8.0}, {"x": 160.0, "y": 8.0}],
        patrol_speed=20.0,
        target_tag="player",
        acquire_radius_tiles=4,
        leash_radius_tiles=6,
        stop_range_tiles=2,
        chase_speed=80.0,
        return_to_patrol=True,
        resume_waypoint_mode="nearest",
    )

    # Target enters range -> chase.
    target.center_x, target.center_y = grid.tile_center_world((2, 0))
    for _ in range(3):
        beh.update(0.1)
    assert beh.state == "chase"

    x0 = chaser.center_x
    for _ in range(5):
        beh.update(0.1)
    assert chaser.center_x == x0

    # Target leaves leash -> disengage -> return -> patrol.
    target.center_x, target.center_y = grid.tile_center_world((40, 0))
    for _ in range(30):
        beh.update(0.1)
    assert beh.state == "patrol"


def test_patrol_chase_unreachable_target_gives_up_and_returns_to_patrol() -> None:
    from engine.behaviours.patrol_chase import PatrolChaseBehaviour
    from engine.pathfinding import NavGrid

    class _Entity:
        def __init__(self, x: float, y: float, *, entity_id: str, tag: str) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_tag = tag
            self.mesh_entity_data = {"id": entity_id}

    class _Scene:
        def __init__(self, grid: NavGrid, sprites: list[_Entity]) -> None:
            self._grid = grid
            self._sprites = sprites

        def get_nav_grid(self) -> NavGrid:
            return self._grid

        def get_all_entities(self) -> list[_Entity]:
            return list(self._sprites)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

        def move_entity_with_collision(self, sprite: _Entity, dx: float, dy: float, friction: float = 1.0) -> None:  # noqa: ARG002
            sprite.center_x += float(dx)
            sprite.center_y += float(dy)

    width, height = 20, 1
    blocked = {0 * width + 3}
    grid = NavGrid(width=width, height=height, tile_w=16, tile_h=16, blocked=frozenset(blocked))

    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((3, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = PatrolChaseBehaviour(
        chaser,
        window,
        patrol_points=[{"x": 0.0, "y": 8.0}, {"x": 80.0, "y": 8.0}],
        patrol_speed=20.0,
        target_tag="player",
        acquire_radius_tiles=10,
        leash_radius_tiles=10,
        chase_speed=80.0,
        give_up_ticks=2,
        cooldown_ticks=999,
        return_to_patrol=True,
    )

    for _ in range(30):
        beh.update(0.1)
    assert beh.state in {"return", "patrol"}
    assert beh._cooldown_remaining > 0  # noqa: SLF001


def test_patrol_chase_los_required_blocks_switch_to_chase() -> None:
    from engine.behaviours.patrol_chase import PatrolChaseBehaviour
    from engine.pathfinding import NavGrid

    class _Entity:
        def __init__(self, x: float, y: float, *, entity_id: str, tag: str) -> None:
            self.center_x = float(x)
            self.center_y = float(y)
            self.mesh_tag = tag
            self.mesh_entity_data = {"id": entity_id}

    class _Scene:
        def __init__(self, grid: NavGrid, sprites: list[_Entity]) -> None:
            self._grid = grid
            self._sprites = sprites

        def get_nav_grid(self) -> NavGrid:
            return self._grid

        def get_all_entities(self) -> list[_Entity]:
            return list(self._sprites)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

        def move_entity_with_collision(self, *_a, **_k) -> None:
            return

    width, height = 10, 1
    blocked = {0 * width + 1}
    grid = NavGrid(width=width, height=height, tile_w=16, tile_h=16, blocked=frozenset(blocked))

    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((2, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = PatrolChaseBehaviour(
        chaser,
        window,
        patrol_points=[{"x": 0.0, "y": 8.0}, {"x": 80.0, "y": 8.0}],
        patrol_speed=20.0,
        target_tag="player",
        acquire_radius_tiles=5,
        leash_radius_tiles=8,
        chase_speed=80.0,
        los_required=True,
    )

    for _ in range(10):
        beh.update(0.1)
    assert beh.state == "patrol"
