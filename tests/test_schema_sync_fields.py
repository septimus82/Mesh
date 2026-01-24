import pytest
from engine.behaviours.dialogue import Dialogue
from engine.behaviours.scene_transition import SceneTransition
from engine.behaviours.patrol import PatrolBehaviour
from engine.behaviours.registry import get_behaviour_info

def test_dialogue_schema_has_role():
    info = get_behaviour_info("Dialogue")
    field_names = [f["name"] for f in info.config_fields]
    assert "role" in field_names, "Dialogue behaviour must have 'role' field"

def test_scene_transition_schema_has_spawn_point():
    info = get_behaviour_info("SceneTransition")
    field_names = [f["name"] for f in info.config_fields]
    assert "spawn_point" in field_names, "SceneTransition behaviour must have 'spawn_point' field"

def test_patrol_schema_has_aliases():
    info = get_behaviour_info("Patrol")
    field_names = [f["name"] for f in info.config_fields]
    assert "points" in field_names, "Patrol behaviour must have 'points' alias"
    assert "speed" in field_names, "Patrol behaviour must have 'speed' alias"
