"""Contract tests for render_sort_model.py.

Tests cover:
- Default render_layer=0 and depth_z=0 when absent
- y_sort mode orders by render_layer, then -y, then entity_id
- explicit_z mode orders by render_layer, then depth_z, then entity_id
- Deterministic tie-breaking by entity_id
- Stability of sort (same input = same output)
"""

from __future__ import annotations

import pytest

from engine.render_sort_model import (
    compute_render_sort_key,
    compute_sprite_render_sort_key,
    sort_entities_for_render,
    sort_sprites_for_render,
)


# -----------------------------------------------------------------------------
# Test compute_render_sort_key
# -----------------------------------------------------------------------------


class TestComputeRenderSortKey:
    """Tests for compute_render_sort_key function."""

    def test_default_values_when_absent(self) -> None:
        """Missing render_layer and depth_z should default to 0."""
        entity: dict = {"id": "e1"}
        key = compute_render_sort_key(entity)
        assert key[0] == 0  # render_layer
        assert key[2] == "e1"  # entity_id

    def test_explicit_render_layer(self) -> None:
        """render_layer should be read from entity dict."""
        entity: dict = {"id": "e1", "render_layer": 5}
        key = compute_render_sort_key(entity)
        assert key[0] == 5

    def test_y_sort_mode_uses_y_directly(self) -> None:
        """y_sort mode should use y directly (lower y = back, higher y = front)."""
        entity: dict = {"id": "e1", "y": 100.0}
        key = compute_render_sort_key(entity, sort_mode="y_sort")
        assert key[1] == 100.0

    def test_explicit_z_mode_uses_depth_z(self) -> None:
        """explicit_z mode should use depth_z directly."""
        entity: dict = {"id": "e1", "depth_z": 50.0}
        key = compute_render_sort_key(entity, sort_mode="explicit_z")
        assert key[1] == 50.0

    def test_entity_id_tie_breaker(self) -> None:
        """entity_id should be used for deterministic tie-breaking."""
        e1: dict = {"id": "alpha", "render_layer": 0, "y": 100.0}
        e2: dict = {"id": "beta", "render_layer": 0, "y": 100.0}
        key1 = compute_render_sort_key(e1)
        key2 = compute_render_sort_key(e2)
        assert key1 < key2  # "alpha" < "beta"


# -----------------------------------------------------------------------------
# Test sort_entities_for_render
# -----------------------------------------------------------------------------


class TestSortEntitiesForRender:
    """Tests for sort_entities_for_render function."""

    def test_sort_by_render_layer_primary(self) -> None:
        """Entities should be sorted by render_layer first."""
        entities = [
            {"id": "e1", "render_layer": 2, "y": 0.0},
            {"id": "e2", "render_layer": 0, "y": 0.0},
            {"id": "e3", "render_layer": 1, "y": 0.0},
        ]
        sorted_ents = sort_entities_for_render(entities)
        assert [e["id"] for e in sorted_ents] == ["e2", "e3", "e1"]

    def test_y_sort_within_same_layer(self) -> None:
        """Within same render_layer, higher y should draw later (be at end)."""
        entities = [
            {"id": "e1", "render_layer": 0, "y": 100.0},  # higher y = closer
            {"id": "e2", "render_layer": 0, "y": 50.0},   # lower y = further
            {"id": "e3", "render_layer": 0, "y": 75.0},
        ]
        sorted_ents = sort_entities_for_render(entities, sort_mode="y_sort")
        # Lower y (further back) should come first
        assert [e["id"] for e in sorted_ents] == ["e2", "e3", "e1"]

    def test_explicit_z_sort_within_same_layer(self) -> None:
        """explicit_z mode should sort by depth_z (lower = further back)."""
        entities = [
            {"id": "e1", "render_layer": 0, "depth_z": 10.0},
            {"id": "e2", "render_layer": 0, "depth_z": 5.0},
            {"id": "e3", "render_layer": 0, "depth_z": 15.0},
        ]
        sorted_ents = sort_entities_for_render(entities, sort_mode="explicit_z")
        assert [e["id"] for e in sorted_ents] == ["e2", "e1", "e3"]

    def test_deterministic_with_same_values(self) -> None:
        """Entities with same render_layer and y should sort by id."""
        entities = [
            {"id": "charlie", "render_layer": 0, "y": 50.0},
            {"id": "alpha", "render_layer": 0, "y": 50.0},
            {"id": "bravo", "render_layer": 0, "y": 50.0},
        ]
        sorted_ents = sort_entities_for_render(entities)
        assert [e["id"] for e in sorted_ents] == ["alpha", "bravo", "charlie"]

    def test_stability_multiple_calls(self) -> None:
        """Same input should produce same output on multiple calls."""
        entities = [
            {"id": "e2", "render_layer": 1, "y": 30.0},
            {"id": "e1", "render_layer": 0, "y": 50.0},
            {"id": "e3", "render_layer": 1, "y": 30.0},
        ]
        result1 = sort_entities_for_render(entities)
        result2 = sort_entities_for_render(entities)
        assert [e["id"] for e in result1] == [e["id"] for e in result2]


# -----------------------------------------------------------------------------
# Test sprite sorting
# -----------------------------------------------------------------------------


class MockSprite:
    """Mock sprite for testing."""

    def __init__(
        self,
        entity_id: str,
        center_y: float = 0.0,
        render_layer: int = 0,
        depth_z: float = 0.0,
    ) -> None:
        self.center_y = center_y
        self.mesh_entity_data = {
            "id": entity_id,
            "render_layer": render_layer,
            "depth_z": depth_z,
        }


class TestSpriteRenderSorting:
    """Tests for sprite sorting functions."""

    def test_compute_sprite_key_uses_center_y(self) -> None:
        """Sprite center_y should be used for y_sort mode."""
        sprite = MockSprite("e1", center_y=75.0)
        key = compute_sprite_render_sort_key(sprite, sort_mode="y_sort")
        assert key[1] == 75.0

    def test_sort_sprites_deterministic(self) -> None:
        """Sprites should sort deterministically."""
        sprites = [
            MockSprite("c", center_y=50.0, render_layer=0),
            MockSprite("a", center_y=50.0, render_layer=0),
            MockSprite("b", center_y=50.0, render_layer=0),
        ]
        sorted_sprites = sort_sprites_for_render(sprites)
        ids = [s.mesh_entity_data["id"] for s in sorted_sprites]
        assert ids == ["a", "b", "c"]

    def test_sort_sprites_by_layer_then_y(self) -> None:
        """Sprites should sort by render_layer, then y."""
        sprites = [
            MockSprite("e1", center_y=100.0, render_layer=1),
            MockSprite("e2", center_y=50.0, render_layer=0),
            MockSprite("e3", center_y=75.0, render_layer=0),
        ]
        sorted_sprites = sort_sprites_for_render(sprites, sort_mode="y_sort")
        ids = [s.mesh_entity_data["id"] for s in sorted_sprites]
        # Layer 0 first (e2 at y=50, e3 at y=75), then layer 1 (e1)
        assert ids == ["e2", "e3", "e1"]


# -----------------------------------------------------------------------------
# Test edge cases
# -----------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_list(self) -> None:
        """Empty list should return empty list."""
        assert sort_entities_for_render([]) == []

    def test_missing_id_uses_empty_string(self) -> None:
        """Missing id should use empty string for tie-breaking."""
        entity: dict = {"render_layer": 0, "y": 50.0}
        key = compute_render_sort_key(entity)
        assert key[2] == ""

    def test_invalid_render_layer_uses_default(self) -> None:
        """Invalid render_layer should fall back to 0."""
        entity: dict = {"id": "e1", "render_layer": "invalid"}
        key = compute_render_sort_key(entity)
        assert key[0] == 0

    def test_invalid_depth_z_uses_default(self) -> None:
        """Invalid depth_z should fall back to 0.0."""
        entity: dict = {"id": "e1", "depth_z": "invalid"}
        key = compute_render_sort_key(entity, sort_mode="explicit_z")
        assert key[1] == 0.0

# -----------------------------------------------------------------------------
# Test explicit_z vs y_sort mode differences
# -----------------------------------------------------------------------------


class TestExplicitZVsYSort:
    """Tests verifying explicit_z and y_sort produce different orderings."""

    def test_explicit_z_key_has_four_elements(self) -> None:
        """explicit_z key should be (render_layer, depth_z, y_pos, entity_id)."""
        entity: dict = {"id": "e1", "render_layer": 1, "depth_z": 10.0, "y": 50.0}
        key = compute_render_sort_key(entity, sort_mode="explicit_z")
        assert len(key) == 4
        assert key == (1, 10.0, 50.0, "e1")

    def test_y_sort_key_has_three_elements(self) -> None:
        """y_sort key should be (render_layer, y_pos, entity_id)."""
        entity: dict = {"id": "e1", "render_layer": 1, "y": 50.0}
        key = compute_render_sort_key(entity, sort_mode="y_sort")
        assert len(key) == 3
        assert key == (1, 50.0, "e1")

    def test_entities_swap_only_in_explicit_z(self) -> None:
        """Entities with different depth_z vs y should swap only in explicit_z mode."""
        # e1: lower y but higher depth_z
        # e2: higher y but lower depth_z
        entities = [
            {"id": "e1", "render_layer": 0, "depth_z": 100.0, "y": 10.0},
            {"id": "e2", "render_layer": 0, "depth_z": 10.0, "y": 100.0},
        ]

        y_sorted = sort_entities_for_render(entities, sort_mode="y_sort")
        z_sorted = sort_entities_for_render(entities, sort_mode="explicit_z")

        y_ids = [e["id"] for e in y_sorted]
        z_ids = [e["id"] for e in z_sorted]

        # y_sort: lower y first -> e1 (y=10) before e2 (y=100)
        assert y_ids == ["e1", "e2"]

        # explicit_z: lower depth_z first -> e2 (z=10) before e1 (z=100)
        assert z_ids == ["e2", "e1"]

    def test_explicit_z_uses_y_as_tiebreaker(self) -> None:
        """When depth_z is equal, y_pos should be the tie-breaker."""
        entities = [
            {"id": "e1", "render_layer": 0, "depth_z": 50.0, "y": 100.0},
            {"id": "e2", "render_layer": 0, "depth_z": 50.0, "y": 50.0},
        ]

        z_sorted = sort_entities_for_render(entities, sort_mode="explicit_z")
        z_ids = [e["id"] for e in z_sorted]

        # Same depth_z, so sort by y: e2 (y=50) before e1 (y=100)
        assert z_ids == ["e2", "e1"]

    def test_sprite_explicit_z_has_y_fallback(self) -> None:
        """Sprite explicit_z key should include y as fallback."""
        sprite = MockSprite("e1", center_y=75.0, render_layer=0, depth_z=50.0)
        key = compute_sprite_render_sort_key(sprite, sort_mode="explicit_z")
        assert len(key) == 4
        assert key == (0, 50.0, 75.0, "e1")

    def test_sprites_swap_only_in_explicit_z(self) -> None:
        """Sprites with different depth_z vs y should swap only in explicit_z mode."""
        sprites = [
            MockSprite("e1", center_y=10.0, render_layer=0, depth_z=100.0),
            MockSprite("e2", center_y=100.0, render_layer=0, depth_z=10.0),
        ]

        y_sorted = sort_sprites_for_render(sprites, sort_mode="y_sort")
        z_sorted = sort_sprites_for_render(sprites, sort_mode="explicit_z")

        y_ids = [s.mesh_entity_data["id"] for s in y_sorted]
        z_ids = [s.mesh_entity_data["id"] for s in z_sorted]

        # y_sort: lower y first -> e1 (y=10) before e2 (y=100)
        assert y_ids == ["e1", "e2"]

        # explicit_z: lower depth_z first -> e2 (z=10) before e1 (z=100)
        assert z_ids == ["e2", "e1"]