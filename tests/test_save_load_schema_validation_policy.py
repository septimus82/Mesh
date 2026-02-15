from __future__ import annotations

import json
from pathlib import Path

from engine.diagnostics import diagnostics_to_json, diagnostics_to_text, sort_diagnostics
from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_runtime import io as save_io
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_slot_load_rejects_malformed_schema_payload(tmp_path: Path) -> None:
    path = tmp_path / "slot_bad.json"
    _write_json(
        path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "world_file": "worlds/act1_prologue.json",
            "world_id": "act1_prologue",
            "scene_id": "packs/core_regions/scenes/Act1_Prologue_Cabin.json",
            "gold": 1,
            "flags": [],
            "saved_entities": "bad-type",
            "saved_quests": [],
        },
    )

    ok, payload_or_error = save_io.load_slot_payload(path)
    assert ok is False
    msg = str(payload_or_error)
    assert msg.startswith("[Mesh][Save] ERROR:")
    assert "saved_entities must be a dict" in msg
    assert "code=save.load.schema_validation_error" in msg
    assert "pointer=$/saved_entities" in msg

    ok2, payload2, diagnostics = save_io.load_and_validate_payload(path, source=str(path), strict_schema=True)
    assert ok2 is False
    assert payload2 is None
    assert tuple(diag.code for diag in diagnostics) == ("save.load.schema_validation_error",)
    context = diagnostics[0].context
    assert str(context.get("pointer", "")).startswith("$/")
    assert str(context.get("file", "")).endswith("slot_bad.json")


def test_slot_load_accepts_minimal_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "slot_ok.json"
    _write_json(
        path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "flags": [],
            "gold": 0,
            "game_state": {"flags": {}, "counters": {"gold": 0}},
            "saved_entities": {"schema_version": 1, "entities": []},
            "saved_quests": {"schema_version": 1, "quests": {}},
        },
    )

    ok, payload_or_error = save_io.load_slot_payload(path)
    assert ok is True
    payload = payload_or_error
    assert isinstance(payload, dict)
    assert payload.get("save_format_version") == SAVE_FORMAT_VERSION
    assert payload.get("save_schema_version") == SAVE_SCHEMA_VERSION


def test_snapshot_load_policy_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "snapshot_bad.json"
    _write_json(
        path,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "world_id": "act1_prologue",
            "scene_id": "packs/core_regions/scenes/Act1_Prologue_Cabin.json",
            "gold": "oops",
            "flags": [],
            "saved_entities": {"schema_version": 1, "entities": []},
            "saved_quests": {"schema_version": 1, "quests": {}},
        },
    )

    ok, payload_or_error = save_io.load_snapshot_payload(path)
    assert ok is False
    msg = str(payload_or_error)
    assert msg.startswith("[Mesh][Snapshot] ERROR:")
    assert "gold must be a number" in msg
    assert "code=save.load.schema_validation_error" in msg

    ok2, payload2, diagnostics = save_io.load_and_validate_payload(path, source=str(path), strict_schema=True)
    assert ok2 is False
    assert payload2 is None
    assert tuple(diag.code for diag in diagnostics) == ("save.load.schema_validation_error",)


def test_diagnostics_are_deterministic_sorted(tmp_path: Path) -> None:
    path_a = tmp_path / "a_bad.json"
    path_b = tmp_path / "b_bad.json"
    _write_json(
        path_a,
        {
            "save_format_version": SAVE_FORMAT_VERSION + 999,
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "flags": [],
        },
    )
    _write_json(
        path_b,
        {
            "save_format_version": SAVE_FORMAT_VERSION,
            "save_schema_version": SAVE_SCHEMA_VERSION,
            "game_state": [],
            "flags": [],
        },
    )

    _, _, diagnostics_a = save_io.load_and_validate_payload(path_a, source=str(path_a), strict_schema=True)
    _, _, diagnostics_b = save_io.load_and_validate_payload(path_b, source=str(path_b), strict_schema=True)
    diagnostics_combined = sort_diagnostics((*diagnostics_b, *diagnostics_a))
    diagnostics_combined_reversed = sort_diagnostics((*diagnostics_a, *diagnostics_b))

    assert [item.to_dict() for item in diagnostics_combined] == [item.to_dict() for item in diagnostics_combined_reversed]

    text_1 = diagnostics_to_text(diagnostics_combined)
    text_2 = diagnostics_to_text(diagnostics_combined_reversed)
    assert text_1 == text_2

    json_1 = diagnostics_to_json(diagnostics_combined)
    json_2 = diagnostics_to_json(diagnostics_combined_reversed)
    assert json_1 == json_2

    codes = [diag.code for diag in diagnostics_combined]
    assert codes == sorted(codes)
