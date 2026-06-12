"""Contract tests for background_planes_edit_model.py.

Tests cover:
- list_background_planes: returns sorted by (render_layer, id)
- add_background_plane: deterministic ID generation
- duplicate_background_plane: clones with unique ID
- remove_background_plane: removes exactly one
- update_background_plane: sanitizes fields, rejects ID collision
- move_background_plane: adjusts render_layer deterministically
- tiling mode conversion
"""

from __future__ import annotations

from engine.editor.background_planes_edit_model import (
    add_background_plane,
    compute_tiling_mode,
    duplicate_background_plane,
    get_plane_by_id,
    list_background_planes,
    move_background_plane,
    parse_tiling_mode,
    remove_background_plane,
    update_background_plane,
)


class TestListBackgroundPlanes:
    """Tests for list_background_planes function."""

    def test_empty_payload(self) -> None:
        """Empty payload returns empty list."""
        result = list_background_planes({})
        assert result == []

    def test_missing_key(self) -> None:
        """Missing background_planes key returns empty list."""
        result = list_background_planes({"entities": []})
        assert result == []

    def test_sorted_by_render_layer_then_id(self) -> None:
        """Planes should be sorted by (render_layer, id)."""
        payload = {
            "background_planes": [
                {"id": "b", "asset_path": "bg.png", "render_layer": 1},
                {"id": "a", "asset_path": "bg.png", "render_layer": 0},
                {"id": "c", "asset_path": "bg.png", "render_layer": 0},
            ]
        }
        result = list_background_planes(payload)
        ids = [p.id for p in result]
        # Layer 0 first (a, c alphabetically), then layer 1 (b)
        assert ids == ["a", "c", "b"]

    def test_stability_multiple_calls(self) -> None:
        """Same payload produces same order."""
        payload = {
            "background_planes": [
                {"id": "z", "asset_path": "bg.png", "render_layer": 0},
                {"id": "a", "asset_path": "bg.png", "render_layer": 0},
            ]
        }
        result1 = list_background_planes(payload)
        result2 = list_background_planes(payload)
        assert [p.id for p in result1] == [p.id for p in result2]


class TestAddBackgroundPlane:
    """Tests for add_background_plane function."""

    def test_adds_to_empty_payload(self) -> None:
        """Should create background_planes list if missing."""
        payload: dict = {}
        new_payload, new_id = add_background_plane(payload)

        assert "background_planes" in new_payload
        assert len(new_payload["background_planes"]) == 1
        assert new_id == "plane_001"

    def test_deterministic_id_generation(self) -> None:
        """IDs should be plane_001, plane_002, etc."""
        payload: dict = {"background_planes": []}

        p1, id1 = add_background_plane(payload)
        p2, id2 = add_background_plane(p1)
        p3, id3 = add_background_plane(p2)

        assert id1 == "plane_001"
        assert id2 == "plane_002"
        assert id3 == "plane_003"

    def test_skips_existing_ids(self) -> None:
        """Should skip IDs that already exist."""
        payload = {
            "background_planes": [
                {"id": "plane_001", "asset_path": "bg.png"},
                {"id": "plane_002", "asset_path": "bg.png"},
            ]
        }
        new_payload, new_id = add_background_plane(payload)
        assert new_id == "plane_003"

    def test_applies_template(self) -> None:
        """Should apply template values to new plane."""
        payload: dict = {"background_planes": []}
        template = {"asset_path": "custom.png", "parallax": 0.8}

        new_payload, new_id = add_background_plane(payload, template=template)

        plane = new_payload["background_planes"][0]
        assert plane["asset_path"] == "custom.png"
        assert plane["parallax"] == 0.8

    def test_does_not_mutate_original(self) -> None:
        """Original payload should not be modified."""
        payload = {"background_planes": [{"id": "existing", "asset_path": "bg.png"}]}
        original_len = len(payload["background_planes"])

        add_background_plane(payload)

        assert len(payload["background_planes"]) == original_len


class TestDuplicateBackgroundPlane:
    """Tests for duplicate_background_plane function."""

    def test_duplicates_plane(self) -> None:
        """Should clone plane with new ID."""
        payload = {
            "background_planes": [
                {"id": "original", "asset_path": "bg.png", "parallax": 0.7}
            ]
        }
        new_payload, new_id = duplicate_background_plane(payload, "original")

        assert len(new_payload["background_planes"]) == 2
        assert new_id == "original_copy_001"

        # Check cloned values
        new_plane = new_payload["background_planes"][1]
        assert new_plane["asset_path"] == "bg.png"
        assert new_plane["parallax"] == 0.7

    def test_deterministic_copy_id(self) -> None:
        """Duplicate IDs should be deterministic."""
        payload = {
            "background_planes": [{"id": "test", "asset_path": "bg.png"}]
        }

        p1, id1 = duplicate_background_plane(payload, "test")
        p2, id2 = duplicate_background_plane(p1, "test")

        assert id1 == "test_copy_001"
        assert id2 == "test_copy_002"

    def test_nonexistent_id_returns_empty(self) -> None:
        """Should return empty ID if plane not found."""
        payload = {"background_planes": [{"id": "a", "asset_path": "bg.png"}]}
        new_payload, new_id = duplicate_background_plane(payload, "nonexistent")

        assert new_id == ""
        assert len(new_payload.get("background_planes", [])) == 1


class TestRemoveBackgroundPlane:
    """Tests for remove_background_plane function."""

    def test_removes_plane(self) -> None:
        """Should remove exactly one plane."""
        payload = {
            "background_planes": [
                {"id": "a", "asset_path": "bg.png"},
                {"id": "b", "asset_path": "bg.png"},
                {"id": "c", "asset_path": "bg.png"},
            ]
        }
        new_payload = remove_background_plane(payload, "b")

        ids = [p["id"] for p in new_payload["background_planes"]]
        assert ids == ["a", "c"]

    def test_removes_only_matching(self) -> None:
        """Should only remove plane with matching ID."""
        payload = {
            "background_planes": [
                {"id": "target", "asset_path": "bg.png"},
                {"id": "other", "asset_path": "bg.png"},
            ]
        }
        new_payload = remove_background_plane(payload, "target")

        assert len(new_payload["background_planes"]) == 1
        assert new_payload["background_planes"][0]["id"] == "other"

    def test_nonexistent_id_no_change(self) -> None:
        """Should not change anything if ID not found."""
        payload = {
            "background_planes": [{"id": "a", "asset_path": "bg.png"}]
        }
        new_payload = remove_background_plane(payload, "nonexistent")

        assert len(new_payload["background_planes"]) == 1

    def test_does_not_mutate_original(self) -> None:
        """Original payload should not be modified."""
        payload = {
            "background_planes": [
                {"id": "a", "asset_path": "bg.png"},
                {"id": "b", "asset_path": "bg.png"},
            ]
        }
        original_len = len(payload["background_planes"])

        remove_background_plane(payload, "a")

        assert len(payload["background_planes"]) == original_len


class TestUpdateBackgroundPlane:
    """Tests for update_background_plane function."""

    def test_updates_field(self) -> None:
        """Should update specified field."""
        payload = {
            "background_planes": [
                {"id": "plane", "asset_path": "bg.png", "parallax": 0.5}
            ]
        }
        new_payload = update_background_plane(payload, "plane", {"parallax": 0.8})

        assert new_payload["background_planes"][0]["parallax"] == 0.8

    def test_clamps_alpha(self) -> None:
        """Alpha should be clamped to [0.0, 1.0]."""
        payload = {
            "background_planes": [{"id": "plane", "asset_path": "bg.png"}]
        }

        # Test over 1.0
        p1 = update_background_plane(payload, "plane", {"alpha": 2.5})
        assert p1["background_planes"][0]["alpha"] == 1.0

        # Test under 0.0
        p2 = update_background_plane(payload, "plane", {"alpha": -0.5})
        assert p2["background_planes"][0]["alpha"] == 0.0

    def test_clamps_parallax(self) -> None:
        """Parallax should be clamped to [0.0, 2.0]."""
        payload = {
            "background_planes": [{"id": "plane", "asset_path": "bg.png"}]
        }

        p1 = update_background_plane(payload, "plane", {"parallax": 5.0})
        assert p1["background_planes"][0]["parallax"] == 2.0

        p2 = update_background_plane(payload, "plane", {"parallax": -1.0})
        assert p2["background_planes"][0]["parallax"] == 0.0

    def test_parses_numbers_deterministically(self) -> None:
        """String numbers should be parsed to numeric types."""
        payload = {
            "background_planes": [{"id": "plane", "asset_path": "bg.png"}]
        }
        new_payload = update_background_plane(
            payload, "plane",
            {"parallax": "0.75", "render_layer": "2"}
        )

        assert new_payload["background_planes"][0]["parallax"] == 0.75
        assert new_payload["background_planes"][0]["render_layer"] == 2

    def test_rejects_id_collision(self) -> None:
        """Should reject ID change that would collide."""
        payload = {
            "background_planes": [
                {"id": "a", "asset_path": "bg.png"},
                {"id": "b", "asset_path": "bg.png"},
            ]
        }
        # Try to rename "a" to "b"
        new_payload = update_background_plane(payload, "a", {"id": "b"})

        # Should be unchanged
        ids = [p["id"] for p in new_payload["background_planes"]]
        assert ids == ["a", "b"]

    def test_allows_unique_id_change(self) -> None:
        """Should allow ID change to unused value."""
        payload = {
            "background_planes": [{"id": "old_id", "asset_path": "bg.png"}]
        }
        new_payload = update_background_plane(payload, "old_id", {"id": "new_id"})

        assert new_payload["background_planes"][0]["id"] == "new_id"


class TestMoveBackgroundPlane:
    """Tests for move_background_plane function."""

    def test_move_up_decreases_layer(self) -> None:
        """Move up should decrease render_layer."""
        payload = {
            "background_planes": [
                {"id": "plane", "asset_path": "bg.png", "render_layer": 5}
            ]
        }
        new_payload = move_background_plane(payload, "plane", "up")

        assert new_payload["background_planes"][0]["render_layer"] == 4

    def test_move_down_increases_layer(self) -> None:
        """Move down should increase render_layer."""
        payload = {
            "background_planes": [
                {"id": "plane", "asset_path": "bg.png", "render_layer": 5}
            ]
        }
        new_payload = move_background_plane(payload, "plane", "down")

        assert new_payload["background_planes"][0]["render_layer"] == 6

    def test_preserves_all_planes(self) -> None:
        """Move should never lose planes."""
        payload = {
            "background_planes": [
                {"id": "a", "asset_path": "bg.png", "render_layer": 0},
                {"id": "b", "asset_path": "bg.png", "render_layer": 1},
                {"id": "c", "asset_path": "bg.png", "render_layer": 2},
            ]
        }
        new_payload = move_background_plane(payload, "b", "up")

        assert len(new_payload["background_planes"]) == 3

    def test_deterministic(self) -> None:
        """Same move should produce same result."""
        payload = {
            "background_planes": [
                {"id": "plane", "asset_path": "bg.png", "render_layer": 0}
            ]
        }
        result1 = move_background_plane(payload, "plane", "down")
        result2 = move_background_plane(payload, "plane", "down")

        assert result1["background_planes"][0]["render_layer"] == \
               result2["background_planes"][0]["render_layer"]

    def test_invalid_direction_no_change(self) -> None:
        """Invalid direction should not change anything."""
        payload = {
            "background_planes": [
                {"id": "plane", "asset_path": "bg.png", "render_layer": 5}
            ]
        }
        new_payload = move_background_plane(payload, "plane", "invalid")

        assert new_payload["background_planes"][0]["render_layer"] == 5

    def test_nonexistent_id_no_change(self) -> None:
        """Nonexistent plane ID should not change anything."""
        payload = {
            "background_planes": [
                {"id": "plane", "asset_path": "bg.png", "render_layer": 5}
            ]
        }
        new_payload = move_background_plane(payload, "nonexistent", "up")

        assert new_payload["background_planes"][0]["render_layer"] == 5


class TestTilingMode:
    """Tests for tiling mode conversion functions."""

    def test_compute_tiling_mode(self) -> None:
        """Should compute correct tiling mode strings."""
        assert compute_tiling_mode(False, False) == "off"
        assert compute_tiling_mode(True, False) == "tiled-x"
        assert compute_tiling_mode(False, True) == "tiled-y"
        assert compute_tiling_mode(True, True) == "tiled-xy"

    def test_parse_tiling_mode(self) -> None:
        """Should parse tiling mode strings to flags."""
        assert parse_tiling_mode("off") == (False, False)
        assert parse_tiling_mode("tiled-x") == (True, False)
        assert parse_tiling_mode("tiled-y") == (False, True)
        assert parse_tiling_mode("tiled-xy") == (True, True)

    def test_parse_tiling_mode_case_insensitive(self) -> None:
        """Should handle case variations."""
        assert parse_tiling_mode("TILED-XY") == (True, True)
        assert parse_tiling_mode("Tiled-X") == (True, False)

    def test_parse_tiling_mode_invalid(self) -> None:
        """Unknown mode should return (False, False)."""
        assert parse_tiling_mode("invalid") == (False, False)
        assert parse_tiling_mode("") == (False, False)


class TestGetPlaneById:
    """Tests for get_plane_by_id function."""

    def test_finds_plane(self) -> None:
        """Should find plane by ID."""
        payload = {
            "background_planes": [
                {"id": "target", "asset_path": "bg.png", "parallax": 0.7}
            ]
        }
        plane = get_plane_by_id(payload, "target")

        assert plane is not None
        assert plane.id == "target"
        assert plane.parallax == 0.7

    def test_returns_none_for_missing(self) -> None:
        """Should return None if plane not found."""
        payload = {"background_planes": [{"id": "other", "asset_path": "bg.png"}]}
        plane = get_plane_by_id(payload, "nonexistent")

        assert plane is None

    def test_empty_payload(self) -> None:
        """Should return None for empty payload."""
        plane = get_plane_by_id({}, "any")
        assert plane is None
