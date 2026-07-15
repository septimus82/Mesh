from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.editor.creator_mode import (
    build_creator_door_live_ops,
    build_creator_door_request_from_selection,
    build_creator_door_workflow,
)

pytestmark = pytest.mark.fast


def test_selected_dict_form_scene_transition_builds_canonical_request() -> None:
    request = build_creator_door_request_from_selection(
        {
            "id": "door_field_fielddoor_240_120_0_0",
            "name": "FieldDoor",
            "behaviours": [{"type": "SceneTransition", "params": {"target_scene": "old"}}],
            "behaviour_config": {
                "SceneTransition": {
                    "target_scene": "scenes/door_interior.json",
                    "spawn_id": "interior_entry",
                }
            },
        },
        source_scene="scenes/door_field.json",
    )

    assert request is not None
    assert request.transition_behaviour == "SceneTransition"
    assert request.source_scene == "scenes/door_field.json"
    assert request.destination_scene == "scenes/door_interior.json"
    assert request.destination_spawn_id == "interior_entry"
    assert request.trigger == "interact"


def test_config_only_door_is_visible_but_not_stageable() -> None:
    request = build_creator_door_request_from_selection(
        {
            "id": "door_north",
            "name": "North Door",
            "behaviour_config": {"SceneTransition": {"target_scene": "scenes/next.json"}},
        },
        source_scene="scenes/current.json",
    )

    assert request is not None
    assert request.transition_behaviour == ""
    workflow = build_creator_door_workflow(request)

    assert workflow.plan.ok is False
    assert "Selected door has no attached transition behaviour." in workflow.plan.errors


def test_scene_transition_live_op_uses_canonical_params_without_legacy_keys() -> None:
    request = build_creator_door_request_from_selection(
        {
            "id": "door_north",
            "name": "North Door",
            "behaviours": ["SceneTransition"],
            "behaviour_config": {
                "SceneTransition": {
                    "target_scene": "scenes/next.json",
                    "spawn_id": "entry",
                }
            },
        },
        source_scene="scenes/current.json",
    )
    assert request is not None

    result = build_creator_door_live_ops(build_creator_door_workflow(request))

    assert result.ok is True
    op = result.ops[0]
    assert op["behaviour_name"] == "SceneTransition"
    assert op["params"] == {
        "target_scene": "scenes/next.json",
        "spawn_id": "entry",
        "allow_interact": True,
        "trigger_on_touch": False,
    }
    assert "target_spawn" not in op["params"]
    assert "trigger" not in op["params"]


def test_existing_two_scene_door_pair_uses_canonical_scene_transition_targets() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    field = _scene(repo_root, "scenes/door_field.json")
    interior = _scene(repo_root, "scenes/door_interior.json")

    field_door = _entity(field, "FieldDoor")
    interior_door = _entity(interior, "InteriorDoor")

    assert field_door["behaviour_config"]["SceneTransition"] == {
        "spawn_id": "interior_entry",
        "target_scene": "scenes/door_interior.json",
    }
    assert interior_door["behaviour_config"]["SceneTransition"] == {
        "spawn_id": "field_return",
        "target_scene": "scenes/door_field.json",
    }


def test_world_links_use_field_and_interior_door_names_for_two_scene_pair() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    world = _scene(repo_root, "worlds/main_world.json")
    links = {
        (link.get("from"), link.get("to")): link.get("via")
        for link in world.get("links", [])
        if isinstance(link, dict)
    }

    assert links[("door_field", "door_interior")] == "FieldDoor"
    assert links[("door_interior", "door_field")] == "InteriorDoor"


def _scene(repo_root: Path, path: str) -> dict:
    payload = json.loads((repo_root / path).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _entity(scene: dict, name: str) -> dict:
    for entity in scene.get("entities", []):
        if isinstance(entity, dict) and entity.get("name") == name:
            return entity
    raise AssertionError(f"Missing entity {name}")
