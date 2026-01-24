"""Contract tests for editor copy/paste functionality.

These tests verify the clipboard operations work correctly
without any arcade/pygame dependencies (pure unit tests).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from engine.editor.editor_clipboard_ops import (
    clone_entity_payload,
    collect_existing_entity_ids,
    generate_copy_entity_id,
    get_entity_id_from_data,
)


# ------------------------------------------------------------------------------
# generate_copy_entity_id tests
# ------------------------------------------------------------------------------


class TestGenerateCopyEntityId:
    """Tests for generate_copy_entity_id function."""

    def test_first_copy_gets_copy_1(self) -> None:
        """First copy of an entity gets _copy_1 suffix."""
        existing_ids = ["player", "enemy"]
        result = generate_copy_entity_id(existing_ids, "player")
        assert result == "player_copy_1"

    def test_second_copy_gets_copy_2(self) -> None:
        """Second copy increments the number."""
        existing_ids = ["player", "player_copy_1"]
        result = generate_copy_entity_id(existing_ids, "player")
        assert result == "player_copy_2"

    def test_handles_existing_copy_without_number(self) -> None:
        """Handles legacy _copy suffix without number."""
        existing_ids = ["player", "player_copy"]
        result = generate_copy_entity_id(existing_ids, "player")
        assert result == "player_copy_2"

    def test_copying_a_copy_uses_base(self) -> None:
        """Copying a copy still uses the base name."""
        existing_ids = ["player", "player_copy_1"]
        result = generate_copy_entity_id(existing_ids, "player_copy_1")
        assert result == "player_copy_2"

    def test_handles_gaps_in_numbering(self) -> None:
        """Uses next number even if there are gaps."""
        existing_ids = ["player", "player_copy_1", "player_copy_5"]
        result = generate_copy_entity_id(existing_ids, "player")
        assert result == "player_copy_6"

    def test_empty_existing_ids(self) -> None:
        """Works with empty existing IDs list."""
        result = generate_copy_entity_id([], "enemy")
        assert result == "enemy_copy_1"

    def test_deterministic_ordering(self) -> None:
        """Same inputs always produce same output."""
        existing_ids = ["a", "b", "c"]
        result1 = generate_copy_entity_id(existing_ids, "a")
        result2 = generate_copy_entity_id(existing_ids, "a")
        assert result1 == result2


# ------------------------------------------------------------------------------
# clone_entity_payload tests
# ------------------------------------------------------------------------------


class TestCloneEntityPayload:
    """Tests for clone_entity_payload function."""

    def test_deep_copies_entity(self) -> None:
        """Entity is deep copied, not referenced."""
        original = {"id": "test", "x": 100, "nested": {"value": 1}}
        cloned = clone_entity_payload(original, "test_copy_1", (200, 300))

        # Modify cloned nested value
        cloned["nested"]["value"] = 999

        # Original should be unchanged
        assert original["nested"]["value"] == 1

    def test_updates_position(self) -> None:
        """Position is updated to new coordinates."""
        original = {"id": "test", "x": 100, "y": 200}
        cloned = clone_entity_payload(original, "test_copy_1", (500, 600))

        assert cloned["x"] == 500.0
        assert cloned["y"] == 600.0

    def test_updates_id_field(self) -> None:
        """ID field is updated with new ID."""
        original = {"id": "test", "x": 0, "y": 0}
        cloned = clone_entity_payload(original, "new_id", (0, 0))

        assert cloned["id"] == "new_id"

    def test_updates_entity_id_field(self) -> None:
        """entity_id field is updated if present."""
        original = {"entity_id": "test", "x": 0, "y": 0}
        cloned = clone_entity_payload(original, "new_id", (0, 0))

        assert cloned["entity_id"] == "new_id"

    def test_updates_name_field(self) -> None:
        """name field is updated if present."""
        original = {"name": "test", "x": 0, "y": 0}
        cloned = clone_entity_payload(original, "new_id", (0, 0))

        assert cloned["name"] == "new_id"

    def test_adds_name_if_no_id_fields(self) -> None:
        """Adds name field if no id fields exist."""
        original = {"x": 0, "y": 0, "sprite": "test.png"}
        cloned = clone_entity_payload(original, "new_id", (0, 0))

        assert cloned["name"] == "new_id"

    def test_preserves_other_fields(self) -> None:
        """Other fields are preserved."""
        original = {
            "id": "test",
            "x": 0,
            "y": 0,
            "prefab_id": "slime",
            "tags": ["enemy", "boss"],
            "behaviour_config": {"patrol": {"speed": 50}},
        }
        cloned = clone_entity_payload(original, "test_copy_1", (100, 200))

        assert cloned["prefab_id"] == "slime"
        assert cloned["tags"] == ["enemy", "boss"]
        assert cloned["behaviour_config"]["patrol"]["speed"] == 50


# ------------------------------------------------------------------------------
# get_entity_id_from_data tests
# ------------------------------------------------------------------------------


class TestGetEntityIdFromData:
    """Tests for get_entity_id_from_data function."""

    def test_prefers_id(self) -> None:
        """Uses 'id' field if present."""
        data = {"id": "my_id", "name": "my_name"}
        assert get_entity_id_from_data(data) == "my_id"

    def test_uses_entity_id_second(self) -> None:
        """Uses 'entity_id' if 'id' not present."""
        data = {"entity_id": "eid", "name": "my_name"}
        assert get_entity_id_from_data(data) == "eid"

    def test_uses_mesh_name_third(self) -> None:
        """Uses 'mesh_name' if id fields not present."""
        data = {"mesh_name": "mesh", "name": "my_name"}
        assert get_entity_id_from_data(data) == "mesh"

    def test_uses_name_fourth(self) -> None:
        """Uses 'name' as last resort."""
        data = {"name": "my_name", "x": 0}
        assert get_entity_id_from_data(data) == "my_name"

    def test_returns_unnamed_if_none(self) -> None:
        """Returns 'unnamed' if no ID found."""
        data = {"x": 0, "y": 0}
        assert get_entity_id_from_data(data) == "unnamed"

    def test_strips_whitespace(self) -> None:
        """Strips whitespace from IDs."""
        data = {"id": "  my_id  "}
        assert get_entity_id_from_data(data) == "my_id"

    def test_skips_empty_strings(self) -> None:
        """Skips empty string values."""
        data = {"id": "", "name": "fallback"}
        assert get_entity_id_from_data(data) == "fallback"


# ------------------------------------------------------------------------------
# collect_existing_entity_ids tests
# ------------------------------------------------------------------------------


class TestCollectExistingEntityIds:
    """Tests for collect_existing_entity_ids function."""

    def test_collects_ids_from_sprites(self) -> None:
        """Collects IDs from sprite mesh_entity_data."""
        sprite1 = MagicMock()
        sprite1.mesh_entity_data = {"id": "entity_1"}
        sprite2 = MagicMock()
        sprite2.mesh_entity_data = {"name": "entity_2"}

        ids = collect_existing_entity_ids([sprite1, sprite2])
        assert ids == ["entity_1", "entity_2"]

    def test_skips_sprites_without_data(self) -> None:
        """Skips sprites without mesh_entity_data."""
        sprite1 = MagicMock()
        sprite1.mesh_entity_data = {"id": "entity_1"}
        sprite2 = MagicMock()
        sprite2.mesh_entity_data = None

        ids = collect_existing_entity_ids([sprite1, sprite2])
        assert ids == ["entity_1"]

    def test_skips_unnamed_entities(self) -> None:
        """Skips entities with 'unnamed' ID."""
        sprite1 = MagicMock()
        sprite1.mesh_entity_data = {"id": "entity_1"}
        sprite2 = MagicMock()
        sprite2.mesh_entity_data = {"x": 0}  # No ID fields

        ids = collect_existing_entity_ids([sprite1, sprite2])
        assert ids == ["entity_1"]

    def test_preserves_order(self) -> None:
        """Preserves sprite order in result."""
        sprites = []
        for name in ["c", "a", "b"]:
            s = MagicMock()
            s.mesh_entity_data = {"id": name}
            sprites.append(s)

        ids = collect_existing_entity_ids(sprites)
        assert ids == ["c", "a", "b"]


# ------------------------------------------------------------------------------
# Integration tests
# ------------------------------------------------------------------------------


class TestCopyPasteIntegration:
    """Integration-style tests for copy/paste workflow."""

    def test_full_copy_paste_workflow(self) -> None:
        """Test full workflow: collect IDs, generate new ID, clone."""
        # Setup: existing sprites
        sprites = []
        for name in ["player", "enemy", "player_copy_1"]:
            s = MagicMock()
            s.mesh_entity_data = {"id": name, "x": 0, "y": 0}
            sprites.append(s)

        # Collect existing IDs
        existing_ids = collect_existing_entity_ids(sprites)
        assert "player" in existing_ids
        assert "player_copy_1" in existing_ids

        # Generate new ID for a copy of "player"
        new_id = generate_copy_entity_id(existing_ids, "player")
        assert new_id == "player_copy_2"

        # Clone the entity
        original_data = {"id": "player", "x": 100, "y": 200, "prefab_id": "hero"}
        cloned = clone_entity_payload(original_data, new_id, (300, 400))

        assert cloned["id"] == "player_copy_2"
        assert cloned["x"] == 300.0
        assert cloned["y"] == 400.0
        assert cloned["prefab_id"] == "hero"

    def test_multiple_pastes_increment_correctly(self) -> None:
        """Multiple pastes generate sequential IDs."""
        existing_ids = ["enemy"]

        # First paste
        id1 = generate_copy_entity_id(existing_ids, "enemy")
        assert id1 == "enemy_copy_1"
        existing_ids.append(id1)

        # Second paste
        id2 = generate_copy_entity_id(existing_ids, "enemy")
        assert id2 == "enemy_copy_2"
        existing_ids.append(id2)

        # Third paste
        id3 = generate_copy_entity_id(existing_ids, "enemy")
        assert id3 == "enemy_copy_3"


# ------------------------------------------------------------------------------
# Context menu tests
# ------------------------------------------------------------------------------


class TestContextMenuCopyPaste:
    """Tests for context menu copy/paste items."""

    def test_copy_enabled_with_selection(self) -> None:
        """Copy is enabled when there's a selection."""
        from engine.editor.context_menu_model import build_context_menu_items

        controller = MagicMock()
        controller.selected_entity = MagicMock()
        controller._entity_clipboard = None

        items = build_context_menu_items(controller)
        copy_item = next(i for i in items if i.id == "ctx_copy")

        assert copy_item.enabled is True

    def test_copy_disabled_without_selection(self) -> None:
        """Copy is disabled when there's no selection."""
        from engine.editor.context_menu_model import build_context_menu_items

        controller = MagicMock()
        controller.selected_entity = None
        controller._entity_clipboard = None

        items = build_context_menu_items(controller)
        copy_item = next(i for i in items if i.id == "ctx_copy")

        assert copy_item.enabled is False

    def test_paste_enabled_with_clipboard(self) -> None:
        """Paste is enabled when clipboard has content."""
        from engine.editor.context_menu_model import build_context_menu_items

        controller = MagicMock()
        controller.selected_entity = None
        controller._entity_clipboard = {"id": "test"}

        items = build_context_menu_items(controller)
        paste_item = next(i for i in items if i.id == "ctx_paste")

        assert paste_item.enabled is True

    def test_paste_disabled_without_clipboard(self) -> None:
        """Paste is disabled when clipboard is empty."""
        from engine.editor.context_menu_model import build_context_menu_items

        controller = MagicMock()
        controller.selected_entity = MagicMock()
        controller._entity_clipboard = None

        items = build_context_menu_items(controller)
        paste_item = next(i for i in items if i.id == "ctx_paste")

        assert paste_item.enabled is False


# ------------------------------------------------------------------------------
# Text input mode tests
# ------------------------------------------------------------------------------


class TestTextInputBlocking:
    """Tests for _is_text_input_active function."""

    def test_blocks_during_palette_filter(self) -> None:
        """Copy/paste blocked during palette filter."""
        from engine.editor_runtime.input import _is_text_input_active

        controller = MagicMock()
        controller.palette_filter_active = True

        assert _is_text_input_active(controller) is True

    def test_blocks_during_hierarchy_rename(self) -> None:
        """Copy/paste blocked during hierarchy rename."""
        from engine.editor_runtime.input import _is_text_input_active

        controller = MagicMock()
        controller.palette_filter_active = False
        controller.hierarchy_filter_active = False
        controller.hierarchy_rename_active = True

        assert _is_text_input_active(controller) is True

    def test_allows_when_not_in_text_mode(self) -> None:
        """Copy/paste allowed when not in text input mode."""
        from engine.editor_runtime.input import _is_text_input_active

        controller = MagicMock()
        controller.palette_filter_active = False
        controller.hierarchy_filter_active = False
        controller.hierarchy_rename_active = False
        controller.animation_edit_active = False
        controller.inspector_edit_active = False
        controller.command_palette_active = False
        controller.entity_panels_filter_active = False

        assert _is_text_input_active(controller) is False
