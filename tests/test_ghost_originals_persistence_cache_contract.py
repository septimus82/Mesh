"""Contract tests for ghost originals workspace persistence and caching.

Tests workspace settings round-trip and ghosting cache behavior.
Headless, no arcade dependency.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from engine.editor.editor_sprite_ghosting import (
    apply_ghosting_to_sprites,
    make_ghosting_cache_key,
    should_reapply_ghosting,
)
from engine.workspace_settings import (
    WorkspaceSettings,
    load_workspace,
    save_workspace,
)

# -----------------------------------------------------------------------------
# Stub Sprite Classes with Write Counters
# -----------------------------------------------------------------------------


class StubSpriteWithWriteCounter:
    """Stub sprite that counts attribute writes for cache testing."""

    def __init__(self, alpha: int = 255) -> None:
        self._alpha = alpha
        self.alpha_write_count = 0

    @property
    def alpha(self) -> int:
        return self._alpha

    @alpha.setter
    def alpha(self, value: int) -> None:
        self._alpha = value
        self.alpha_write_count += 1


# -----------------------------------------------------------------------------
# Workspace Settings Persistence
# -----------------------------------------------------------------------------


class TestGhostOriginalsWorkspacePersistence:
    """Tests for ghost originals settings workspace persistence."""

    def test_defaults(self) -> None:
        """Default ghost settings should be enabled, alpha=90, scale=0.65."""
        settings = WorkspaceSettings()
        assert settings.ghost_originals_enabled is True
        assert settings.ghost_originals_alpha == 90
        assert settings.ghost_originals_dim_scale == 0.65

    def test_from_dict_defaults(self) -> None:
        """from_dict should use defaults for missing fields."""
        settings = WorkspaceSettings.from_dict({})
        assert settings.ghost_originals_enabled is True
        assert settings.ghost_originals_alpha == 90
        assert settings.ghost_originals_dim_scale == 0.65

    def test_from_dict_custom_values(self) -> None:
        """from_dict should load custom ghost settings."""
        settings = WorkspaceSettings.from_dict({
            "ghost_originals_enabled": False,
            "ghost_originals_alpha": 120,
            "ghost_originals_dim_scale": 0.5,
        })
        assert settings.ghost_originals_enabled is False
        assert settings.ghost_originals_alpha == 120
        assert settings.ghost_originals_dim_scale == 0.5

    def test_alpha_clamped_to_0_255(self) -> None:
        """Alpha should be clamped to [0, 255]."""
        # Over max
        settings = WorkspaceSettings.from_dict({"ghost_originals_alpha": 500})
        assert settings.ghost_originals_alpha == 255

        # Below min
        settings = WorkspaceSettings.from_dict({"ghost_originals_alpha": -50})
        assert settings.ghost_originals_alpha == 0

    def test_dim_scale_clamped_to_0_1(self) -> None:
        """Dim scale should be clamped to [0.0, 1.0]."""
        # Over max
        settings = WorkspaceSettings.from_dict({"ghost_originals_dim_scale": 2.5})
        assert settings.ghost_originals_dim_scale == 1.0

        # Below min
        settings = WorkspaceSettings.from_dict({"ghost_originals_dim_scale": -0.5})
        assert settings.ghost_originals_dim_scale == 0.0

    def test_save_load_roundtrip(self) -> None:
        """Workspace save/load should roundtrip ghost settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)

            # Create settings with custom ghost values
            original = WorkspaceSettings(
                ghost_originals_enabled=False,
                ghost_originals_alpha=75,
                ghost_originals_dim_scale=0.4,
            )

            # Save and load
            save_workspace(repo_root, original)
            loaded = load_workspace(repo_root)

            # Verify roundtrip
            assert loaded.ghost_originals_enabled == original.ghost_originals_enabled
            assert loaded.ghost_originals_alpha == original.ghost_originals_alpha
            assert loaded.ghost_originals_dim_scale == original.ghost_originals_dim_scale

    def test_json_contains_ghost_fields(self) -> None:
        """Saved JSON should contain ghost settings fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            settings = WorkspaceSettings(
                ghost_originals_enabled=True,
                ghost_originals_alpha=100,
                ghost_originals_dim_scale=0.8,
            )

            save_workspace(repo_root, settings)

            # Read raw JSON and verify fields
            json_path = repo_root / "workspace.json"
            data = json.loads(json_path.read_text(encoding="utf-8"))

            assert "ghost_originals_enabled" in data
            assert "ghost_originals_alpha" in data
            assert "ghost_originals_dim_scale" in data
            assert data["ghost_originals_enabled"] is True
            assert data["ghost_originals_alpha"] == 100
            assert data["ghost_originals_dim_scale"] == 0.8


# -----------------------------------------------------------------------------
# Ghosting Cache Behavior
# -----------------------------------------------------------------------------


class TestGhostingCacheKey:
    """Tests for ghosting cache key creation."""

    def test_make_cache_key_creates_frozenset(self) -> None:
        """make_ghosting_cache_key should create frozenset of IDs."""
        state = make_ghosting_cache_key(
            ghost_ids=["entity_b", "entity_a"],
            alpha=90,
            dim_scale=0.65,
            enabled=True,
            alt_dup_active=True,
        )

        assert state.ghosted_ids_key == frozenset(["entity_a", "entity_b"])
        assert state.alpha == 90
        assert state.dim_scale == 0.65
        assert state.enabled is True
        assert state.alt_dup_active is True

    def test_empty_ghost_ids(self) -> None:
        """Empty ghost IDs should create empty frozenset."""
        state = make_ghosting_cache_key(
            ghost_ids=[],
            alpha=90,
            dim_scale=0.65,
            enabled=True,
            alt_dup_active=True,
        )

        assert state.ghosted_ids_key == frozenset()


class TestShouldReapplyGhosting:
    """Tests for should_reapply_ghosting function."""

    def test_none_previous_returns_true(self) -> None:
        """Should reapply if previous state is None."""
        current = make_ghosting_cache_key(["a"], 90, 0.65, True, True)
        assert should_reapply_ghosting(current, None) is True

    def test_none_current_returns_true(self) -> None:
        """Should reapply if current state is None."""
        previous = make_ghosting_cache_key(["a"], 90, 0.65, True, True)
        assert should_reapply_ghosting(None, previous) is True

    def test_same_state_returns_false(self) -> None:
        """Same state should not require reapply."""
        state1 = make_ghosting_cache_key(["a", "b"], 90, 0.65, True, True)
        state2 = make_ghosting_cache_key(["b", "a"], 90, 0.65, True, True)  # Order doesn't matter
        assert should_reapply_ghosting(state1, state2) is False

    def test_different_ids_returns_true(self) -> None:
        """Different ghost IDs should require reapply."""
        state1 = make_ghosting_cache_key(["a", "b"], 90, 0.65, True, True)
        state2 = make_ghosting_cache_key(["a", "c"], 90, 0.65, True, True)
        assert should_reapply_ghosting(state1, state2) is True

    def test_different_alpha_returns_true(self) -> None:
        """Different alpha should require reapply."""
        state1 = make_ghosting_cache_key(["a"], 90, 0.65, True, True)
        state2 = make_ghosting_cache_key(["a"], 100, 0.65, True, True)
        assert should_reapply_ghosting(state1, state2) is True

    def test_different_dim_scale_returns_true(self) -> None:
        """Different dim scale should require reapply."""
        state1 = make_ghosting_cache_key(["a"], 90, 0.65, True, True)
        state2 = make_ghosting_cache_key(["a"], 90, 0.5, True, True)
        assert should_reapply_ghosting(state1, state2) is True

    def test_different_enabled_returns_true(self) -> None:
        """Different enabled flag should require reapply."""
        state1 = make_ghosting_cache_key(["a"], 90, 0.65, True, True)
        state2 = make_ghosting_cache_key(["a"], 90, 0.65, False, True)
        assert should_reapply_ghosting(state1, state2) is True

    def test_different_alt_dup_active_returns_true(self) -> None:
        """Different alt_dup_active flag should require reapply."""
        state1 = make_ghosting_cache_key(["a"], 90, 0.65, True, True)
        state2 = make_ghosting_cache_key(["a"], 90, 0.65, True, False)
        assert should_reapply_ghosting(state1, state2) is True


class TestGhostingCacheWriteCounter:
    """Tests that caching avoids redundant sprite attribute writes."""

    def test_apply_writes_once(self) -> None:
        """First apply should write alpha once."""
        sprite = StubSpriteWithWriteCounter(alpha=255)
        sprites_by_id = {"entity_1": sprite}

        apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_alpha=90,
        )

        assert sprite.alpha_write_count == 1
        assert sprite.alpha == 90

    def test_repeated_apply_writes_again(self) -> None:
        """Without caching, repeated apply would write multiple times."""
        sprite = StubSpriteWithWriteCounter(alpha=255)
        sprites_by_id = {"entity_1": sprite}

        # First apply
        apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_alpha=90,
        )
        assert sprite.alpha_write_count == 1

        # Second apply (would normally be avoided by tick.py caching)
        apply_ghosting_to_sprites(
            sprites_by_entity_id=sprites_by_id,
            ghost_entity_ids=["entity_1"],
            ghost_alpha=90,
        )
        # Note: Without tick.py caching, this would write again
        assert sprite.alpha_write_count == 2

    def test_cache_key_stability(self) -> None:
        """Same inputs should produce equal cache keys."""
        key1 = make_ghosting_cache_key(["x", "y", "z"], 90, 0.65, True, True)
        key2 = make_ghosting_cache_key(["z", "y", "x"], 90, 0.65, True, True)

        # Both should match because frozenset order doesn't matter
        assert key1.ghosted_ids_key == key2.ghosted_ids_key
        assert should_reapply_ghosting(key1, key2) is False
