from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import savegame
from engine.diagnostics import clear_diagnostics, get_diagnostics_payload
from engine.persistence_io import SAVE_FORMAT_VERSION
from engine.save_manager import SaveManager
from engine.save_runtime.ux_codes import (
    LOAD_FALLBACK_TO_START_SCENE,
    LOAD_NOT_FOUND,
    LOAD_PARSE_FAILED,
    LOAD_SCHEMA_INVALID,
    SAVE_LOAD_CODES,
    SAVE_SERIALIZE_FAILED,
    SAVE_SLOT_INVALID,
    SAVE_WRITE_FAILED,
)

pytestmark = [pytest.mark.fast]


class _Window:
    def __init__(self) -> None:
        self.engine_config = type("Cfg", (), {"start_scene": "scenes/runtime_smoke_scene.json"})()
        self.requested_scenes: list[str] = []

    def request_scene_change(self, scene_path: str) -> None:
        self.requested_scenes.append(str(scene_path))


def _schema_mismatch_payload() -> dict[str, object]:
    return {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": 2,
        "gold": 1,
        "flags": [],
        "saved_entities": "bad-type",
        "saved_quests": [],
    }


def test_save_load_ux_code_contract() -> None:
    required = (
        LOAD_NOT_FOUND,
        LOAD_PARSE_FAILED,
        LOAD_SCHEMA_INVALID,
        "LOAD_APPLY_FAILED",
        LOAD_FALLBACK_TO_START_SCENE,
        SAVE_WRITE_FAILED,
        SAVE_SERIALIZE_FAILED,
        SAVE_SLOT_INVALID,
    )
    for code in required:
        assert code in SAVE_LOAD_CODES


@pytest.mark.parametrize(
    ("case_name", "writer", "expected_code", "slot_index"),
    [
        ("missing", None, LOAD_NOT_FOUND, 11),
        ("corrupt_json", "{", LOAD_PARSE_FAILED, 12),
        ("schema_mismatch", _schema_mismatch_payload(), LOAD_SCHEMA_INVALID, 13),
    ],
)
def test_save_manager_load_failures_emit_structured_diagnostics_and_fallback(
    tmp_path: Path, case_name: str, writer: object, expected_code: str, slot_index: int
) -> None:
    clear_diagnostics()
    window = _Window()
    manager = SaveManager(window, save_dir=str(tmp_path / "saves"))
    slot_name = f"slot_{slot_index}"
    slot_path = manager.get_save_path(slot_name)

    if isinstance(writer, str):
        slot_path.parent.mkdir(parents=True, exist_ok=True)
        slot_path.write_text(writer, encoding="utf-8")
    elif isinstance(writer, dict):
        slot_path.parent.mkdir(parents=True, exist_ok=True)
        slot_path.write_text(json.dumps(writer, sort_keys=True) + "\n", encoding="utf-8")

    ok = manager.load_game(slot_name)
    assert ok is False
    assert window.requested_scenes == ["scenes/runtime_smoke_scene.json"]

    payload_a = get_diagnostics_payload()
    payload_b = get_diagnostics_payload()
    assert payload_a == payload_b
    codes = tuple(str(item.get("code", "")) for item in payload_a if isinstance(item, dict))
    assert expected_code in codes
    assert LOAD_FALLBACK_TO_START_SCENE in codes

    primary = next(item for item in payload_a if isinstance(item, dict) and item.get("code") == expected_code)
    assert primary.get("source") == "engine.save_manager"
    assert isinstance(primary.get("hint"), str) and str(primary.get("hint"))
    context = primary.get("context")
    assert isinstance(context, dict)
    assert "pointer" in context
    assert context.get("operation") == "load"
    assert context.get("save_path") == slot_path.as_posix()
    assert context.get("slot") == slot_index

    fallback = next(
        item for item in payload_a if isinstance(item, dict) and item.get("code") == LOAD_FALLBACK_TO_START_SCENE
    )
    fallback_context = fallback.get("context")
    assert isinstance(fallback_context, dict)
    assert fallback_context.get("operation") == "load"
    assert fallback_context.get("save_path") == slot_path.as_posix()
    assert fallback_context.get("slot") == slot_index
    assert fallback_context.get("target_scene") == "scenes/runtime_smoke_scene.json"


def test_apply_savegame_invalid_payload_emits_error_and_fallback() -> None:
    clear_diagnostics()
    window = _Window()
    ok = savegame.apply_savegame(window, {"version": 999})
    assert ok is False
    assert window.requested_scenes == ["scenes/runtime_smoke_scene.json"]

    payload = get_diagnostics_payload()
    codes = tuple(str(item.get("code", "")) for item in payload if isinstance(item, dict))
    assert codes == (LOAD_SCHEMA_INVALID, LOAD_FALLBACK_TO_START_SCENE)
    fallback = payload[1]
    context = fallback.get("context")
    assert isinstance(context, dict)
    assert context.get("target_scene") == "scenes/runtime_smoke_scene.json"


@pytest.mark.parametrize(
    ("case_name", "writer", "expected_code", "slot_index"),
    [
        ("missing", None, LOAD_NOT_FOUND, 21),
        ("corrupt_json", "{", LOAD_PARSE_FAILED, 22),
        ("schema_mismatch", {"version": 999, "scene_path": "scenes/runtime_smoke_scene.json"}, LOAD_SCHEMA_INVALID, 23),
    ],
)
def test_load_savegame_failures_emit_structured_diagnostics(
    tmp_path: Path, case_name: str, writer: object, expected_code: str, slot_index: int
) -> None:
    clear_diagnostics()
    path = tmp_path / f"slot_{slot_index}.json"

    if isinstance(writer, str):
        path.write_text(writer, encoding="utf-8")
    elif isinstance(writer, dict):
        path.write_text(json.dumps(writer, sort_keys=True) + "\n", encoding="utf-8")

    loaded = savegame.load_savegame(path)
    assert loaded is None

    payload_a = get_diagnostics_payload()
    payload_b = get_diagnostics_payload()
    assert payload_a == payload_b

    codes = tuple(str(item.get("code", "")) for item in payload_a if isinstance(item, dict))
    assert expected_code in codes

    entry = next(item for item in payload_a if isinstance(item, dict) and item.get("code") == expected_code)
    assert entry.get("source") == "engine.savegame"
    assert isinstance(entry.get("hint"), str) and str(entry.get("hint"))
    context = entry.get("context")
    assert isinstance(context, dict)
    assert "pointer" in context
    assert context.get("operation") == "load"
    assert context.get("save_path") == path.as_posix()
    assert context.get("slot") == slot_index
