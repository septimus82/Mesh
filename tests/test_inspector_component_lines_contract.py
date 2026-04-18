"""Contract tests for inspector component lines builder.

Tests cover:
- Ordering stable and lines contain expected headers/fields
- Add-row present
- Removing a component removes its section deterministically
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from engine.editor.components_model import (
    build_components,
    add_component,
    remove_component,
    InspectorComponent,
)
from engine.editor.entity_panels import (
    build_component_inspector_lines,
    get_component_inspector_row_count,
    resolve_component_inspector_selection,
)


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def minimal_entity() -> Dict[str, Any]:
    """Minimal entity with just transform."""
    return {
        "id": "test_entity",
        "x": 100.0,
        "y": 200.0,
        "rotation": 45.0,
    }


@pytest.fixture
def full_entity() -> Dict[str, Any]:
    """Entity with all component types."""
    return {
        "id": "full_entity",
        "components": {
            "transform": {"x": 50.0, "y": 60.0, "rot": 90.0},
            "sprite": {"asset": "player.png"},
            "light": {
                "radius_px": 200.0,
                "color_rgba": [255, 128, 0, 255],
                "flicker_enabled": True,
                "flicker_amount": 0.5,
                "flicker_speed": 1.0,
                "cookie_id": None,
                "cookie_scale": 1.0,
                "cookie_rotation_deg": 0.0,
            },
            "collider": {"kind": "rect", "w": 16, "h": 16},
        },
    }


# -----------------------------------------------------------------------------
# Test Line Building
# -----------------------------------------------------------------------------

class TestBuildComponentInspectorLines:
    """Test build_component_inspector_lines function."""

    def test_minimal_entity_has_transform_header(self, minimal_entity: Dict[str, Any]):
        """Minimal entity should have Transform header."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        # Should have at least the Transform header
        assert any("[Transform]" in line for line in lines)

    def test_minimal_entity_has_transform_fields(self, minimal_entity: Dict[str, Any]):
        """Minimal entity should have Transform fields."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        # Should have X, Y, Rotation fields
        assert any("X:" in line for line in lines)
        assert any("Y:" in line for line in lines)
        assert any("Rotation:" in line for line in lines)

    def test_full_entity_has_all_headers(self, full_entity: Dict[str, Any]):
        """Full entity should have all component headers."""
        components = build_components(full_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        assert any("[Transform]" in line for line in lines)
        assert any("[SpriteRenderer]" in line for line in lines)
        assert any("[LightSource]" in line for line in lines)
        assert any("[Collider]" in line for line in lines)

    def test_add_row_present(self, minimal_entity: Dict[str, Any]):
        """Add component row should be present."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0, show_add_row=True)
        
        assert any("[+ Add Component]" in line for line in lines)

    def test_add_row_can_be_hidden(self, minimal_entity: Dict[str, Any]):
        """Add component row can be hidden."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0, show_add_row=False)
        
        assert not any("[+ Add Component]" in line for line in lines)

    def test_selection_marker(self, minimal_entity: Dict[str, Any]):
        """Selected row should have > prefix."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        # First line (Transform header) should be selected
        assert lines[0].startswith("> ")

    def test_non_selected_rows_have_space_prefix(self, minimal_entity: Dict[str, Any]):
        """Non-selected rows should have space prefix."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        # Second line (first field) should not be selected
        if len(lines) > 1:
            assert lines[1].startswith("  ")

    def test_removable_marker_on_header(self, full_entity: Dict[str, Any]):
        """Removable components should have [-] marker."""
        components = build_components(full_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        # Sprite/Light/Collider are removable
        sprite_line = next(line for line in lines if "[SpriteRenderer]" in line)
        assert "[-]" in sprite_line

    def test_transform_not_removable_marker(self, full_entity: Dict[str, Any]):
        """Transform should not have [-] marker."""
        components = build_components(full_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        transform_line = next(line for line in lines if "[Transform]" in line)
        assert "[-]" not in transform_line

    def test_text_edit_mode_shows_buffer(self, minimal_entity: Dict[str, Any]):
        """Text edit mode should show buffer with cursor."""
        components = build_components(minimal_entity)
        edit_state = {"active": True, "buffer": "123"}
        lines = build_component_inspector_lines(components, selection_index=1, edit_state=edit_state)
        
        # First field (X) should show buffer with cursor
        x_line = next(line for line in lines if "X:" in line)
        assert "123_" in x_line


# -----------------------------------------------------------------------------
# Test Line Ordering
# -----------------------------------------------------------------------------

class TestLineOrdering:
    """Test that line ordering is stable and correct."""

    def test_header_before_fields(self, full_entity: Dict[str, Any]):
        """Each component header should come before its fields."""
        components = build_components(full_entity)
        lines = build_component_inspector_lines(components, selection_index=0, show_add_row=False)
        
        # Find Transform header and X field indices
        transform_idx = next(i for i, line in enumerate(lines) if "[Transform]" in line)
        x_idx = next(i for i, line in enumerate(lines) if "X:" in line)
        
        assert transform_idx < x_idx

    def test_component_order_matches_spec(self, full_entity: Dict[str, Any]):
        """Components should be in order: Transform, Sprite, Light, Collider."""
        components = build_components(full_entity)
        lines = build_component_inspector_lines(components, selection_index=0, show_add_row=False)
        
        transform_idx = next(i for i, line in enumerate(lines) if "[Transform]" in line)
        sprite_idx = next(i for i, line in enumerate(lines) if "[SpriteRenderer]" in line)
        light_idx = next(i for i, line in enumerate(lines) if "[LightSource]" in line)
        collider_idx = next(i for i, line in enumerate(lines) if "[Collider]" in line)
        
        assert transform_idx < sprite_idx < light_idx < collider_idx

    def test_add_row_is_last(self, minimal_entity: Dict[str, Any]):
        """Add component row should be last."""
        components = build_components(minimal_entity)
        lines = build_component_inspector_lines(components, selection_index=0, show_add_row=True)
        
        assert "[+ Add Component]" in lines[-1]


# -----------------------------------------------------------------------------
# Test Row Count
# -----------------------------------------------------------------------------

class TestRowCount:
    """Test get_component_inspector_row_count function."""

    def test_minimal_entity_row_count(self, minimal_entity: Dict[str, Any]):
        """Minimal entity should have Transform header + 3 fields + add row."""
        components = build_components(minimal_entity)
        count = get_component_inspector_row_count(components, include_add_row=True)
        
        # 1 header + 3 fields (X, Y, Rotation) + 1 add row = 5
        assert count == 5

    def test_row_count_without_add_row(self, minimal_entity: Dict[str, Any]):
        """Row count without add row should be smaller."""
        components = build_components(minimal_entity)
        count_with = get_component_inspector_row_count(components, include_add_row=True)
        count_without = get_component_inspector_row_count(components, include_add_row=False)
        
        assert count_without == count_with - 1

    def test_full_entity_row_count(self, full_entity: Dict[str, Any]):
        """Full entity should have correct row count."""
        components = build_components(full_entity)
        count = get_component_inspector_row_count(components, include_add_row=False)
        
        # Transform: 1 header + 3 fields = 4
        # Sprite: 1 header + 1 field = 2
        # Light: 1 header + 8 fields = 9
        # Collider (rect): 1 header + 3 fields = 4
        # Total = 19
        assert count == 19


# -----------------------------------------------------------------------------
# Test Selection Resolution
# -----------------------------------------------------------------------------

class TestResolveComponentInspectorSelection:
    """Test resolve_component_inspector_selection function."""

    def test_index_0_is_transform_header(self, minimal_entity: Dict[str, Any]):
        """Index 0 should be Transform header."""
        components = build_components(minimal_entity)
        selection = resolve_component_inspector_selection(components, 0)
        
        assert selection is not None
        assert selection["type"] == "header"
        assert selection["component_kind"] == "transform"

    def test_index_1_is_x_field(self, minimal_entity: Dict[str, Any]):
        """Index 1 should be X field."""
        components = build_components(minimal_entity)
        selection = resolve_component_inspector_selection(components, 1)
        
        assert selection is not None
        assert selection["type"] == "field"
        assert selection["component_kind"] == "transform"
        assert selection["field_key"] == "x"

    def test_add_row_index(self, minimal_entity: Dict[str, Any]):
        """Last index should be add row."""
        components = build_components(minimal_entity)
        count = get_component_inspector_row_count(components, include_add_row=True)
        selection = resolve_component_inspector_selection(components, count - 1)
        
        assert selection is not None
        assert selection["type"] == "add_row"

    def test_out_of_bounds_returns_none(self, minimal_entity: Dict[str, Any]):
        """Out of bounds index should return None."""
        components = build_components(minimal_entity)
        count = get_component_inspector_row_count(components, include_add_row=True)
        selection = resolve_component_inspector_selection(components, count + 10)
        
        assert selection is None

    def test_field_selection_has_field_object(self, minimal_entity: Dict[str, Any]):
        """Field selection should include the InspectorField object."""
        components = build_components(minimal_entity)
        selection = resolve_component_inspector_selection(components, 1)
        
        assert "field" in selection
        assert selection["field"].key == "x"
        assert selection["field"].kind == "float"


# -----------------------------------------------------------------------------
# Test Removing Component Updates Lines
# -----------------------------------------------------------------------------

class TestRemoveComponentUpdateLines:
    """Test that removing a component removes its section from lines."""

    def test_remove_light_removes_section(self, full_entity: Dict[str, Any]):
        """Removing light component removes its section."""
        # Before removal
        components_before = build_components(full_entity)
        lines_before = build_component_inspector_lines(components_before, selection_index=0)
        assert any("[LightSource]" in line for line in lines_before)
        
        # Remove light
        updated_entity = remove_component(full_entity, "light")
        components_after = build_components(updated_entity)
        lines_after = build_component_inspector_lines(components_after, selection_index=0)
        
        # Light section should be gone
        assert not any("[LightSource]" in line for line in lines_after)
        # But others should remain
        assert any("[Transform]" in line for line in lines_after)
        assert any("[SpriteRenderer]" in line for line in lines_after)
        assert any("[Collider]" in line for line in lines_after)

    def test_remove_sprite_removes_section(self, full_entity: Dict[str, Any]):
        """Removing sprite component removes its section."""
        updated_entity = remove_component(full_entity, "sprite")
        components = build_components(updated_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        assert not any("[SpriteRenderer]" in line for line in lines)

    def test_row_count_decreases_after_removal(self, full_entity: Dict[str, Any]):
        """Row count should decrease after removing component."""
        components_before = build_components(full_entity)
        count_before = get_component_inspector_row_count(components_before)
        
        updated_entity = remove_component(full_entity, "light")
        components_after = build_components(updated_entity)
        count_after = get_component_inspector_row_count(components_after)
        
        assert count_after < count_before


# -----------------------------------------------------------------------------
# Test Adding Component Updates Lines
# -----------------------------------------------------------------------------

class TestAddComponentUpdateLines:
    """Test that adding a component adds its section to lines."""

    def test_add_light_adds_section(self, minimal_entity: Dict[str, Any]):
        """Adding light component adds its section."""
        # Before addition
        components_before = build_components(minimal_entity)
        lines_before = build_component_inspector_lines(components_before, selection_index=0)
        assert not any("[LightSource]" in line for line in lines_before)
        
        # Add light
        updated_entity = add_component(minimal_entity, "light")
        components_after = build_components(updated_entity)
        lines_after = build_component_inspector_lines(components_after, selection_index=0)
        
        assert any("[LightSource]" in line for line in lines_after)

    def test_add_collider_adds_section(self, minimal_entity: Dict[str, Any]):
        """Adding collider component adds its section."""
        updated_entity = add_component(minimal_entity, "collider")
        components = build_components(updated_entity)
        lines = build_component_inspector_lines(components, selection_index=0)
        
        assert any("[Collider]" in line for line in lines)


# -----------------------------------------------------------------------------
# Test Determinism
# -----------------------------------------------------------------------------

class TestDeterminism:
    """Test that output is deterministic."""

    def test_same_input_same_output(self, full_entity: Dict[str, Any]):
        """Same input should produce same output."""
        components = build_components(full_entity)
        
        lines1 = build_component_inspector_lines(components, selection_index=5)
        lines2 = build_component_inspector_lines(components, selection_index=5)
        
        assert lines1 == lines2

    def test_multiple_builds_same_order(self, full_entity: Dict[str, Any]):
        """Multiple builds should have same component order."""
        for _ in range(5):
            components = build_components(full_entity)
            kinds = [c.kind for c in components]
            assert kinds == ["transform", "sprite", "light", "collider"]
