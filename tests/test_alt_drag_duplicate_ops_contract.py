"""Contract tests for alt_drag_duplicate_ops pure module.

Tests alt-drag duplicate computation as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import copy
import pytest

from engine.editor.editor_alt_drag_duplicate_ops import (
    DuplicateEntitySpec,
    AltDragDuplicateCommand,
    normalize_selection_ids,
    compute_next_copy_ids,
    duplicate_entities_in_scene,
    apply_drag_delta_to_specs,
    apply_alt_drag_duplicate,
    remove_alt_drag_duplicates,
    should_start_alt_drag_duplicate,
)
from tests._typing import as_any


# -----------------------------------------------------------------------------
# normalize_selection_ids
# -----------------------------------------------------------------------------


class TestNormalizeSelectionIds:
    """Tests for normalize_selection_ids function."""

    def test_sorts_ids_alphabetically(self) -> None:
        result = normalize_selection_ids(["z_entity", "a_entity", "m_entity"])
        assert result == ["a_entity", "m_entity", "z_entity"]

    def test_empty_list(self) -> None:
        result = normalize_selection_ids([])
        assert result == []

    def test_single_id(self) -> None:
        result = normalize_selection_ids(["only_one"])
        assert result == ["only_one"]

    def test_already_sorted(self) -> None:
        result = normalize_selection_ids(["a", "b", "c"])
        assert result == ["a", "b", "c"]


# -----------------------------------------------------------------------------
# compute_next_copy_ids
# -----------------------------------------------------------------------------


class TestComputeNextCopyIds:
    """Tests for compute_next_copy_ids function."""

    def test_first_copy_gets_copy_1(self) -> None:
        scene_entities = [{"id": "entity_a"}, {"id": "entity_b"}]
        result = compute_next_copy_ids(scene_entities, ["entity_a"])
        assert result == {"entity_a": "entity_a_copy_1"}

    def test_increments_from_existing_copy(self) -> None:
        scene_entities = [
            {"id": "entity_a"},
            {"id": "entity_a_copy_1"},
        ]
        result = compute_next_copy_ids(scene_entities, ["entity_a"])
        assert result == {"entity_a": "entity_a_copy_2"}

    def test_multiple_existing_copies(self) -> None:
        scene_entities = [
            {"id": "entity_a"},
            {"id": "entity_a_copy_1"},
            {"id": "entity_a_copy_2"},
            {"id": "entity_a_copy_5"},  # Gap
        ]
        result = compute_next_copy_ids(scene_entities, ["entity_a"])
        assert result == {"entity_a": "entity_a_copy_6"}

    def test_batch_copy_unique_ids(self) -> None:
        scene_entities = [{"id": "entity_a"}, {"id": "entity_b"}]
        result = compute_next_copy_ids(scene_entities, ["entity_a", "entity_b"])
        assert result["entity_a"] == "entity_a_copy_1"
        assert result["entity_b"] == "entity_b_copy_1"

    def test_batch_copy_same_base_increments(self) -> None:
        # When copying multiple entities with same base, each should get unique ID
        scene_entities = [{"id": "entity_a"}, {"id": "entity_a_copy_1"}]
        # If we copy entity_a and entity_a_copy_1, they share base "entity_a"
        result = compute_next_copy_ids(scene_entities, ["entity_a", "entity_a_copy_1"])
        # Both should get unique IDs
        assert result["entity_a"] == "entity_a_copy_2"
        assert result["entity_a_copy_1"] == "entity_a_copy_3"

    def test_strips_existing_copy_suffix(self) -> None:
        scene_entities = [{"id": "test_copy_1"}]
        result = compute_next_copy_ids(scene_entities, ["test_copy_1"])
        # Should strip _copy_1 and create test_copy_2
        assert result == {"test_copy_1": "test_copy_2"}

    def test_entity_id_key_fallback(self) -> None:
        scene_entities = [{"entity_id": "entity_a"}]
        result = compute_next_copy_ids(scene_entities, ["entity_a"])
        assert result == {"entity_a": "entity_a_copy_1"}

    def test_name_key_fallback(self) -> None:
        scene_entities = [{"name": "entity_a"}]
        result = compute_next_copy_ids(scene_entities, ["entity_a"])
        assert result == {"entity_a": "entity_a_copy_1"}


# -----------------------------------------------------------------------------
# duplicate_entities_in_scene
# -----------------------------------------------------------------------------


class TestDuplicateEntitiesInScene:
    """Tests for duplicate_entities_in_scene function."""

    def test_duplicates_single_entity(self) -> None:
        scene = {
            "entities": [
                {"id": "entity_a", "x": 100.0, "y": 200.0, "sprite": "test.png"},
            ]
        }
        new_scene, specs = duplicate_entities_in_scene(scene, ["entity_a"])

        assert len(specs) == 1
        assert specs[0].src_id == "entity_a"
        assert specs[0].new_id == "entity_a_copy_1"
        assert specs[0].start_xy == (100.0, 200.0)
        assert specs[0].end_xy == (100.0, 200.0)
        assert specs[0].entity_json["id"] == "entity_a_copy_1"
        assert specs[0].entity_json["sprite"] == "test.png"

        # Scene should have 2 entities
        assert len(new_scene["entities"]) == 2

    def test_duplicates_multiple_entities(self) -> None:
        scene = {
            "entities": [
                {"id": "entity_a", "x": 0.0, "y": 0.0},
                {"id": "entity_b", "x": 50.0, "y": 50.0},
            ]
        }
        new_scene, specs = duplicate_entities_in_scene(scene, ["entity_a", "entity_b"])

        assert len(specs) == 2
        # Specs should be sorted by ID
        assert specs[0].src_id == "entity_a"
        assert specs[1].src_id == "entity_b"

        # Scene should have 4 entities
        assert len(new_scene["entities"]) == 4

    def test_deep_copies_entity_data(self) -> None:
        original_behaviour = {"type": "patrol", "points": [[0, 0], [100, 100]]}
        scene = {
            "entities": [
                {"id": "entity_a", "x": 0.0, "y": 0.0, "behaviours": [original_behaviour]},
            ]
        }
        new_scene, specs = duplicate_entities_in_scene(scene, ["entity_a"])

        # Modify the original
        original_behaviour["points"].append([200, 200])

        # Spec should not be affected (deep copy)
        assert len(specs[0].entity_json["behaviours"][0]["points"]) == 2

    def test_preserves_all_fields_except_id(self) -> None:
        scene = {
            "entities": [
                {
                    "id": "entity_a",
                    "x": 10.0,
                    "y": 20.0,
                    "scale": 2.0,
                    "rotation": 45.0,
                    "custom_field": "preserved",
                },
            ]
        }
        new_scene, specs = duplicate_entities_in_scene(scene, ["entity_a"])

        new_entity = specs[0].entity_json
        assert new_entity["id"] == "entity_a_copy_1"
        assert new_entity["x"] == 10.0
        assert new_entity["y"] == 20.0
        assert new_entity["scale"] == 2.0
        assert new_entity["rotation"] == 45.0
        assert new_entity["custom_field"] == "preserved"

    def test_original_scene_not_mutated(self) -> None:
        scene = {
            "entities": [
                {"id": "entity_a", "x": 0.0, "y": 0.0},
            ]
        }
        original_count = len(scene["entities"])
        new_scene, specs = duplicate_entities_in_scene(scene, ["entity_a"])

        assert len(scene["entities"]) == original_count
        assert len(new_scene["entities"]) == original_count + 1

    def test_empty_selection_returns_empty(self) -> None:
        scene = {"entities": [{"id": "entity_a"}]}
        new_scene, specs = duplicate_entities_in_scene(scene, [])
        assert specs == []
        assert len(new_scene["entities"]) == 1

    def test_missing_entity_skipped(self) -> None:
        scene = {"entities": [{"id": "entity_a"}]}
        new_scene, specs = duplicate_entities_in_scene(scene, ["nonexistent"])
        assert specs == []
        assert len(new_scene["entities"]) == 1


# -----------------------------------------------------------------------------
# apply_drag_delta_to_specs
# -----------------------------------------------------------------------------


class TestApplyDragDeltaToSpecs:
    """Tests for apply_drag_delta_to_specs function."""

    def test_applies_delta_to_all(self) -> None:
        specs = [
            DuplicateEntitySpec("a", "a_copy_1", {}, (0.0, 0.0), (0.0, 0.0)),
            DuplicateEntitySpec("b", "b_copy_1", {}, (100.0, 100.0), (100.0, 100.0)),
        ]
        result = apply_drag_delta_to_specs(specs, (50.0, 25.0), False, "grid16", 16, "a_copy_1")

        assert result[0].end_xy == (50.0, 25.0)
        assert result[1].end_xy == (150.0, 125.0)

    def test_snaps_pivot_only(self) -> None:
        specs = [
            DuplicateEntitySpec("a", "a_copy_1", {}, (0.0, 0.0), (0.0, 0.0)),
            DuplicateEntitySpec("b", "b_copy_1", {}, (5.0, 5.0), (5.0, 5.0)),
        ]
        # Delta that would snap to grid16
        result = apply_drag_delta_to_specs(specs, (17.0, 17.0), True, "grid16", 16, "a_copy_1")

        # Pivot (a_copy_1) should snap: 0 + 17 = 17 -> snaps to 16
        # Delta becomes 16, applied to all
        assert result[0].end_xy == (16.0, 16.0)
        assert result[1].end_xy == (21.0, 21.0)  # 5 + 16 = 21

    def test_no_snap_when_disabled(self) -> None:
        specs = [
            DuplicateEntitySpec("a", "a_copy_1", {}, (0.0, 0.0), (0.0, 0.0)),
        ]
        result = apply_drag_delta_to_specs(specs, (17.0, 17.0), False, "grid16", 16, "a_copy_1")

        assert result[0].end_xy == (17.0, 17.0)

    def test_empty_specs(self) -> None:
        result = apply_drag_delta_to_specs([], (10.0, 10.0), True, "grid16", 16, None)
        assert result == []

    def test_fallback_pivot_if_not_found(self) -> None:
        specs = [
            DuplicateEntitySpec("a", "a_copy_1", {}, (0.0, 0.0), (0.0, 0.0)),
        ]
        # Pivot ID doesn't match, should use first spec
        result = apply_drag_delta_to_specs(specs, (10.0, 10.0), False, "grid16", 16, "nonexistent")

        assert result[0].end_xy == (10.0, 10.0)


# -----------------------------------------------------------------------------
# apply_alt_drag_duplicate
# -----------------------------------------------------------------------------


class TestApplyAltDragDuplicate:
    """Tests for apply_alt_drag_duplicate function."""

    def test_adds_new_entities(self) -> None:
        scene = {"entities": [{"id": "original"}]}
        cmd = AltDragDuplicateCommand(
            specs=(
                DuplicateEntitySpec("original", "original_copy_1", {"id": "original_copy_1", "x": 0.0, "y": 0.0}, (0.0, 0.0), (100.0, 100.0)),
            ),
        )
        result = apply_alt_drag_duplicate(scene, cmd)

        assert len(result["entities"]) == 2
        new_entity = next(e for e in result["entities"] if e.get("id") == "original_copy_1")
        assert new_entity["x"] == 100.0
        assert new_entity["y"] == 100.0

    def test_updates_existing_positions(self) -> None:
        scene = {
            "entities": [
                {"id": "original"},
                {"id": "original_copy_1", "x": 0.0, "y": 0.0},
            ]
        }
        cmd = AltDragDuplicateCommand(
            specs=(
                DuplicateEntitySpec("original", "original_copy_1", {"id": "original_copy_1"}, (0.0, 0.0), (50.0, 50.0)),
            ),
        )
        result = apply_alt_drag_duplicate(scene, cmd)

        # Should still have 2 entities, but position updated
        assert len(result["entities"]) == 2
        copy_entity = next(e for e in result["entities"] if e.get("id") == "original_copy_1")
        assert copy_entity["x"] == 50.0
        assert copy_entity["y"] == 50.0

    def test_does_not_touch_originals(self) -> None:
        scene = {"entities": [{"id": "original", "x": 10.0, "y": 20.0}]}
        cmd = AltDragDuplicateCommand(
            specs=(
                DuplicateEntitySpec("original", "original_copy_1", {"id": "original_copy_1"}, (10.0, 20.0), (100.0, 100.0)),
            ),
        )
        result = apply_alt_drag_duplicate(scene, cmd)

        original = next(e for e in result["entities"] if e.get("id") == "original")
        assert original["x"] == 10.0
        assert original["y"] == 20.0


# -----------------------------------------------------------------------------
# remove_alt_drag_duplicates
# -----------------------------------------------------------------------------


class TestRemoveAltDragDuplicates:
    """Tests for remove_alt_drag_duplicates function."""

    def test_removes_duplicated_entities(self) -> None:
        scene = {
            "entities": [
                {"id": "original"},
                {"id": "original_copy_1"},
            ]
        }
        cmd = AltDragDuplicateCommand(
            specs=(
                DuplicateEntitySpec("original", "original_copy_1", {}, (0.0, 0.0), (100.0, 100.0)),
            ),
        )
        result = remove_alt_drag_duplicates(scene, cmd)

        assert len(result["entities"]) == 1
        assert result["entities"][0]["id"] == "original"

    def test_leaves_other_entities(self) -> None:
        scene = {
            "entities": [
                {"id": "original"},
                {"id": "original_copy_1"},
                {"id": "unrelated"},
            ]
        }
        cmd = AltDragDuplicateCommand(
            specs=(
                DuplicateEntitySpec("original", "original_copy_1", {}, (0.0, 0.0), (0.0, 0.0)),
            ),
        )
        result = remove_alt_drag_duplicates(scene, cmd)

        assert len(result["entities"]) == 2
        ids = [e["id"] for e in result["entities"]]
        assert "original" in ids
        assert "unrelated" in ids
        assert "original_copy_1" not in ids

    def test_handles_missing_duplicates(self) -> None:
        scene = {"entities": [{"id": "original"}]}
        cmd = AltDragDuplicateCommand(
            specs=(
                DuplicateEntitySpec("original", "nonexistent_copy", {}, (0.0, 0.0), (0.0, 0.0)),
            ),
        )
        result = remove_alt_drag_duplicates(scene, cmd)

        # Should not error, just leave scene as-is
        assert len(result["entities"]) == 1


# -----------------------------------------------------------------------------
# should_start_alt_drag_duplicate
# -----------------------------------------------------------------------------


class TestShouldStartAltDragDuplicate:
    """Tests for should_start_alt_drag_duplicate function."""

    def test_starts_when_all_conditions_met(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id="entity_a",
            selected_ids=["entity_a", "entity_b"],
            alt_held=True,
            editor_mode_active=True,
            gizmo_active=False,
        ) is True

    def test_no_start_without_alt(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id="entity_a",
            selected_ids=["entity_a"],
            alt_held=False,
            editor_mode_active=True,
            gizmo_active=False,
        ) is False

    def test_no_start_when_editor_inactive(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id="entity_a",
            selected_ids=["entity_a"],
            alt_held=True,
            editor_mode_active=False,
            gizmo_active=False,
        ) is False

    def test_no_start_when_gizmo_active(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id="entity_a",
            selected_ids=["entity_a"],
            alt_held=True,
            editor_mode_active=True,
            gizmo_active=True,
        ) is False

    def test_no_start_when_clicked_not_in_selection(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id="entity_c",
            selected_ids=["entity_a", "entity_b"],
            alt_held=True,
            editor_mode_active=True,
            gizmo_active=False,
        ) is False

    def test_no_start_with_empty_selection(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id="entity_a",
            selected_ids=[],
            alt_held=True,
            editor_mode_active=True,
            gizmo_active=False,
        ) is False

    def test_no_start_without_clicked_entity(self) -> None:
        assert should_start_alt_drag_duplicate(
            clicked_entity_id=None,
            selected_ids=["entity_a"],
            alt_held=True,
            editor_mode_active=True,
            gizmo_active=False,
        ) is False


# -----------------------------------------------------------------------------
# AltDragDuplicateCommand serialization
# -----------------------------------------------------------------------------


class TestAltDragDuplicateCommandSerialization:
    """Tests for AltDragDuplicateCommand to_dict/from_dict."""

    def test_round_trip_serialization(self) -> None:
        original = AltDragDuplicateCommand(
            kind="alt_drag_duplicate",
            specs=(
                DuplicateEntitySpec("a", "a_copy_1", {"id": "a_copy_1", "x": 10.0}, (0.0, 0.0), (100.0, 100.0)),
                DuplicateEntitySpec("b", "b_copy_1", {"id": "b_copy_1"}, (50.0, 50.0), (150.0, 150.0)),
            ),
            pivot_src_id="a",
            pivot_new_id="a_copy_1",
            snap_enabled=True,
            snap_mode="grid16",
        )

        serialized = original.to_dict()
        restored = AltDragDuplicateCommand.from_dict(serialized)

        assert restored.kind == original.kind
        assert len(restored.specs) == len(original.specs)
        assert restored.specs[0].src_id == "a"
        assert restored.specs[0].new_id == "a_copy_1"
        assert restored.specs[0].start_xy == (0.0, 0.0)
        assert restored.specs[0].end_xy == (100.0, 100.0)
        assert restored.pivot_src_id == "a"
        assert restored.pivot_new_id == "a_copy_1"
        assert restored.snap_enabled is True
        assert restored.snap_mode == "grid16"

    def test_to_dict_type_field(self) -> None:
        cmd = AltDragDuplicateCommand()
        d = cmd.to_dict()
        assert d["type"] == "AltDragDuplicate"


# -----------------------------------------------------------------------------
# DuplicateEntitySpec
# -----------------------------------------------------------------------------


class TestDuplicateEntitySpec:
    """Tests for DuplicateEntitySpec dataclass."""

    def test_creation(self) -> None:
        spec = DuplicateEntitySpec(
            src_id="original",
            new_id="original_copy_1",
            entity_json={"id": "original_copy_1", "x": 100.0},
            start_xy=(0.0, 0.0),
            end_xy=(100.0, 100.0),
        )
        assert spec.src_id == "original"
        assert spec.new_id == "original_copy_1"
        assert spec.entity_json["x"] == 100.0
        assert spec.start_xy == (0.0, 0.0)
        assert spec.end_xy == (100.0, 100.0)

    def test_frozen(self) -> None:
        spec = DuplicateEntitySpec("a", "b", {}, (0.0, 0.0), (0.0, 0.0))
        with pytest.raises(AttributeError):
            as_any(spec).src_id = "changed"
