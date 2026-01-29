"""Contract tests for history label formatting."""

from __future__ import annotations

from engine.editor.history_label_model import (
    build_history_label_for_command,
    format_history_entry,
    normalize_action_label,
)


def test_history_label_formatting_deterministic() -> None:
    label = format_history_entry(
        "editor.background_planes.add",
        "Background Planes: Add",
        {"plane_id": "plane_001"},
    )
    assert label == "Background Planes: Add (plane:plane_001)"


def test_history_label_normalize_fallback() -> None:
    assert normalize_action_label("editor.history.undo", "") == "editor.history.undo"


def test_history_label_entity_ops_deterministic() -> None:
    add_cmd = {"type": "AddEntity", "entity_name": "crate_01"}
    assert build_history_label_for_command(add_cmd) == "Add Entity (entity:crate_01)"

    move_cmd = {"type": "MoveEntity", "entity_name": "crate_01"}
    assert build_history_label_for_command(move_cmd) == "Move Entity (entity:crate_01)"

    rename_cmd = {"type": "RenameEntity", "before": "old", "after": "new"}
    assert build_history_label_for_command(rename_cmd) == "Rename Entity (from:old, to:new)"


def test_history_label_variant_ops_deterministic() -> None:
    edit_cmd = {"type": "EditPrefabOverride", "entity_id": "e1", "key": "x"}
    assert build_history_label_for_command(edit_cmd) == "Edit Prefab Override (entity:e1, field:x)"

    clear_cmd = {"type": "ClearPrefabOverrides", "entity_name": "e1"}
    assert build_history_label_for_command(clear_cmd) == "Clear Prefab Overrides (entity:e1, field:all)"


def test_history_label_field_edit_deterministic() -> None:
    cmd = {
        "type": "InspectorEdit",
        "entity_id": "crate_01",
        "field_key": "x",
        "before": 1.23456,
        "after": 2.34567,
    }
    assert build_history_label_for_command(cmd) == "Set x - crate_01 (1.235 -> 2.346)"


def test_history_label_lights_occluders_deterministic() -> None:
    light_cmd = {"type": "EditLight", "index": 2, "field": "radius", "before": 120, "after": 140}
    assert build_history_label_for_command(light_cmd) == "Set Light radius - light:2 (120 -> 140)"

    add_light_cmd = {"type": "AddLight", "index": 1}
    assert build_history_label_for_command(add_light_cmd) == "Add Light (light:1)"

    occ_cmd = {"type": "EditOccluder", "cmd": {"kind": "delete_polygon", "payload": {"occ_id": "occ_1"}}}
    assert build_history_label_for_command(occ_cmd) == "Delete Occluder (occluder:occ_1)"
