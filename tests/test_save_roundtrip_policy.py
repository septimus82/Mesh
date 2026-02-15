from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour
from engine.diagnostics import sort_diagnostics
from engine.gameplay_event_bus import GameplayEventBus
from engine.persistence_io import SAVE_FORMAT_VERSION, write_text_atomic
from engine.save_runtime import io as save_io
from engine.save_runtime.restore_policy import SLOT_POLICY, SNAPSHOT_POLICY, RestorePolicy
from engine.save_runtime.schema import SAVE_SCHEMA_VERSION
from engine.save_runtime.state_codec import encode_state


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    # Keep insertion-order JSON formatting fixed so byte-level round-trip
    # assertions measure payload stability, not writer-format variation.
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
        sort_keys=False,
    )
    write_text_atomic(path, text + "\n")


def _load_and_validate(path: Path, *, policy: RestorePolicy) -> tuple[dict[str, Any], tuple[Any, ...]]:
    ok, payload, diagnostics = save_io.load_and_validate_payload(
        path,
        source=str(path),
        strict_schema=policy.strict_schema,
        policy=policy,
    )
    assert ok is True
    assert isinstance(payload, dict)
    return payload, diagnostics


def _slot_payload_with_wrapped_runners() -> dict[str, Any]:
    return {
        "save_format_version": SAVE_FORMAT_VERSION,
        "save_schema_version": SAVE_SCHEMA_VERSION,
        "version": 1,
        "meta": {"slot": "slot1", "timestamp": "2026-01-01T00:00:00Z", "version": 1},
        "world_file": "worlds/test_world.json",
        "world_id": "test_world",
        "scene_path": "scenes/test_scene.json",
        "scene_id": "scenes/test_scene.json",
        "spawn_zone_id": "spawn_a",
        "gold": 5,
        "flags": {"campaign.active": True},
        "game_state": {"flags": {"campaign.active": True}, "counters": {"gold": 5}},
        "state": {"flags": {"campaign.active": True}, "counters": {"gold": 5}},
        "saved_flags": {"campaign.active": True, "episode_01_complete": True},
        "saved_entities": {
            "schema_version": 1,
            "entities": [
                {
                    "entity_id": "entity_alpha",
                    "x": 12.0,
                    "y": 24.0,
                    "behaviour_state": {
                        "DialogueRunnerBehaviour": encode_state(
                            "dialogue_runner",
                            1,
                            {
                                "enabled": True,
                                "current_node": "start",
                                "visited_nodes": ["start"],
                                "choice_history": [],
                                "is_running": True,
                                "completed": False,
                            },
                        ),
                    },
                },
                {
                    "entity_id": "entity_beta",
                    "x": 36.0,
                    "y": 48.0,
                    "behaviour_state": {},
                },
            ],
        },
        "saved_quests": {
            "schema_version": 1,
            "quests": {
                "episode_01": {
                    "quest_id": "episode_01",
                    "state": "completed",
                    "current_step": "done",
                    "counters": {"objective_count": 3},
                }
            },
        },
        "saved_runners": {
            "cutscene_runner": encode_state(
                "cutscene_runner",
                1,
                {
                    "script_id": "ep01_intro",
                    "command_index": 2,
                    "is_running": False,
                    "completed": True,
                },
            ),
            "dialogue_runner": encode_state(
                "dialogue_runner",
                1,
                {
                    "enabled": True,
                    "current_node": "start",
                    "visited_nodes": ["start"],
                    "choice_history": [],
                    "is_running": True,
                    "completed": False,
                },
            ),
            "quest_runner": encode_state(
                "quest_runner",
                1,
                {
                    "quests": {
                        "episode_01": {
                            "quest_id": "episode_01",
                            "state": "completed",
                            "current_step": "done",
                            "counters": {"objective_count": 3},
                        }
                    }
                },
            ),
        },
        "saved_time": {"day": 2, "hour": 18},
    }


def _upgrade_dialogue_runner_state(
    payload: dict[str, Any],
    *,
    source: str,
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    upgraded = copy.deepcopy(payload)
    legacy_state = upgraded.get("saved_runners", {}).get("dialogue_runner")
    if not isinstance(legacy_state, dict):
        return upgraded, ()

    entity = SimpleNamespace(mesh_id="dialogue_entity", mesh_name="DialogueEntity", mesh_tags=[])
    window = SimpleNamespace(gameplay_event_bus=GameplayEventBus())
    runner = DialogueRunnerBehaviour(
        entity,
        window,
        script={"start": {"text": "Hello", "next": None}},
        start_node="start",
    )
    runner.restore_state(legacy_state, strict=False, source=source)
    upgraded["saved_runners"]["dialogue_runner"] = runner.saveable_state()
    return upgraded, tuple(getattr(runner, "_last_restore_diagnostics", ()))


def roundtrip_n(
    *,
    initial_payload: dict[str, Any],
    tmp_path: Path,
    stem: str,
    policy: RestorePolicy,
    n: int = 3,
    post_load_adapter: Any | None = None,
) -> list[dict[str, Any]]:
    assert n >= 2
    payload = copy.deepcopy(initial_payload)
    records: list[dict[str, Any]] = []

    for pass_index in range(1, n + 1):
        save_path = tmp_path / f"{stem}_pass{pass_index}.json"
        _write_payload(save_path, payload)

        saved_bytes = read_bytes(save_path)
        pass_record: dict[str, Any] = {
            "pass_index": pass_index,
            "path": save_path,
            "bytes": saved_bytes,
            "sha256": sha256(saved_bytes),
            "diagnostics": (),
            "diagnostic_codes": (),
        }

        if pass_index < n:
            loaded_payload, load_diags = _load_and_validate(save_path, policy=policy)
            extra_diags: tuple[Any, ...] = ()
            if post_load_adapter is not None:
                loaded_payload, extra_diags = post_load_adapter(
                    loaded_payload,
                    pass_index=pass_index,
                )
            combined = tuple(sort_diagnostics((*load_diags, *extra_diags)))
            payload = loaded_payload
            pass_record["diagnostics"] = combined
            pass_record["diagnostic_codes"] = tuple(diag.code for diag in combined)

        records.append(pass_record)

    return records


def test_slot_policy_roundtrip_is_byte_identical_and_clean(tmp_path: Path) -> None:
    records = roundtrip_n(
        initial_payload=_slot_payload_with_wrapped_runners(),
        tmp_path=tmp_path,
        stem="slot_roundtrip",
        policy=SLOT_POLICY,
        n=3,
    )

    for record in records:
        assert record["diagnostic_codes"] == (), (
            f"slot pass {record['pass_index']} produced unexpected diagnostics: "
            f"{record['diagnostic_codes']}"
        )

    for idx in range(1, len(records)):
        prev_record = records[idx - 1]
        cur_record = records[idx]
        assert prev_record["bytes"] == cur_record["bytes"], (
            "slot bytes diverged between passes "
            f"{prev_record['pass_index']}->{cur_record['pass_index']}; "
            f"sha(prev)={prev_record['sha256']} sha(cur)={cur_record['sha256']}"
        )
        assert prev_record["sha256"] == cur_record["sha256"], (
            "slot sha256 diverged between passes "
            f"{prev_record['pass_index']}->{cur_record['pass_index']}; "
            f"sha(prev)={prev_record['sha256']} sha(cur)={cur_record['sha256']}"
        )


def test_snapshot_policy_roundtrip_preserves_unknown_keys_and_is_byte_identical(tmp_path: Path) -> None:
    payload = _slot_payload_with_wrapped_runners()
    payload["x_unknown_snapshot_key"] = {"note": "preserve-me", "values": [1, 2, 3]}
    payload["saved_entities"]["x_nested_unknown"] = {"note": "nested-preserve", "rank": 7}
    payload["saved_runners"]["x_runner_unknown"] = {"state": "preserve"}

    records = roundtrip_n(
        initial_payload=payload,
        tmp_path=tmp_path,
        stem="snapshot_roundtrip",
        policy=SNAPSHOT_POLICY,
        n=3,
    )

    final_path = records[-1]["path"]
    _, final_payload, _ = save_io.load_and_validate_payload(
        final_path,
        source=str(final_path),
        strict_schema=SNAPSHOT_POLICY.strict_schema,
        policy=SNAPSHOT_POLICY,
    )
    assert isinstance(final_payload, dict)
    assert final_payload.get("x_unknown_snapshot_key") == {"note": "preserve-me", "values": [1, 2, 3]}
    assert final_payload.get("saved_entities", {}).get("x_nested_unknown") == {"note": "nested-preserve", "rank": 7}
    assert final_payload.get("saved_runners", {}).get("x_runner_unknown") == {"state": "preserve"}

    for idx in range(1, len(records)):
        prev_record = records[idx - 1]
        cur_record = records[idx]
        assert prev_record["bytes"] == cur_record["bytes"], (
            "snapshot bytes diverged between passes "
            f"{prev_record['pass_index']}->{cur_record['pass_index']}; "
            f"sha(prev)={prev_record['sha256']} sha(cur)={cur_record['sha256']}"
        )
        assert prev_record["sha256"] == cur_record["sha256"], (
            "snapshot sha256 diverged between passes "
            f"{prev_record['pass_index']}->{cur_record['pass_index']}; "
            f"sha(prev)={prev_record['sha256']} sha(cur)={cur_record['sha256']}"
        )


def test_legacy_upgrade_roundtrip_is_clean_on_second_pass(tmp_path: Path) -> None:
    payload = _slot_payload_with_wrapped_runners()
    payload.pop("scene_path", None)
    payload["scene"] = "scenes/test_scene.json"
    payload["saved_runners"]["dialogue_runner"] = {
        "enabled": True,
        "current_node": "start",
        "visited_nodes": ["start"],
        "choice_history": [],
        "is_running": True,
        "completed": False,
    }

    def _legacy_adapter(loaded_payload: dict[str, Any], *, pass_index: int) -> tuple[dict[str, Any], tuple[Any, ...]]:
        return _upgrade_dialogue_runner_state(
            loaded_payload,
            source=f"tests/save_roundtrip/legacy_pass_{pass_index}",
        )

    records = roundtrip_n(
        initial_payload=payload,
        tmp_path=tmp_path,
        stem="legacy_roundtrip",
        policy=SNAPSHOT_POLICY,
        n=3,
        post_load_adapter=_legacy_adapter,
    )

    first_codes = records[0]["diagnostic_codes"]
    second_codes = records[1]["diagnostic_codes"]
    third_codes = records[2]["diagnostic_codes"]

    expected_first_codes = (
        "NORMALIZED_DICT_ORDER",
        "NORMALIZED_KEY_RENAMED",
        "SAVE_STATE_LEGACY_UPGRADED",
    )
    assert first_codes == expected_first_codes, (
        "legacy first pass warning codes changed; "
        f"expected={expected_first_codes} actual={first_codes}"
    )
    assert second_codes == (), (
        "legacy second pass should be clean; "
        f"actual={second_codes}"
    )
    assert third_codes == (), (
        "legacy third pass should be clean; "
        f"actual={third_codes}"
    )

    pass2_path = records[1]["path"]
    _, pass2_payload, _ = save_io.load_and_validate_payload(
        pass2_path,
        source=str(pass2_path),
        strict_schema=SNAPSHOT_POLICY.strict_schema,
        policy=SNAPSHOT_POLICY,
    )
    assert isinstance(pass2_payload, dict)
    assert pass2_payload["scene_path"] == "scenes/test_scene.json"
    assert "scene" not in pass2_payload
    assert pass2_payload["saved_runners"]["dialogue_runner"]["type"] == "dialogue_runner"
    assert pass2_payload["saved_runners"]["dialogue_runner"]["state_version"] == 1

    pass2_record = records[1]
    pass3_record = records[2]
    assert pass2_record["bytes"] == pass3_record["bytes"], (
        "legacy bytes diverged between pass2 and pass3; "
        f"sha(pass2)={pass2_record['sha256']} sha(pass3)={pass3_record['sha256']}"
    )
    assert pass2_record["sha256"] == pass3_record["sha256"], (
        "legacy sha256 diverged between pass2 and pass3; "
        f"sha(pass2)={pass2_record['sha256']} sha(pass3)={pass3_record['sha256']}"
    )
