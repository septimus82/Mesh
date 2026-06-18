from __future__ import annotations

from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine import physics_runtime
from engine.perf import PerfStats
from engine.physics_model import Aabb, MoveRequest, sweep_axis_separate

pytestmark = [pytest.mark.fast]


class _Sprite:
    def __init__(
        self,
        sid: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        circle_radius: float | None = None,
        is_sensor: bool = False,
        layer: str | None = None,
    ) -> None:
        self.id = sid
        self.center_x = x
        self.center_y = y
        self.width = w
        self.height = h
        if circle_radius is not None:
            self.collider_kind = "circle"
            self.collider_radius = float(circle_radius)
        self.is_sensor = bool(is_sensor)
        if layer is not None:
            self.mesh_layer = str(layer)


def _no_collision(_proxy: Any, _sprites: Any) -> list[Any]:
    return []


def _prepare_query_state(monkeypatch: pytest.MonkeyPatch, colliders: list[Any]) -> None:
    monkeypatch.setattr(
        optional_arcade.arcade,
        "check_for_collision_with_list",
        _no_collision,
    )
    physics_runtime.reset_broadphase_cache()
    physics_runtime.set_broadphase_enabled(True)
    mover = _Sprite("mover", 0.0, 0.0, 2.0, 2.0)
    # Builds/updates runtime collider cache used by query_overlaps_circle.
    physics_runtime.move_entity_with_physics(mover, (0.0, 0.0), colliders)


def test_query_overlaps_circle_returns_expected_set_and_sorted_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliders = [
        _Sprite("z_far", 20.0, 0.0, 2.0, 2.0),
        _Sprite("b_circle", 0.0, 3.0, 2.0, 2.0, circle_radius=1.0),
        _Sprite("a_box", 2.0, 0.0, 2.0, 2.0),
    ]
    _prepare_query_state(monkeypatch, colliders)

    hits = physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0)
    assert hits == ["a_box", "b_circle"]


def test_query_overlaps_circle_boundary_touching_is_excluded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliders = [
        _Sprite("touch_aabb", 4.0, 0.0, 2.0, 2.0),   # nearest point at x=3 -> exactly radius distance
        _Sprite("touch_circle", 5.0, 0.0, 2.0, 2.0, circle_radius=2.0),  # distance 5, radii 3+2
    ]
    _prepare_query_state(monkeypatch, colliders)

    hits = physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0)
    assert hits == []


def test_query_overlaps_circle_include_sensors_and_solids_gating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliders = [
        _Sprite("solid", 1.0, 0.0, 2.0, 2.0, is_sensor=False),
        _Sprite("sensor", 1.0, 1.0, 2.0, 2.0, is_sensor=True),
    ]
    _prepare_query_state(monkeypatch, colliders)

    assert physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0, include_sensors=False, include_solids=True) == ["solid"]
    assert physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0, include_sensors=True, include_solids=False) == ["sensor"]


def test_query_overlaps_circle_layer_filter_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliders = [
        _Sprite("enemy_a", 1.0, 0.0, 2.0, 2.0, layer="enemies"),
        _Sprite("enemy_b", 2.0, 0.0, 2.0, 2.0, layer="enemies"),
        _Sprite("pickup", 1.0, 1.0, 2.0, 2.0, layer="pickups"),
    ]
    _prepare_query_state(monkeypatch, colliders)

    hits = physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0, layers={"enemies"})
    assert hits == ["enemy_a", "enemy_b"]


def test_query_overlaps_circle_fallback_full_scan_increments_perf_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliders = [
        _Sprite("near", 1.0, 0.0, 2.0, 2.0),
        _Sprite("far", 100.0, 0.0, 2.0, 2.0),
    ]
    _prepare_query_state(monkeypatch, colliders)
    physics_runtime.set_broadphase_enabled(True)
    monkeypatch.setattr(
        physics_runtime._BROADPHASE_CACHE,
        "get_candidates",
        lambda _aabb, _solids, _cache_key: [],
    )
    perf_stats = PerfStats()
    window = type("Window", (), {"perf_stats": perf_stats})()
    monkeypatch.setattr(optional_arcade.arcade, "get_window", lambda: window)

    hits = physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0)
    counters = perf_stats.snapshot().meta.get("counters", {})
    assert hits == ["near"]
    assert counters.get("physics.circle_query.fallback_full_scan.count") == 1


def test_query_overlaps_circle_candidate_no_hit_does_not_full_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliders = [
        _Sprite("near_cell", 16.0, 30.0, 8.0, 8.0),
        _Sprite("far", 100.0, 100.0, 8.0, 8.0),
    ]
    _prepare_query_state(monkeypatch, colliders)
    perf_stats = PerfStats()
    window = type("Window", (), {"perf_stats": perf_stats})()
    monkeypatch.setattr(optional_arcade.arcade, "get_window", lambda: window)

    hits = physics_runtime.query_overlaps_circle(16.0, 15.0, 8.0)
    counters = perf_stats.snapshot().meta.get("counters", {})

    assert hits == []
    assert physics_runtime.get_broadphase_stats()["candidate_count"] == 1
    assert counters.get("physics.circle_query.fallback_full_scan.count", 0) == 0


def test_aabb_only_collision_smoke_unchanged() -> None:
    wall = Aabb(20.0, 0.0, 10.0, 100.0)

    def _aabb_query(aabb: Aabb) -> list[Aabb]:
        return [wall] if aabb.intersection(wall) is not None else []

    req = MoveRequest(
        entity_id="mover",
        from_pos=(0.0, 0.0),
        delta=(20.0, 0.0),
        aabb=Aabb(0.0, 0.0, 10.0, 10.0),
    )
    result = sweep_axis_separate(req, _aabb_query)
    assert result.hit_x is True
    assert result.final_pos == pytest.approx((10.0, 0.0))


def test_query_overlaps_circle_result_matches_stored_solid_sprites_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Lock: seeding via move_entity_with_physics then querying returns the
    # correct in-range IDs whether _LAST_SOLID_SPRITES holds a copy or a ref.
    # Colliders are NOT mutated between move and query.
    colliders = [
        _Sprite("wall_a", 0.0, 1.5, 2.0, 2.0),   # nearest to origin: (0, 0.5), dist 0.5 < 3 → hit
        _Sprite("wall_c", 1.0, 0.0, 2.0, 2.0),   # nearest to origin: (0, 0),   dist 0.0 < 3 → hit
        _Sprite("wall_z", 8.0, 0.0, 2.0, 2.0),   # nearest to origin: (7, 0),   dist 7.0 > 3 → miss
    ]
    _prepare_query_state(monkeypatch, colliders)

    hits = physics_runtime.query_overlaps_circle(0.0, 0.0, 3.0)
    assert hits == ["wall_a", "wall_c"]
