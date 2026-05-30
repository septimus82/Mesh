"""Lock tests for Tier 3.0c — PatrolChase acquisition-helper reuse.

Verifies three invariants of Option A:
1. _build_chase is called exactly once across N no-target patrol ticks (helper reuse).
2. _build_chase is called exactly twice on acquisition (1 helper + 1 promoted chaser).
3. The acquisition outcome (target id, transition tick) is unchanged.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------

def _make_env(
    *,
    grid_width: int = 30,
    target_tile: int = 20,
    acquire_radius_tiles: int = 4,
):
    """Return (grid, chaser_entity, target_entity, scene, window) for a 1-row grid."""
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

        def move_entity_with_collision(
            self, sprite: _Entity, dx: float, dy: float, friction: float = 1.0  # noqa: ARG002
        ) -> None:
            sprite.center_x += float(dx)
            sprite.center_y += float(dy)

    grid = NavGrid(width=grid_width, height=1, tile_w=16, tile_h=16, blocked=frozenset())
    chaser = _Entity(*grid.tile_center_world((0, 0)), entity_id="chaser", tag="enemy")
    target = _Entity(
        *grid.tile_center_world((target_tile, 0)), entity_id="target", tag="player"
    )
    scene = _Scene(grid, [chaser, target])
    window = _Window(scene)
    return grid, chaser, target, scene, window


def _make_beh(chaser, window, *, acquire_radius_tiles: int = 4, **kwargs):
    from engine.behaviours.patrol_chase import PatrolChaseBehaviour

    return PatrolChaseBehaviour(
        chaser,
        window,
        patrol_points=[{"x": 0.0, "y": 8.0}, {"x": 160.0, "y": 8.0}],
        patrol_speed=20.0,
        target_tag="player",
        acquire_radius_tiles=acquire_radius_tiles,
        leash_radius_tiles=acquire_radius_tiles + 4,
        chase_speed=80.0,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test 1: helper is reused, not rebuilt, across no-target patrol ticks
# ---------------------------------------------------------------------------

def test_acquire_helper_is_reused_across_no_target_ticks() -> None:
    """_build_chase must be called exactly once across N no-target patrol ticks."""
    grid, chaser, target, scene, window = _make_env(
        grid_width=30, target_tile=25, acquire_radius_tiles=3
    )
    # Target is far out of acquire range (tile 25 > radius 3).
    beh = _make_beh(chaser, window, acquire_radius_tiles=3)

    build_count = [0]
    original_build = beh._build_chase  # noqa: SLF001

    def _spy_build():
        build_count[0] += 1
        return original_build()

    beh._build_chase = _spy_build  # noqa: SLF001

    N = 5
    for _ in range(N):
        beh.update(0.1)

    assert beh.state == "patrol", f"expected patrol, got {beh.state!r}"
    assert build_count[0] == 1, (
        f"_build_chase called {build_count[0]}× across {N} no-target ticks; expected exactly 1"
    )


# ---------------------------------------------------------------------------
# Test 2: exactly 2 constructions on acquisition (1 helper + 1 promoted chaser)
# ---------------------------------------------------------------------------

def test_fresh_chaser_built_on_acquisition() -> None:
    """_build_chase called exactly 2× total: once for the helper, once for the promoted chaser."""
    grid, chaser, target, scene, window = _make_env(
        grid_width=30, target_tile=25, acquire_radius_tiles=3
    )
    beh = _make_beh(chaser, window, acquire_radius_tiles=3)

    build_count = [0]
    original_build = beh._build_chase  # noqa: SLF001

    def _spy_build():
        build_count[0] += 1
        return original_build()

    beh._build_chase = _spy_build  # noqa: SLF001

    # Run a handful of no-target ticks first (helper built on tick 1, reused after).
    for _ in range(4):
        beh.update(0.1)
    assert beh.state == "patrol"
    assert build_count[0] == 1, (
        f"expected 1 build after no-target phase, got {build_count[0]}"
    )

    # Now bring the target into acquire range.
    target.center_x, target.center_y = grid.tile_center_world((1, 0))
    beh.update(0.1)

    assert beh.state == "chase", f"expected chase after target enters range, got {beh.state!r}"
    assert build_count[0] == 2, (
        f"_build_chase called {build_count[0]}× on acquisition; expected exactly 2 "
        f"(1 helper + 1 promoted chaser)"
    )

    # The _acquire_helper must not be the same object as _chase (helper never promoted).
    assert beh._acquire_helper is not beh._chase, (  # noqa: SLF001
        "acquire_helper must remain distinct from the promoted _chase (Option A invariant)"
    )


# ---------------------------------------------------------------------------
# Test 3: acquisition outcome is correct (target id + transition tick unchanged)
# ---------------------------------------------------------------------------

def test_acquisition_outcome_correct() -> None:
    """After patrol→chase, _chase._target_id equals the target entity id."""
    grid, chaser, target, scene, window = _make_env(
        grid_width=30, target_tile=25, acquire_radius_tiles=3
    )
    beh = _make_beh(chaser, window, acquire_radius_tiles=3)

    # Target starts out of range; bring it in on tick 3.
    in_range_tick: int | None = None
    for tick in range(1, 10):
        if tick == 3:
            target.center_x, target.center_y = grid.tile_center_world((1, 0))
            in_range_tick = tick
        beh.update(0.1)
        if beh.state == "chase":
            transition_tick = tick
            break
    else:
        pytest.fail("state never transitioned to 'chase'")

    assert in_range_tick is not None
    assert transition_tick == in_range_tick, (
        f"expected transition on tick {in_range_tick}, got tick {transition_tick}"
    )

    chase = beh._chase  # noqa: SLF001
    assert chase is not None, "_chase must not be None after transition"
    assert chase._target_id == "target", (  # noqa: SLF001
        f"expected _target_id='target', got {chase._target_id!r}"
    )
