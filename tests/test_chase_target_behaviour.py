from __future__ import annotations


def test_chase_target_chases_when_in_range() -> None:
    from engine.behaviours.chase_target import ChaseTargetBehaviour
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

        def move_entity_with_collision(self, entity: _Entity, dx: float, dy: float) -> None:
            entity.center_x += float(dx)
            entity.center_y += float(dy)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

    grid = NavGrid(width=10, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((2, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = ChaseTargetBehaviour(
        chaser,
        window,
        target_tag="player",
        acquire_radius_tiles=5,
        leash_radius_tiles=8,
        speed=64.0,
        give_up_ticks=5,
        cooldown_ticks=5,
        los_required=False,
        repath_min_ticks=1,
        no_path_repath_ticks=10,
    )

    x0 = chaser.center_x
    for _ in range(5):
        beh.update(0.1)
    assert beh.state == "chase"
    assert chaser.center_x > x0


def test_chase_target_stops_within_stop_range_tiles() -> None:
    from engine.behaviours.chase_target import ChaseTargetBehaviour
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

        def move_entity_with_collision(self, entity: _Entity, dx: float, dy: float) -> None:
            entity.center_x += float(dx)
            entity.center_y += float(dy)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

    grid = NavGrid(width=10, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((1, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = ChaseTargetBehaviour(
        chaser,
        window,
        target_tag="player",
        acquire_radius_tiles=5,
        leash_radius_tiles=8,
        stop_range_tiles=2,
        speed=64.0,
        give_up_ticks=5,
        cooldown_ticks=5,
        repath_min_ticks=1,
        no_path_repath_ticks=10,
    )

    x0, y0 = chaser.center_x, chaser.center_y
    for _ in range(10):
        beh.update(0.1)
    assert beh.state == "chase"
    assert chaser.center_x == x0
    assert chaser.center_y == y0


def test_chase_target_disengages_when_target_leaves_leash() -> None:
    from engine.behaviours.chase_target import ChaseTargetBehaviour
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

        def move_entity_with_collision(self, entity: _Entity, dx: float, dy: float) -> None:
            entity.center_x += float(dx)
            entity.center_y += float(dy)

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

    grid = NavGrid(width=30, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((2, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = ChaseTargetBehaviour(
        chaser,
        window,
        target_tag="player",
        acquire_radius_tiles=5,
        leash_radius_tiles=6,
        speed=64.0,
        give_up_ticks=5,
        cooldown_ticks=5,
        repath_min_ticks=1,
    )

    beh.update(0.1)
    assert beh.state == "chase"

    target.center_x, target.center_y = grid.tile_center_world((20, 0))
    beh.update(0.1)
    assert beh.state == "idle"


def test_chase_target_unreachable_target_gives_up_deterministically() -> None:
    from engine.behaviours.chase_target import ChaseTargetBehaviour
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

        def move_entity_with_collision(self, *_a, **_k) -> None:
            return

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

    width, height = 6, 1
    goal = (3, 0)
    blocked = {goal[1] * width + goal[0]}
    grid = NavGrid(width=width, height=height, tile_w=16, tile_h=16, blocked=frozenset(blocked))
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world(goal), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = ChaseTargetBehaviour(
        chaser,
        window,
        target_tag="player",
        acquire_radius_tiles=10,
        leash_radius_tiles=10,
        speed=64.0,
        give_up_ticks=3,
        cooldown_ticks=100,
        repath_min_ticks=1,
        no_path_repath_ticks=100,
    )

    for _ in range(10):
        beh.update(0.1)
    assert beh.state == "cooldown"


def test_chase_target_los_blocks_acquisition() -> None:
    from engine.behaviours.chase_target import ChaseTargetBehaviour
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

        def move_entity_with_collision(self, *_a, **_k) -> None:
            return

    class _Window:
        def __init__(self, scene: _Scene) -> None:
            self.scene_controller = scene

    width, height = 5, 1
    blocked = {0 * width + 1}
    grid = NavGrid(width=width, height=height, tile_w=16, tile_h=16, blocked=frozenset(blocked))
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(*grid.tile_center_world((2, 0)), entity_id="target", tag="player")
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)

    beh = ChaseTargetBehaviour(
        chaser,
        window,
        target_tag="player",
        acquire_radius_tiles=5,
        leash_radius_tiles=8,
        speed=64.0,
        los_required=True,
    )

    for _ in range(5):
        beh.update(0.1)
    assert beh.state == "idle"
