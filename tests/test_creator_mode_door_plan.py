from __future__ import annotations

import dataclasses
import subprocess
import sys
from copy import deepcopy

import pytest

from engine.editor.creator_mode import CreatorDoorPlanRequest, build_creator_door_plan

pytestmark = pytest.mark.fast


def test_valid_minimal_request_produces_ok_plan() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(
            source_scene="forest",
            destination_scene="town",
        )
    )

    assert plan.ok is True
    assert plan.errors == ()
    assert [operation.op for operation in plan.operations] == [
        "ensure_door_entity",
        "configure_door_transition",
    ]


def test_valid_request_with_destination_spawn_produces_deterministic_operations() -> None:
    request = CreatorDoorPlanRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        door_name="North Gate",
        source_entity_id="door_north",
        locked=True,
        required_flag="gate_unlocked",
        trigger="touch",
    )

    first = build_creator_door_plan(request)
    second = build_creator_door_plan(request)

    assert first == second
    assert first.ok is True
    assert first.warnings == ()
    assert [operation.op for operation in first.operations] == [
        "ensure_door_entity",
        "configure_door_transition",
        "configure_lock",
    ]
    assert [operation.target for operation in first.operations] == ["door_north"] * 3


def test_missing_source_scene_returns_error() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(source_scene="", destination_scene="town")
    )

    assert plan.ok is False
    assert "Source scene is required." in plan.errors
    assert plan.operations == ()


def test_missing_destination_scene_returns_error() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(source_scene="forest", destination_scene="")
    )

    assert plan.ok is False
    assert "Destination scene is required." in plan.errors
    assert plan.operations == ()


def test_locked_without_required_flag_returns_error() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(
            source_scene="forest",
            destination_scene="town",
            locked=True,
        )
    )

    assert plan.ok is False
    assert "Locked doors require a required flag." in plan.errors
    assert plan.operations == ()


def test_missing_destination_spawn_warns_but_allows_plan() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(source_scene="forest", destination_scene="town")
    )

    assert plan.ok is True
    assert plan.warnings == ("Door has no destination spawn point.",)


def test_invalid_trigger_returns_error() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(
            source_scene="forest",
            destination_scene="town",
            trigger="script",
        )
    )

    assert plan.ok is False
    assert "Trigger must be one of: interact, touch, auto." in plan.errors


def test_whitespace_is_trimmed() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(
            source_scene=" forest ",
            destination_scene=" town ",
            destination_spawn_id=" north_gate_entry ",
            door_name=" North Gate ",
            source_entity_id=" door_north ",
            required_flag=" gate_unlocked ",
            trigger=" interact ",
        )
    )

    payload = dict(plan.operations[0].payload)
    assert payload["source_scene"] == "forest"
    assert payload["destination_scene"] == "town"
    assert payload["destination_spawn_id"] == "north_gate_entry"
    assert payload["door_name"] == "North Gate"
    assert payload["source_entity_id"] == "door_north"
    assert payload["required_flag"] == "gate_unlocked"
    assert payload["trigger"] == "interact"


def test_request_object_is_not_mutated() -> None:
    request = CreatorDoorPlanRequest(
        source_scene=" forest ",
        destination_scene=" town ",
        destination_spawn_id=" north_gate_entry ",
    )
    before = dataclasses.asdict(request)

    build_creator_door_plan(request)

    assert dataclasses.asdict(request) == before


def test_input_data_copy_is_not_mutated() -> None:
    data = {
        "source_scene": " forest ",
        "destination_scene": " town ",
        "destination_spawn_id": " north_gate_entry ",
    }
    before = deepcopy(data)
    request = CreatorDoorPlanRequest(**data)

    build_creator_door_plan(request)

    assert data == before


def test_operation_payload_contains_friendly_intent_fields() -> None:
    request = CreatorDoorPlanRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        door_name="North Gate",
        source_entity_id="door_north",
        locked=True,
        required_flag="gate_unlocked",
        trigger="auto",
    )

    plan = build_creator_door_plan(request)
    payload = dict(plan.operations[0].payload)

    assert payload == {
        "source_scene": "forest",
        "destination_scene": "town",
        "destination_spawn_id": "north_gate_entry",
        "door_name": "North Gate",
        "source_entity_id": "door_north",
        "locked": True,
        "required_flag": "gate_unlocked",
        "trigger": "auto",
        "transition_behaviour": "SceneTransition",
        "scene_exit_listen_event": "",
        "interactable_event": "",
        "entity_require_flags": (),
    }


def test_creator_door_plan_import_does_not_require_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_plan import build_creator_door_plan; "
                "print(callable(build_creator_door_plan))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "True"


def test_package_import_still_does_not_import_renderer_module() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import engine.editor.creator_mode; "
                "print('engine.editor.creator_mode.creator_overlay_renderer' in sys.modules)"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"
