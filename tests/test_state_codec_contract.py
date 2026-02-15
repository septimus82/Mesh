from __future__ import annotations

from engine.diagnostics import diagnostics_to_json, diagnostics_to_text
from engine.save_runtime.state_codec import decode_state, encode_state


def test_encode_state_returns_wrapped_shape() -> None:
    payload = encode_state("dialogue_runner", 1, {"current_node": "start"})
    assert payload == {
        "type": "dialogue_runner",
        "state_version": 1,
        "state": {"current_node": "start"},
    }


def test_decode_state_happy_path() -> None:
    state, diagnostics = decode_state(
        {"type": "cutscene_runner", "state_version": 1, "state": {"command_index": 2}},
        expected_type_id="cutscene_runner",
        supported_versions={1},
        strict=True,
        source="tests/cutscene.json",
    )
    assert state == {"command_index": 2}
    assert diagnostics == []


def test_decode_state_strict_type_mismatch_is_deterministic() -> None:
    state, diagnostics = decode_state(
        {"type": "wrong_type", "state_version": "x"},
        expected_type_id="quest_runner",
        supported_versions={1},
        strict=True,
        source="tests/slot.json",
    )
    assert state is None
    codes = tuple(item.code for item in diagnostics)
    assert codes == (
        "SAVE_STATE_STATE_MISSING",
        "SAVE_STATE_TYPE_MISMATCH",
        "SAVE_STATE_VERSION_INVALID",
    )
    text = diagnostics_to_text(diagnostics)
    assert "/state" in text
    assert "/type" in text
    assert "/state_version" in text


def test_decode_state_unsupported_version() -> None:
    state, diagnostics = decode_state(
        {"type": "quest_runner", "state_version": 99, "state": {}},
        expected_type_id="quest_runner",
        supported_versions={1},
        strict=True,
        source="tests/slot.json",
    )
    assert state is None
    assert tuple(item.code for item in diagnostics) == ("SAVE_STATE_VERSION_UNSUPPORTED",)


def test_decode_state_legacy_upgrade_path_non_strict() -> None:
    legacy_payload = {
        "enabled": True,
        "current_node": "start",
        "visited_nodes": ["start"],
        "choice_history": [],
        "is_running": True,
        "completed": False,
    }
    state, diagnostics = decode_state(
        legacy_payload,
        expected_type_id="dialogue_runner",
        supported_versions={1},
        strict=False,
        source="tests/dialogue_snapshot.json",
        legacy_v0_predicate=lambda payload: "current_node" in payload,
        legacy_v0_adapter=lambda payload: dict(payload),
    )
    assert state == legacy_payload
    assert tuple(item.code for item in diagnostics) == ("SAVE_STATE_LEGACY_UPGRADED",)
    assert "legacy" in diagnostics[0].message.lower()


def test_decode_state_diagnostics_json_text_are_stable() -> None:
    _, diagnostics_a = decode_state(
        {"type": 1, "state_version": "nope", "state": []},
        expected_type_id="dialogue_runner",
        supported_versions={1},
        strict=True,
        source="tests/a.json",
    )
    _, diagnostics_b = decode_state(
        {"state": []},
        expected_type_id="dialogue_runner",
        supported_versions={1},
        strict=True,
        source="tests/a.json",
    )
    blob_1 = diagnostics_to_json((*diagnostics_a, *diagnostics_b))
    blob_2 = diagnostics_to_json((*diagnostics_b, *diagnostics_a))
    assert blob_1 == blob_2
    text_1 = diagnostics_to_text((*diagnostics_a, *diagnostics_b))
    text_2 = diagnostics_to_text((*diagnostics_b, *diagnostics_a))
    assert text_1 == text_2
