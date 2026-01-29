"""Contract tests for hd2d_debug_model.py.

Tests cover:
- format_render_key_line: correct format for y_sort and explicit_z modes
- extract_sprite_debug_info: extracting fields from sprites
- format_hd2d_summary: summary line formatting
- format_hd2d_debug_text: full debug text output
- sort_sprite_infos_for_display: deterministic sorting
- compute_hd2d_debug_payload: payload generation
"""

from __future__ import annotations

import pytest

from engine.hd2d_debug_model import (
    compute_hd2d_debug_payload,
    extract_sprite_debug_info,
    format_hd2d_debug_text,
    format_hd2d_summary,
    format_render_key_line,
    sort_sprite_infos_for_display,
)


class MockSprite:
    """Mock sprite for testing."""

    def __init__(
        self,
        entity_id: str = "",
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


class TestFormatRenderKeyLine:
    """Tests for format_render_key_line function."""

    def test_y_sort_mode_format(self) -> None:
        """y_sort mode should show layer, y, and id."""
        line = format_render_key_line(
            entity_id="player",
            render_layer=0,
            y_pos=100.5,
            depth_z=50.0,
            sort_mode="y_sort",
        )
        assert line == "layer=0 y=100.5 id=player"

    def test_explicit_z_mode_format(self) -> None:
        """explicit_z mode should show layer, z, y, and id."""
        line = format_render_key_line(
            entity_id="enemy",
            render_layer=1,
            y_pos=75.0,
            depth_z=25.5,
            sort_mode="explicit_z",
        )
        assert line == "layer=1 z=25.5 y=75.0 id=enemy"

    def test_negative_values(self) -> None:
        """Should handle negative values correctly."""
        line = format_render_key_line(
            entity_id="bg",
            render_layer=-1,
            y_pos=-50.0,
            depth_z=-10.0,
            sort_mode="explicit_z",
        )
        assert line == "layer=-1 z=-10.0 y=-50.0 id=bg"


class TestExtractSpriteDebugInfo:
    """Tests for extract_sprite_debug_info function."""

    def test_extracts_all_fields(self) -> None:
        """Should extract all expected fields from sprite."""
        sprite = MockSprite("npc", center_y=200.0, render_layer=2, depth_z=30.0)
        info = extract_sprite_debug_info(sprite)

        assert info["entity_id"] == "npc"
        assert info["render_layer"] == 2
        assert info["y_pos"] == 200.0
        assert info["depth_z"] == 30.0

    def test_handles_missing_mesh_entity_data(self) -> None:
        """Should use defaults when mesh_entity_data is missing."""

        class BareSprite:
            def __init__(self) -> None:
                self.center_y = 50.0

        sprite = BareSprite()
        info = extract_sprite_debug_info(sprite)

        assert info["entity_id"] == ""
        assert info["render_layer"] == 0
        assert info["y_pos"] == 50.0
        assert info["depth_z"] == 0.0

    def test_handles_invalid_values(self) -> None:
        """Should use defaults for invalid values."""

        class BadSprite:
            def __init__(self) -> None:
                self.center_y = "not_a_number"
                self.mesh_entity_data = {
                    "id": 123,  # Not a string
                    "render_layer": "bad",
                    "depth_z": None,
                }

        sprite = BadSprite()
        info = extract_sprite_debug_info(sprite)

        assert info["entity_id"] == ""
        assert info["render_layer"] == 0
        assert info["depth_z"] == 0.0


class TestFormatHd2dSummary:
    """Tests for format_hd2d_summary function."""

    def test_basic_summary(self) -> None:
        """Should format summary line correctly."""
        summary = format_hd2d_summary("y_sort", 42, 3)
        assert summary == "mode=y_sort sprites=42 planes=3"

    def test_explicit_z_mode(self) -> None:
        """Should show explicit_z mode."""
        summary = format_hd2d_summary("explicit_z", 10, 0)
        assert summary == "mode=explicit_z sprites=10 planes=0"

    def test_zero_values(self) -> None:
        """Should handle zero values."""
        summary = format_hd2d_summary("y_sort", 0, 0)
        assert summary == "mode=y_sort sprites=0 planes=0"


class TestSortSpriteInfosForDisplay:
    """Tests for sort_sprite_infos_for_display function."""

    def test_sorts_by_render_layer_first(self) -> None:
        """Should sort by render_layer as primary key."""
        infos = [
            {"entity_id": "a", "render_layer": 2, "y_pos": 0.0, "depth_z": 0.0},
            {"entity_id": "b", "render_layer": 0, "y_pos": 0.0, "depth_z": 0.0},
            {"entity_id": "c", "render_layer": 1, "y_pos": 0.0, "depth_z": 0.0},
        ]
        sorted_infos = sort_sprite_infos_for_display(infos, "y_sort")
        ids = [i["entity_id"] for i in sorted_infos]
        assert ids == ["b", "c", "a"]

    def test_y_sort_uses_y_pos_secondary(self) -> None:
        """y_sort mode should use y_pos as secondary sort key."""
        infos = [
            {"entity_id": "a", "render_layer": 0, "y_pos": 100.0, "depth_z": 50.0},
            {"entity_id": "b", "render_layer": 0, "y_pos": 50.0, "depth_z": 100.0},
        ]
        sorted_infos = sort_sprite_infos_for_display(infos, "y_sort")
        ids = [i["entity_id"] for i in sorted_infos]
        # Lower y first
        assert ids == ["b", "a"]

    def test_explicit_z_uses_depth_z_secondary(self) -> None:
        """explicit_z mode should use depth_z as secondary sort key."""
        infos = [
            {"entity_id": "a", "render_layer": 0, "y_pos": 50.0, "depth_z": 100.0},
            {"entity_id": "b", "render_layer": 0, "y_pos": 100.0, "depth_z": 50.0},
        ]
        sorted_infos = sort_sprite_infos_for_display(infos, "explicit_z")
        ids = [i["entity_id"] for i in sorted_infos]
        # Lower depth_z first
        assert ids == ["b", "a"]

    def test_deterministic_with_same_values(self) -> None:
        """Should sort deterministically by entity_id as tie-breaker."""
        infos = [
            {"entity_id": "charlie", "render_layer": 0, "y_pos": 50.0, "depth_z": 0.0},
            {"entity_id": "alpha", "render_layer": 0, "y_pos": 50.0, "depth_z": 0.0},
            {"entity_id": "bravo", "render_layer": 0, "y_pos": 50.0, "depth_z": 0.0},
        ]
        sorted_infos = sort_sprite_infos_for_display(infos, "y_sort")
        ids = [i["entity_id"] for i in sorted_infos]
        assert ids == ["alpha", "bravo", "charlie"]

    def test_stability_multiple_calls(self) -> None:
        """Same input should produce same output."""
        infos = [
            {"entity_id": "b", "render_layer": 1, "y_pos": 30.0, "depth_z": 0.0},
            {"entity_id": "a", "render_layer": 0, "y_pos": 50.0, "depth_z": 0.0},
        ]
        result1 = sort_sprite_infos_for_display(infos, "y_sort")
        result2 = sort_sprite_infos_for_display(infos, "y_sort")
        assert [i["entity_id"] for i in result1] == [i["entity_id"] for i in result2]


class TestFormatHd2dDebugText:
    """Tests for format_hd2d_debug_text function."""

    def test_empty_sprites(self) -> None:
        """Should show '(no sprites)' when list is empty."""
        text = format_hd2d_debug_text("y_sort", 0, 0, [])
        assert "(no sprites)" in text

    def test_includes_header_and_summary(self) -> None:
        """Should include header and summary line."""
        infos = [{"entity_id": "e1", "render_layer": 0, "y_pos": 50.0, "depth_z": 0.0}]
        text = format_hd2d_debug_text("y_sort", 1, 2, infos)

        assert "HD-2D Depth Debug" in text
        assert "mode=y_sort sprites=1 planes=2" in text

    def test_respects_max_entries(self) -> None:
        """Should limit entries and show '... +N more'."""
        infos = [
            {"entity_id": f"e{i}", "render_layer": 0, "y_pos": float(i), "depth_z": 0.0}
            for i in range(15)
        ]
        text = format_hd2d_debug_text("y_sort", 15, 0, infos, max_entries=5)

        # Should have 5 entry lines + "... +10 more"
        assert "... +10 more" in text

    def test_shows_render_key_lines(self) -> None:
        """Should include formatted render key lines."""
        infos = [
            {"entity_id": "player", "render_layer": 0, "y_pos": 100.0, "depth_z": 0.0},
        ]
        text = format_hd2d_debug_text("y_sort", 1, 0, infos)
        assert "layer=0 y=100.0 id=player" in text


class TestComputeHd2dDebugPayload:
    """Tests for compute_hd2d_debug_payload function."""

    def test_computes_payload_from_sprites(self) -> None:
        """Should compute payload with sprite infos."""
        sprites = [
            MockSprite("e1", center_y=50.0, render_layer=0),
            MockSprite("e2", center_y=100.0, render_layer=1),
        ]
        payload = compute_hd2d_debug_payload("y_sort", sprites, 3)

        assert payload["sort_mode"] == "y_sort"
        assert payload["sprite_count"] == 2
        assert payload["plane_count"] == 3
        assert len(payload["sprite_infos"]) == 2

    def test_empty_sprites(self) -> None:
        """Should handle empty sprite list."""
        payload = compute_hd2d_debug_payload("explicit_z", [], 0)

        assert payload["sort_mode"] == "explicit_z"
        assert payload["sprite_count"] == 0
        assert payload["sprite_infos"] == []
