"""Contract tests for editor sprite ghosting.

Tests pure ghosting functions without arcade dependency.
Uses stub sprite classes to simulate various sprite configurations.
"""

from __future__ import annotations

import pytest

from engine.editor.editor_sprite_ghosting import (
    GhostSpriteSnapshot,
    compute_ghost_alpha,
    apply_ghosting_to_sprites,
    restore_ghosted_sprites,
)


# -----------------------------------------------------------------------------
# Stub Sprite Classes
# -----------------------------------------------------------------------------


class StubSpriteAlpha:
    """Stub sprite with alpha attribute."""

    def __init__(self, alpha: int = 255, color: tuple = (255, 255, 255)) -> None:
        self.alpha = alpha
        self.color = color


class StubSpriteColorOnly:
    """Stub sprite with color but no alpha attribute."""

    def __init__(self, color: tuple = (200, 100, 50)) -> None:
        self.color = color


class StubSpriteColorWithAlpha:
    """Stub sprite with color tuple that includes alpha."""

    def __init__(self, color: tuple = (200, 100, 50, 255)) -> None:
        self.color = color


class StubSpriteNoVisuals:
    """Stub sprite with no alpha or color attributes."""

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0


# -----------------------------------------------------------------------------
# compute_ghost_alpha
# -----------------------------------------------------------------------------


class TestComputeGhostAlpha:
    """Tests for compute_ghost_alpha function."""

    def test_returns_ghost_alpha_value(self) -> None:
        """Should return the ghost_alpha value."""
        result = compute_ghost_alpha(255, ghost_alpha=90)
        assert result == 90

    def test_clamps_to_zero(self) -> None:
        """Should clamp negative values to 0."""
        result = compute_ghost_alpha(255, ghost_alpha=-10)
        assert result == 0

    def test_clamps_to_255(self) -> None:
        """Should clamp values above 255 to 255."""
        result = compute_ghost_alpha(255, ghost_alpha=300)
        assert result == 255

    def test_default_ghost_alpha(self) -> None:
        """Default ghost_alpha should be 90."""
        result = compute_ghost_alpha(255)
        assert result == 90


# -----------------------------------------------------------------------------
# apply_ghosting_to_sprites
# -----------------------------------------------------------------------------


class TestApplyGhostingToSprites:
    """Tests for apply_ghosting_to_sprites function."""

    def test_dims_sprites_with_alpha(self) -> None:
        """Should dim sprites by setting alpha to ghost_alpha."""
        sprite = StubSpriteAlpha(alpha=255)
        sprites_by_id = {"entity_1": sprite}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_alpha=90,
        )

        assert len(snapshots) == 1
        assert snapshots[0].entity_id == "entity_1"
        assert snapshots[0].old_alpha == 255
        assert sprite.alpha == 90

    def test_dims_sprites_by_color_when_no_alpha(self) -> None:
        """Should scale color when sprite has no alpha attribute."""
        sprite = StubSpriteColorOnly(color=(200, 100, 50))
        sprites_by_id = {"entity_1": sprite}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_color_scale=0.5,
        )

        assert len(snapshots) == 1
        assert snapshots[0].old_color_rgb == (200, 100, 50)
        assert sprite.color == (100, 50, 25)

    def test_preserves_alpha_in_color_tuple(self) -> None:
        """Should preserve alpha channel when scaling RGBA color."""
        sprite = StubSpriteColorWithAlpha(color=(200, 100, 50, 200))
        sprites_by_id = {"entity_1": sprite}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_color_scale=0.5,
        )

        assert len(snapshots) == 1
        assert sprite.color == (100, 50, 25, 200)  # Alpha preserved

    def test_only_ghosts_specified_ids(self) -> None:
        """Should only ghost entities in ghost_entity_ids."""
        sprite_1 = StubSpriteAlpha(alpha=255)
        sprite_2 = StubSpriteAlpha(alpha=255)
        sprites_by_id = {"entity_1": sprite_1, "entity_2": sprite_2}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],  # Only entity_1
            ghost_alpha=90,
        )

        assert len(snapshots) == 1
        assert sprite_1.alpha == 90  # Ghosted
        assert sprite_2.alpha == 255  # Unchanged

    def test_deterministic_ordering(self) -> None:
        """Snapshots should be in sorted entity ID order."""
        sprites_by_id = {
            "z_entity": StubSpriteAlpha(alpha=255),
            "a_entity": StubSpriteAlpha(alpha=255),
            "m_entity": StubSpriteAlpha(alpha=255),
        }

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["z_entity", "a_entity", "m_entity"],
        )

        ids = [s.entity_id for s in snapshots]
        assert ids == ["a_entity", "m_entity", "z_entity"]

    def test_empty_ghost_list_no_changes(self) -> None:
        """Empty ghost list should produce no snapshots or changes."""
        sprite = StubSpriteAlpha(alpha=255)
        sprites_by_id = {"entity_1": sprite}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=[],
        )

        assert snapshots == []
        assert sprite.alpha == 255  # Unchanged

    def test_missing_sprite_ignored(self) -> None:
        """Missing sprites in lookup should be silently ignored."""
        sprites_by_id = {"entity_1": StubSpriteAlpha(alpha=255)}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1", "missing_entity"],
        )

        assert len(snapshots) == 1
        assert snapshots[0].entity_id == "entity_1"

    def test_sprite_without_visuals_ignored(self) -> None:
        """Sprites without alpha or color should be silently ignored."""
        sprite = StubSpriteNoVisuals()
        sprites_by_id = {"entity_1": sprite}

        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
        )

        assert snapshots == []

    def test_color_clamping_low(self) -> None:
        """Color scaling should clamp to minimum of 0."""
        sprite = StubSpriteColorOnly(color=(10, 5, 2))
        sprites_by_id = {"entity_1": sprite}

        apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_color_scale=0.0,
        )

        assert sprite.color[0] >= 0
        assert sprite.color[1] >= 0
        assert sprite.color[2] >= 0

    def test_color_clamping_high(self) -> None:
        """Color scaling should clamp to maximum of 255."""
        sprite = StubSpriteColorOnly(color=(255, 255, 255))
        sprites_by_id = {"entity_1": sprite}

        apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_color_scale=2.0,  # Would exceed 255
        )

        assert sprite.color[0] <= 255
        assert sprite.color[1] <= 255
        assert sprite.color[2] <= 255


# -----------------------------------------------------------------------------
# restore_ghosted_sprites
# -----------------------------------------------------------------------------


class TestRestoreGhostedSprites:
    """Tests for restore_ghosted_sprites function."""

    def test_restores_alpha_to_original(self) -> None:
        """Should restore alpha to original value."""
        sprite = StubSpriteAlpha(alpha=90)  # Currently ghosted
        sprites_by_id = {"entity_1": sprite}
        snapshots = [GhostSpriteSnapshot(
            entity_id="entity_1",
            old_alpha=255,
            old_color_rgb=None,
        )]

        restore_ghosted_sprites(snapshots, sprites_by_id)

        assert sprite.alpha == 255

    def test_restores_color_to_original(self) -> None:
        """Should restore color to original value."""
        sprite = StubSpriteColorOnly(color=(100, 50, 25))  # Currently ghosted
        sprites_by_id = {"entity_1": sprite}
        snapshots = [GhostSpriteSnapshot(
            entity_id="entity_1",
            old_alpha=None,
            old_color_rgb=(200, 100, 50),
        )]

        restore_ghosted_sprites(snapshots, sprites_by_id)

        assert sprite.color == (200, 100, 50)

    def test_preserves_alpha_in_color_on_restore(self) -> None:
        """Should preserve alpha channel when restoring RGBA color."""
        sprite = StubSpriteColorWithAlpha(color=(100, 50, 25, 200))  # Ghosted
        sprites_by_id = {"entity_1": sprite}
        snapshots = [GhostSpriteSnapshot(
            entity_id="entity_1",
            old_alpha=None,
            old_color_rgb=(200, 100, 50),
        )]

        restore_ghosted_sprites(snapshots, sprites_by_id)

        assert sprite.color == (200, 100, 50, 200)  # Alpha preserved

    def test_missing_sprite_on_restore_safe(self) -> None:
        """Missing sprite during restore should not raise."""
        sprites_by_id: dict = {}  # Empty - sprite removed
        snapshots = [GhostSpriteSnapshot(
            entity_id="entity_1",
            old_alpha=255,
            old_color_rgb=None,
        )]

        # Should not raise
        restore_ghosted_sprites(snapshots, sprites_by_id)

    def test_full_apply_restore_cycle(self) -> None:
        """Full cycle: apply ghosting then restore."""
        sprite = StubSpriteAlpha(alpha=255, color=(200, 100, 50))
        sprites_by_id = {"entity_1": sprite}

        # Apply ghosting
        snapshots = apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_alpha=90,
        )

        assert sprite.alpha == 90  # Ghosted

        # Restore
        restore_ghosted_sprites(snapshots, sprites_by_id)

        assert sprite.alpha == 255  # Restored

    def test_empty_snapshots_no_op(self) -> None:
        """Empty snapshots list should be a no-op."""
        sprite = StubSpriteAlpha(alpha=100)
        sprites_by_id = {"entity_1": sprite}

        restore_ghosted_sprites([], sprites_by_id)

        assert sprite.alpha == 100  # Unchanged


# -----------------------------------------------------------------------------
# GhostSpriteSnapshot
# -----------------------------------------------------------------------------


class TestGhostSpriteSnapshot:
    """Tests for GhostSpriteSnapshot dataclass."""

    def test_immutable(self) -> None:
        """Snapshot should be immutable (frozen dataclass)."""
        snapshot = GhostSpriteSnapshot(
            entity_id="test",
            old_alpha=255,
            old_color_rgb=None,
        )

        with pytest.raises(AttributeError):
            snapshot.entity_id = "changed"  # type: ignore

    def test_allows_none_values(self) -> None:
        """Should allow None for both old_alpha and old_color_rgb."""
        snapshot = GhostSpriteSnapshot(
            entity_id="test",
            old_alpha=None,
            old_color_rgb=None,
        )

        assert snapshot.old_alpha is None
        assert snapshot.old_color_rgb is None
