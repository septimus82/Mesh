from __future__ import annotations

import json
from pathlib import Path

from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_runtime import io as save_io
from engine.save_runtime.normalize import normalize_save_payload
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION
from mesh_cli import replays as replays_module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_missing_defaults_are_added_with_deterministic_warning_codes() -> None:
    payload = {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": SAVE_SCHEMA_VERSION,
        "game_state": {"flags": {}, "counters": {"gold": 0}},
    }
    normalized, diagnostics = normalize_save_payload(payload, source="tests/normalize_defaults")

    for required in ("saved_flags", "saved_entities", "saved_quests", "saved_runners", "saved_time"):
        assert required in normalized
    codes = [diag.code for diag in diagnostics]
    assert "NORMALIZED_DEFAULT_ADDED" in codes
    assert codes == sorted(codes)


def test_legacy_scene_key_renamed_to_scene_path_with_warning() -> None:
    payload = {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": SAVE_SCHEMA_VERSION,
        "scene": "scenes/legacy.json",
        "game_state": {"flags": {}, "counters": {"gold": 0}},
    }
    normalized, diagnostics = normalize_save_payload(payload, source="tests/normalize_scene")

    assert "scene" not in normalized
    assert normalized["scene_path"] == "scenes/legacy.json"
    rename_diags = [diag for diag in diagnostics if diag.code == "NORMALIZED_KEY_RENAMED"]
    assert len(rename_diags) == 1
    assert rename_diags[0].context.get("old_pointer") == "/scene"


def test_saved_entities_flags_runners_are_canonically_ordered() -> None:
    payload = {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": SAVE_SCHEMA_VERSION,
        "saved_flags": {"z_flag": True, "a_flag": False},
        "saved_runners": {"runner_b": {"k": 2}, "runner_a": {"k": 1}},
        "saved_entities": {
            "entities": [
                {"entity_id": "z_entity", "x": 1.0, "y": 1.0},
                {"entity_id": "a_entity", "x": 2.0, "y": 2.0},
            ],
            "schema_version": 1,
        },
        "saved_quests": {"schema_version": 1, "quests": {"q_b": {}, "q_a": {}}},
    }
    normalized_a, diagnostics_a = normalize_save_payload(payload, source="tests/normalize_order_a")
    normalized_b, diagnostics_b = normalize_save_payload(payload, source="tests/normalize_order_b")

    assert list(normalized_a["saved_flags"].keys()) == ["a_flag", "z_flag"]
    assert list(normalized_a["saved_runners"].keys()) == ["runner_a", "runner_b"]
    assert [entry["entity_id"] for entry in normalized_a["saved_entities"]["entities"]] == ["a_entity", "z_entity"]
    assert list(normalized_a["saved_quests"]["quests"].keys()) == ["q_a", "q_b"]
    assert normalized_a == normalized_b
    assert [diag.code for diag in diagnostics_a] == [diag.code for diag in diagnostics_b]


def test_event_history_lists_are_not_reordered() -> None:
    payload = {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": SAVE_SCHEMA_VERSION,
        "event_history": [
            {"sequence": 3, "event_type": "third"},
            {"sequence": 1, "event_type": "first"},
            {"sequence": 2, "event_type": "second"},
        ],
    }
    normalized, _ = normalize_save_payload(payload, source="tests/normalize_history")
    assert normalized["event_history"] == payload["event_history"]


def test_io_load_path_applies_normalization_after_schema_validation(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    _write_json(
        path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "gold": 0,
            "flags": [],
            "game_state": {"flags": {}, "counters": {"gold": 0}},
            "saved_entities": {"schema_version": 1, "entities": []},
            "saved_quests": {"schema_version": 1, "quests": {}},
        },
    )
    ok, normalized_payload, diagnostics = save_io.load_and_validate_payload(
        path,
        source=str(path),
        strict_schema=True,
    )
    assert ok is True
    assert isinstance(normalized_payload, dict)
    assert "saved_flags" in normalized_payload
    assert "saved_runners" in normalized_payload
    assert "saved_time" in normalized_payload
    assert any(diag.code == "NORMALIZED_DEFAULT_ADDED" for diag in diagnostics)


def test_non_save_payload_digest_inputs_are_unchanged_by_normalizer() -> None:
    final_state_payload = {
        "schema_version": 1,
        "final_state": {"player_hp": 10, "flags": {"ep01_complete": True}},
        "snapshots": [{"tick": 1, "frame": 1}, {"tick": 2, "frame": 2}],
    }
    normalized, diagnostics = normalize_save_payload(
        final_state_payload,
        source="tests/non_save_payload",
    )
    assert normalized == final_state_payload
    assert diagnostics == []

    before = replays_module._sha256_payload(
        replays_module._project_final_state_for_golden_digest(final_state_payload)
    )
    after = replays_module._sha256_payload(
        replays_module._project_final_state_for_golden_digest(normalized)
    )
    assert before == after

