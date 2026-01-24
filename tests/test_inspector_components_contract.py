"""Contract tests for Component Inspector v1.

Tests cover:
- Deterministic section construction for sample entities
- Collapsing hides rows
- Cursor clamping stays valid
- Numeric edits adjust correctly
- String edit commit modifies entity JSON
- Toggle section doesn't mark dirty (pure function)
"""

from __future__ import annotations

import pytest
from typing import Any, Dict

from engine.editor.inspector_components_model import (
    COMPONENT_SECTIONS,
    NUMERIC_STEP_NORMAL,
    NUMERIC_STEP_SHIFT,
    ComponentRow,
    ComponentSection,
    InspectorCursor,
    apply_inspector_edit,
    build_inspector_sections,
    clamp_inspector_cursor,
    format_field_value,
    get_cursor_row,
    move_cursor,
    toggle_section,
)


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def minimal_entity() -> Dict[str, Any]:
    """Minimal entity with just transform fields."""
    return {
        "id": "test_entity",
        "mesh_name": "TestEntity",
        "x": 100.0,
        "y": 200.0,
        "rotation": 45.0,
        "scale": 1.5,
    }


@pytest.fixture
def full_entity() -> Dict[str, Any]:
    """Entity with all component types."""
    return {
        "id": "full_entity",
        "mesh_name": "FullEntity",
        "x": 100.0,
        "y": 200.0,
        "rotation": 0.0,
        "scale": 1.0,
        "sprite": "assets/sprites/player.png",
        "layer": "entities",
        "interact_label": "Talk",
        "solid": True,
        "tags": ["npc", "friendly"],
        "dialogue": {
            "speaker": "NPC Name",
        },
        "behaviours": ["LightSource"],
        "behaviour_config": {
            "LightSource": {
                "radius": 256.0,
                "color": "#ffcc00",
                "enabled": True,
                "offset_x": 0.0,
                "offset_y": 16.0,
            }
        },
    }


@pytest.fixture
def light_only_entity() -> Dict[str, Any]:
    """Entity with only LightSource behaviour."""
    return {
        "id": "light_entity",
        "x": 50.0,
        "y": 50.0,
        "behaviours": ["LightSource"],
        "behaviour_config": {
            "LightSource": {
                "radius": 128.0,
                "color": "#ffffff",
            }
        },
    }


# -----------------------------------------------------------------------------
# Test Constants
# -----------------------------------------------------------------------------

class TestInspectorConstants:
    """Test inspector constants are correct."""

    def test_component_sections_defined(self):
        """COMPONENT_SECTIONS should have expected entries."""
        section_ids = [s[0] for s in COMPONENT_SECTIONS]
        assert "transform" in section_ids
        assert "render" in section_ids
        assert "interaction" in section_ids
        assert "dialogue" in section_ids
        assert "light_source" in section_ids

    def test_numeric_step_values(self):
        """Numeric step constants should be correct."""
        assert NUMERIC_STEP_NORMAL == 1.0
        assert NUMERIC_STEP_SHIFT == 10.0


# -----------------------------------------------------------------------------
# Test ComponentRow
# -----------------------------------------------------------------------------

class TestComponentRow:
    """Test ComponentRow dataclass."""

    def test_header_row_factory(self):
        """ComponentRow.header creates a header row."""
        row = ComponentRow.header("transform", "Transform")
        assert row.kind == "header"
        assert row.key == "transform"
        assert row.label == "Transform"
        assert row.value is None
        assert row.editable is False
        assert row.field_kind == "header"

    def test_field_row_factory(self):
        """ComponentRow.field creates a field row."""
        row = ComponentRow.field("x", "X", 100.0, "float", editable=True)
        assert row.kind == "field"
        assert row.key == "x"
        assert row.label == "X"
        assert row.value == 100.0
        assert row.editable is True
        assert row.field_kind == "float"

    def test_row_is_frozen(self):
        """ComponentRow should be immutable."""
        row = ComponentRow.field("x", "X", 100.0, "float")
        with pytest.raises(AttributeError):
            row.value = 200.0  # type: ignore[misc]


# -----------------------------------------------------------------------------
# Test ComponentSection
# -----------------------------------------------------------------------------

class TestComponentSection:
    """Test ComponentSection dataclass."""

    def test_expanded_shows_all_rows(self):
        """Expanded section shows all rows."""
        rows = (
            ComponentRow.header("transform", "Transform"),
            ComponentRow.field("x", "X", 100.0, "float"),
            ComponentRow.field("y", "Y", 200.0, "float"),
        )
        section = ComponentSection(id="transform", title="Transform", expanded=True, rows=rows)

        visible = section.visible_rows
        assert len(visible) == 3

    def test_collapsed_shows_only_header(self):
        """Collapsed section shows only header row."""
        rows = (
            ComponentRow.header("transform", "Transform"),
            ComponentRow.field("x", "X", 100.0, "float"),
            ComponentRow.field("y", "Y", 200.0, "float"),
        )
        section = ComponentSection(id="transform", title="Transform", expanded=False, rows=rows)

        visible = section.visible_rows
        assert len(visible) == 1
        assert visible[0].kind == "header"

    def test_header_row_property(self):
        """header_row property returns header."""
        rows = (
            ComponentRow.header("transform", "Transform"),
            ComponentRow.field("x", "X", 100.0, "float"),
        )
        section = ComponentSection(id="transform", title="Transform", expanded=True, rows=rows)

        header = section.header_row
        assert header is not None
        assert header.kind == "header"
        assert header.key == "transform"


# -----------------------------------------------------------------------------
# Test InspectorCursor
# -----------------------------------------------------------------------------

class TestInspectorCursor:
    """Test InspectorCursor dataclass."""

    def test_default_cursor(self):
        """Default cursor starts at transform section."""
        cursor = InspectorCursor.default()
        assert cursor.section_id == "transform"
        assert cursor.row_index == 0

    def test_cursor_is_frozen(self):
        """InspectorCursor should be immutable."""
        cursor = InspectorCursor(section_id="transform", row_index=1)
        with pytest.raises(AttributeError):
            cursor.row_index = 2  # type: ignore[misc]


# -----------------------------------------------------------------------------
# Test build_inspector_sections
# -----------------------------------------------------------------------------

class TestBuildInspectorSections:
    """Test build_inspector_sections function."""

    def test_minimal_entity_has_transform_only(self, minimal_entity):
        """Minimal entity should only have Transform section."""
        sections = build_inspector_sections(minimal_entity)

        # Should have exactly Transform
        section_ids = [s.id for s in sections]
        assert section_ids == ["transform"]

    def test_full_entity_has_all_sections(self, full_entity):
        """Full entity should have all applicable sections."""
        sections = build_inspector_sections(full_entity)

        section_ids = [s.id for s in sections]
        assert "transform" in section_ids
        assert "render" in section_ids
        assert "interaction" in section_ids
        assert "dialogue" in section_ids
        assert "light_source" in section_ids

    def test_sections_default_expanded(self, minimal_entity):
        """Sections should be expanded by default."""
        sections = build_inspector_sections(minimal_entity)

        for section in sections:
            assert section.expanded is True

    def test_expanded_state_respected(self, minimal_entity):
        """Expanded state dict should control collapse."""
        expanded_state = {"transform": False}
        sections = build_inspector_sections(minimal_entity, expanded_state=expanded_state)

        assert len(sections) == 1
        assert sections[0].expanded is False

    def test_transform_section_has_expected_fields(self, minimal_entity):
        """Transform section should have x, y, rotation, scale fields."""
        sections = build_inspector_sections(minimal_entity)
        transform = sections[0]

        field_keys = [r.key for r in transform.rows if r.kind == "field"]
        assert "x" in field_keys
        assert "y" in field_keys
        assert "rotation" in field_keys
        assert "scale" in field_keys

    def test_transform_field_values_correct(self, minimal_entity):
        """Transform fields should have correct values from entity."""
        sections = build_inspector_sections(minimal_entity)
        transform = sections[0]

        # Find x field
        x_row = next((r for r in transform.rows if r.key == "x"), None)
        assert x_row is not None
        assert x_row.value == 100.0

        # Find y field
        y_row = next((r for r in transform.rows if r.key == "y"), None)
        assert y_row is not None
        assert y_row.value == 200.0

    def test_light_source_fields_from_behaviour_config(self, light_only_entity):
        """LightSource fields should be read from behaviour_config."""
        sections = build_inspector_sections(light_only_entity)

        light_section = next((s for s in sections if s.id == "light_source"), None)
        assert light_section is not None

        radius_row = next((r for r in light_section.rows if r.key == "behaviour_config.LightSource.radius"), None)
        assert radius_row is not None
        assert radius_row.value == 128.0

    def test_deterministic_output(self, full_entity):
        """Same input should produce identical output."""
        sections1 = build_inspector_sections(full_entity)
        sections2 = build_inspector_sections(full_entity)

        assert len(sections1) == len(sections2)
        for s1, s2 in zip(sections1, sections2):
            assert s1.id == s2.id
            assert s1.expanded == s2.expanded
            assert len(s1.rows) == len(s2.rows)


# -----------------------------------------------------------------------------
# Test toggle_section
# -----------------------------------------------------------------------------

class TestToggleSection:
    """Test toggle_section function."""

    def test_toggle_expands_collapsed(self):
        """Toggle should expand a collapsed section."""
        state = {"transform": False}
        new_state = toggle_section(state, "transform")

        assert new_state["transform"] is True

    def test_toggle_collapses_expanded(self):
        """Toggle should collapse an expanded section."""
        state = {"transform": True}
        new_state = toggle_section(state, "transform")

        assert new_state["transform"] is False

    def test_toggle_defaults_to_expanded(self):
        """Toggle on missing key assumes expanded (True), so toggles to False."""
        state = {}
        new_state = toggle_section(state, "render")

        assert new_state["render"] is False

    def test_toggle_does_not_mutate_input(self):
        """Toggle should not mutate the input state dict."""
        state = {"transform": True}
        _ = toggle_section(state, "transform")

        # Original should be unchanged
        assert state["transform"] is True

    def test_toggle_is_pure(self):
        """Toggle is a pure function - same input, same output."""
        state = {"transform": True}
        result1 = toggle_section(state, "transform")
        result2 = toggle_section(state, "transform")

        assert result1 == result2


# -----------------------------------------------------------------------------
# Test clamp_inspector_cursor
# -----------------------------------------------------------------------------

class TestClampInspectorCursor:
    """Test clamp_inspector_cursor function."""

    def test_valid_cursor_unchanged(self, minimal_entity):
        """Valid cursor should be returned unchanged."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=0)

        result = clamp_inspector_cursor(cursor, sections)

        assert result.section_id == "transform"
        assert result.row_index == 0

    def test_invalid_section_clamps_to_first(self, minimal_entity):
        """Cursor with invalid section should clamp to first section."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="nonexistent", row_index=0)

        result = clamp_inspector_cursor(cursor, sections)

        assert result.section_id == "transform"
        assert result.row_index == 0

    def test_row_index_clamps_to_visible(self, minimal_entity):
        """Row index beyond visible rows should clamp."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=999)

        result = clamp_inspector_cursor(cursor, sections)

        assert result.section_id == "transform"
        # Should clamp to last visible row
        visible_count = len(sections[0].visible_rows)
        assert result.row_index == visible_count - 1

    def test_empty_sections_returns_default(self):
        """Empty sections list should return default cursor."""
        cursor = InspectorCursor(section_id="transform", row_index=0)
        result = clamp_inspector_cursor(cursor, [])

        # Should return default
        assert result.section_id == "transform"
        assert result.row_index == 0


# -----------------------------------------------------------------------------
# Test move_cursor
# -----------------------------------------------------------------------------

class TestMoveCursor:
    """Test move_cursor function."""

    def test_move_down_from_header(self, minimal_entity):
        """Move down from header should go to first field."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=0)

        result = move_cursor(cursor, sections, "down")

        assert result.section_id == "transform"
        assert result.row_index == 1

    def test_move_up_from_first_stays(self, minimal_entity):
        """Move up from first row should stay at first."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=0)

        result = move_cursor(cursor, sections, "up")

        assert result.section_id == "transform"
        assert result.row_index == 0

    def test_move_down_clamps_at_bottom(self, minimal_entity):
        """Move down at last row should stay at last."""
        sections = build_inspector_sections(minimal_entity)
        last_row = len(sections[0].visible_rows) - 1
        cursor = InspectorCursor(section_id="transform", row_index=last_row)

        result = move_cursor(cursor, sections, "down")

        assert result.row_index == last_row

    def test_move_across_sections(self, full_entity):
        """Move down should cross section boundaries."""
        sections = build_inspector_sections(full_entity)
        # Start at last row of transform
        transform = sections[0]
        last_transform_row = len(transform.visible_rows) - 1
        cursor = InspectorCursor(section_id="transform", row_index=last_transform_row)

        result = move_cursor(cursor, sections, "down")

        # Should be in next section
        assert result.section_id != "transform" or result.row_index > last_transform_row


# -----------------------------------------------------------------------------
# Test get_cursor_row
# -----------------------------------------------------------------------------

class TestGetCursorRow:
    """Test get_cursor_row function."""

    def test_valid_cursor_returns_row(self, minimal_entity):
        """Valid cursor should return the correct row."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=0)

        row = get_cursor_row(cursor, sections)

        assert row is not None
        assert row.kind == "header"

    def test_field_cursor_returns_field(self, minimal_entity):
        """Cursor on field should return field row."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=1)

        row = get_cursor_row(cursor, sections)

        assert row is not None
        assert row.kind == "field"

    def test_invalid_section_returns_none(self, minimal_entity):
        """Invalid section should return None."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="nonexistent", row_index=0)

        row = get_cursor_row(cursor, sections)

        assert row is None


# -----------------------------------------------------------------------------
# Test apply_inspector_edit
# -----------------------------------------------------------------------------

class TestApplyInspectorEdit:
    """Test apply_inspector_edit function."""

    def test_numeric_delta_adjusts_value(self, minimal_entity):
        """Numeric delta should adjust float value."""
        sections = build_inspector_sections(minimal_entity)
        # Cursor on x field (index 1, after header)
        cursor = InspectorCursor(section_id="transform", row_index=1)

        new_json, changed = apply_inspector_edit(
            minimal_entity, cursor, sections, 5.0, is_text_commit=False
        )

        assert changed is True
        assert new_json["x"] == 105.0  # 100 + 5

    def test_negative_delta_decreases_value(self, minimal_entity):
        """Negative delta should decrease value."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=1)  # x field

        new_json, changed = apply_inspector_edit(
            minimal_entity, cursor, sections, -10.0, is_text_commit=False
        )

        assert changed is True
        assert new_json["x"] == 90.0  # 100 - 10

    def test_string_commit_updates_value(self, full_entity):
        """Text commit should update string field."""
        sections = build_inspector_sections(full_entity)
        # Find interaction section and interact_label field
        interaction_section = next((s for s in sections if s.id == "interaction"), None)
        assert interaction_section is not None

        # Find interact_label row index
        for i, row in enumerate(interaction_section.visible_rows):
            if row.key == "interact_label":
                cursor = InspectorCursor(section_id="interaction", row_index=i)
                break
        else:
            pytest.fail("interact_label field not found")

        new_json, changed = apply_inspector_edit(
            full_entity, cursor, sections, "Speak", is_text_commit=True
        )

        assert changed is True
        assert new_json["interact_label"] == "Speak"

    def test_unchanged_value_returns_false(self, minimal_entity):
        """Edit that doesn't change value should return changed=False."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=1)  # x field

        new_json, changed = apply_inspector_edit(
            minimal_entity, cursor, sections, 0.0, is_text_commit=False
        )

        assert changed is False

    def test_header_row_not_editable(self, minimal_entity):
        """Editing header row should return unchanged."""
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=0)  # header

        new_json, changed = apply_inspector_edit(
            minimal_entity, cursor, sections, 100.0, is_text_commit=False
        )

        assert changed is False

    def test_nested_field_edit(self, light_only_entity):
        """Edit should work on nested fields like behaviour_config."""
        sections = build_inspector_sections(light_only_entity)
        light_section = next((s for s in sections if s.id == "light_source"), None)
        assert light_section is not None

        # Find radius row
        for i, row in enumerate(light_section.visible_rows):
            if "radius" in row.key:
                cursor = InspectorCursor(section_id="light_source", row_index=i)
                break
        else:
            pytest.fail("radius field not found")

        new_json, changed = apply_inspector_edit(
            light_only_entity, cursor, sections, 32.0, is_text_commit=False
        )

        assert changed is True
        # Check nested value
        assert new_json["behaviour_config"]["LightSource"]["radius"] == 160.0  # 128 + 32

    def test_bool_toggle(self, full_entity):
        """Bool field should toggle on edit."""
        sections = build_inspector_sections(full_entity)
        interaction_section = next((s for s in sections if s.id == "interaction"), None)
        assert interaction_section is not None

        # Find solid row
        for i, row in enumerate(interaction_section.visible_rows):
            if row.key == "solid":
                cursor = InspectorCursor(section_id="interaction", row_index=i)
                original_value = row.value
                break
        else:
            pytest.fail("solid field not found")

        new_json, changed = apply_inspector_edit(
            full_entity, cursor, sections, True, is_text_commit=False
        )

        assert changed is True
        assert new_json["solid"] != original_value


# -----------------------------------------------------------------------------
# Test format_field_value
# -----------------------------------------------------------------------------

class TestFormatFieldValue:
    """Test format_field_value function."""

    def test_format_float(self):
        """Float should format with 1 decimal."""
        result = format_field_value(123.456, "float")
        assert result == "123.5"

    def test_format_int_float(self):
        """Integer float should show .0."""
        result = format_field_value(100.0, "float")
        assert result == "100.0"

    def test_format_bool_true(self):
        """True should format as 'Yes'."""
        result = format_field_value(True, "bool")
        assert result == "Yes"

    def test_format_bool_false(self):
        """False should format as 'No'."""
        result = format_field_value(False, "bool")
        assert result == "No"

    def test_format_string(self):
        """String should pass through."""
        result = format_field_value("hello", "string")
        assert result == "hello"

    def test_format_none(self):
        """None should format as empty string."""
        result = format_field_value(None, "string")
        assert result == ""


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

class TestInspectorIntegration:
    """Integration tests for inspector workflow."""

    def test_collapse_expand_workflow(self, full_entity):
        """Test collapse/expand doesn't affect entity data."""
        expanded_state: Dict[str, bool] = {}

        # Build initial sections
        sections1 = build_inspector_sections(full_entity, expanded_state=expanded_state)
        initial_count = sum(len(s.visible_rows) for s in sections1)

        # Collapse transform
        expanded_state = toggle_section(expanded_state, "transform")
        sections2 = build_inspector_sections(full_entity, expanded_state=expanded_state)

        # Should have fewer visible rows
        collapsed_count = sum(len(s.visible_rows) for s in sections2)
        assert collapsed_count < initial_count

        # Expand again
        expanded_state = toggle_section(expanded_state, "transform")
        sections3 = build_inspector_sections(full_entity, expanded_state=expanded_state)

        # Should be back to original
        restored_count = sum(len(s.visible_rows) for s in sections3)
        assert restored_count == initial_count

    def test_navigation_after_collapse(self, full_entity):
        """Cursor should clamp properly after section collapse."""
        expanded_state: Dict[str, bool] = {}
        sections = build_inspector_sections(full_entity, expanded_state=expanded_state)

        # Put cursor on last field of transform
        transform = sections[0]
        last_row = len(transform.visible_rows) - 1
        cursor = InspectorCursor(section_id="transform", row_index=last_row)

        # Collapse transform
        expanded_state = toggle_section(expanded_state, "transform")
        sections = build_inspector_sections(full_entity, expanded_state=expanded_state)

        # Clamp cursor
        cursor = clamp_inspector_cursor(cursor, sections)

        # Should now be on header (only visible row)
        assert cursor.row_index == 0

    def test_edit_does_not_mutate_original(self, minimal_entity):
        """Edit should not mutate the original entity dict."""
        original_x = minimal_entity["x"]
        sections = build_inspector_sections(minimal_entity)
        cursor = InspectorCursor(section_id="transform", row_index=1)

        new_json, changed = apply_inspector_edit(
            minimal_entity, cursor, sections, 50.0, is_text_commit=False
        )

        assert changed is True
        assert new_json["x"] == original_x + 50.0
        assert minimal_entity["x"] == original_x  # Original unchanged

    def test_section_visibility_based_on_entity(self):
        """Sections should only appear when entity has relevant data."""
        # Entity with no sprite - no render section
        no_sprite_entity = {"id": "test", "x": 0, "y": 0}
        sections = build_inspector_sections(no_sprite_entity)
        section_ids = [s.id for s in sections]
        assert "render" not in section_ids

        # Add sprite - render section should appear
        with_sprite_entity = {"id": "test", "x": 0, "y": 0, "sprite": "test.png"}
        sections = build_inspector_sections(with_sprite_entity)
        section_ids = [s.id for s in sections]
        assert "render" in section_ids
