"""Integration tests for HD-2D render ordering.

Tests verify that entities are sorted deterministically even when:
- Entity IDs differ
- Render layers are mixed
- Y positions vary
"""

from __future__ import annotations

import pytest

from engine.render_sort_model import (
    compute_sprite_render_sort_key,
    sort_sprites_for_render,
)


class MockSprite:
    """Mock sprite for integration testing."""

    def __init__(
        self,
        entity_id: str,
        center_x: float = 0.0,
        center_y: float = 0.0,
        render_layer: int = 0,
        depth_z: float = 0.0,
    ) -> None:
        self.center_x = center_x
        self.center_y = center_y
        self.mesh_entity_data = {
            "id": entity_id,
            "render_layer": render_layer,
            "depth_z": depth_z,
            "x": center_x,
            "y": center_y,
        }


class TestHD2DRenderOrderIntegration:
    """Integration tests for HD-2D style render ordering."""

    def test_deterministic_ordering_different_ids(self) -> None:
        """Entities should sort deterministically regardless of ID format."""
        # Create sprites with various ID formats
        sprites = [
            MockSprite("player_1", center_y=100.0),
            MockSprite("npc_vendor", center_y=100.0),
            MockSprite("enemy_slime_01", center_y=100.0),
            MockSprite("prop_barrel", center_y=100.0),
        ]

        # Sort multiple times and verify consistency
        result1 = sort_sprites_for_render(sprites, sort_mode="y_sort")
        result2 = sort_sprites_for_render(sprites, sort_mode="y_sort")

        ids1 = [s.mesh_entity_data["id"] for s in result1]
        ids2 = [s.mesh_entity_data["id"] for s in result2]

        assert ids1 == ids2
        # Should be alphabetically sorted due to same y position
        assert ids1 == ["enemy_slime_01", "npc_vendor", "player_1", "prop_barrel"]

    def test_layer_takes_precedence_over_y(self) -> None:
        """render_layer should take precedence over y-position."""
        sprites = [
            MockSprite("ground_decal", center_y=200.0, render_layer=-1),  # Below
            MockSprite("player", center_y=100.0, render_layer=0),         # Mid
            MockSprite("flying_enemy", center_y=50.0, render_layer=1),    # Above
        ]

        result = sort_sprites_for_render(sprites, sort_mode="y_sort")
        ids = [s.mesh_entity_data["id"] for s in result]

        # Should be sorted by layer first: -1, 0, 1
        assert ids == ["ground_decal", "player", "flying_enemy"]

    def test_y_sort_within_same_layer(self) -> None:
        """Within same layer, lower y should render first (further back)."""
        sprites = [
            MockSprite("e1", center_y=150.0, render_layer=0),  # Front
            MockSprite("e2", center_y=50.0, render_layer=0),   # Back
            MockSprite("e3", center_y=100.0, render_layer=0),  # Middle
        ]

        result = sort_sprites_for_render(sprites, sort_mode="y_sort")
        ids = [s.mesh_entity_data["id"] for s in result]

        # Lower y (back) should come first
        assert ids == ["e2", "e3", "e1"]

    def test_explicit_z_mode(self) -> None:
        """explicit_z mode should use depth_z instead of y."""
        sprites = [
            MockSprite("e1", center_y=50.0, depth_z=100.0, render_layer=0),   # High z
            MockSprite("e2", center_y=150.0, depth_z=10.0, render_layer=0),   # Low z
            MockSprite("e3", center_y=100.0, depth_z=50.0, render_layer=0),   # Mid z
        ]

        result = sort_sprites_for_render(sprites, sort_mode="explicit_z")
        ids = [s.mesh_entity_data["id"] for s in result]

        # Should be sorted by depth_z: 10, 50, 100
        assert ids == ["e2", "e3", "e1"]

    def test_complex_scene_determinism(self) -> None:
        """Complex scene with mixed layers should sort deterministically."""
        sprites = [
            # Background layer (-1)
            MockSprite("bg_tree_1", center_y=200.0, render_layer=-1),
            MockSprite("bg_tree_2", center_y=180.0, render_layer=-1),
            # Entity layer (0)
            MockSprite("player", center_y=100.0, render_layer=0),
            MockSprite("enemy_a", center_y=120.0, render_layer=0),
            MockSprite("enemy_b", center_y=80.0, render_layer=0),
            MockSprite("npc", center_y=100.0, render_layer=0),  # Same y as player
            # Foreground layer (1)
            MockSprite("fg_particle", center_y=90.0, render_layer=1),
        ]

        # Shuffle input order
        import random
        shuffled = sprites.copy()
        random.seed(42)
        random.shuffle(shuffled)

        result = sort_sprites_for_render(shuffled, sort_mode="y_sort")
        ids = [s.mesh_entity_data["id"] for s in result]

        # Expected order:
        # Layer -1: bg_tree_2 (y=180), bg_tree_1 (y=200)
        # Layer 0: enemy_b (y=80), npc (y=100, "npc" < "player"), player (y=100), enemy_a (y=120)
        # Layer 1: fg_particle
        expected = [
            "bg_tree_2", "bg_tree_1",  # Layer -1
            "enemy_b", "npc", "player", "enemy_a",  # Layer 0
            "fg_particle",  # Layer 1
        ]
        assert ids == expected

    def test_missing_entity_data_uses_defaults(self) -> None:
        """Sprites missing mesh_entity_data should use defaults."""

        class BareSprite:
            def __init__(self, center_y: float) -> None:
                self.center_y = center_y
                # No mesh_entity_data

        sprites = [
            BareSprite(100.0),
            BareSprite(50.0),
            BareSprite(75.0),
        ]

        # Should not crash, uses defaults (render_layer=0, empty id)
        result = sort_sprites_for_render(sprites, sort_mode="y_sort")
        # All have same id (""), so sort by y
        ys = [s.center_y for s in result]
        assert ys == [50.0, 75.0, 100.0]


class TestExplicitZModeIntegration:
    """Integration tests for explicit_z mode."""

    def test_explicit_z_overrides_y_position(self) -> None:
        """explicit_z mode should order by depth_z, not y position."""
        # Characters with depth_z opposite to their y positions
        sprites = [
            MockSprite("tall_tree", center_y=200.0, depth_z=0.0, render_layer=0),    # high y, low z
            MockSprite("player", center_y=100.0, depth_z=50.0, render_layer=0),      # mid y, mid z
            MockSprite("ground_decal", center_y=50.0, depth_z=100.0, render_layer=0), # low y, high z
        ]

        # y_sort: should order by y (50, 100, 200)
        y_result = sort_sprites_for_render(sprites, sort_mode="y_sort")
        y_ids = [s.mesh_entity_data["id"] for s in y_result]
        assert y_ids == ["ground_decal", "player", "tall_tree"]

        # explicit_z: should order by depth_z (0, 50, 100)
        z_result = sort_sprites_for_render(sprites, sort_mode="explicit_z")
        z_ids = [s.mesh_entity_data["id"] for s in z_result]
        assert z_ids == ["tall_tree", "player", "ground_decal"]

    def test_explicit_z_falls_back_to_y_then_id(self) -> None:
        """When depth_z is equal, should fall back to y, then id."""
        sprites = [
            MockSprite("b_entity", center_y=100.0, depth_z=50.0, render_layer=0),
            MockSprite("a_entity", center_y=100.0, depth_z=50.0, render_layer=0),
            MockSprite("c_entity", center_y=50.0, depth_z=50.0, render_layer=0),
        ]

        result = sort_sprites_for_render(sprites, sort_mode="explicit_z")
        ids = [s.mesh_entity_data["id"] for s in result]

        # Same depth_z (50), so fall back to y: c_entity (y=50), then a/b (y=100, alphabetically)
        assert ids == ["c_entity", "a_entity", "b_entity"]

    def test_complex_scene_with_explicit_z(self) -> None:
        """Complex scene with explicit_z should be deterministic."""
        import random

        sprites = [
            # Background layer
            MockSprite("bg_sky", center_y=300.0, depth_z=-100.0, render_layer=-1),
            MockSprite("bg_mountains", center_y=250.0, depth_z=-50.0, render_layer=-1),
            # Main layer with various depths
            MockSprite("floor_tile", center_y=100.0, depth_z=0.0, render_layer=0),
            MockSprite("player", center_y=100.0, depth_z=50.0, render_layer=0),
            MockSprite("flying_bird", center_y=200.0, depth_z=100.0, render_layer=0),
            # Foreground
            MockSprite("rain_overlay", center_y=50.0, depth_z=200.0, render_layer=1),
        ]

        # Shuffle and sort multiple times
        shuffled = sprites.copy()
        random.seed(999)
        random.shuffle(shuffled)

        result1 = sort_sprites_for_render(shuffled, sort_mode="explicit_z")
        result2 = sort_sprites_for_render(shuffled, sort_mode="explicit_z")

        ids1 = [s.mesh_entity_data["id"] for s in result1]
        ids2 = [s.mesh_entity_data["id"] for s in result2]

        assert ids1 == ids2
        # Expected: layer -1 (by depth_z: -100, -50), layer 0 (by depth_z: 0, 50, 100), layer 1
        assert ids1 == [
            "bg_sky", "bg_mountains",  # Layer -1
            "floor_tile", "player", "flying_bird",  # Layer 0
            "rain_overlay",  # Layer 1
        ]
