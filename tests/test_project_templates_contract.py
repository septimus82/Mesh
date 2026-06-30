"""Tests for Project Templates logic."""

import json

from engine.project_scaffold import create_project
from engine.project_templates import Template, list_templates


def test_list_templates_stable():
    """Ensure template list returns expected items."""
    templates = list_templates()
    ids = [t.id for t in templates]
    assert "blank" in ids
    assert "lighting_playground" in ids
    assert "demo_slice" in ids

    # Check structure
    iso = templates[0]
    assert isinstance(iso, Template)
    assert iso.id
    assert iso.title
    assert iso.description

def test_apply_template_blank(tmp_path):
    """Test blank template application."""
    root = tmp_path / "blank_proj"
    create_project(root, "BlankTest", template_id="blank")

    start_scene = root / "packs/core_regions/scenes/start.json"
    assert start_scene.exists()

    data = json.loads(start_scene.read_text("utf-8"))
    assert data["name"] == "Start Scene"
    players = [entity for entity in data.get("entities", []) if entity.get("tag") == "player"]
    assert len(players) == 1

def test_apply_template_lighting_playground(tmp_path):
    """Test lighting playground template."""
    root = tmp_path / "light_proj"
    create_project(root, "LightTest", template_id="lighting_playground")

    start_scene = root / "packs/core_regions/scenes/start.json"
    data = json.loads(start_scene.read_text("utf-8"))

    # Check for lights
    assert "lights" in data["layers"]
    assert len(data["layers"]["lights"]) > 0

    # Check config
    config = json.loads((root / "config.json").read_text("utf-8"))
    assert config["lighting_enabled"] is True

def test_apply_template_demo_slice(tmp_path):
    """Test demo slice template."""
    root = tmp_path / "demo_proj"
    create_project(root, "DemoTest", template_id="demo_slice")

    # Check quest
    quest_file = root / "packs/core_regions/quests/intro.json"
    assert quest_file.exists()

    # Check start scene has NPC and interaction
    start_scene = root / "packs/core_regions/scenes/start.json"
    data = json.loads(start_scene.read_text("utf-8"))

    entities = data["layers"]["entities"]
    npcs = [e for e in entities if e.get("type") == "npc"]
    assert len(npcs) > 0
    assert npcs[0]["interaction"]["quest_trigger"] == "intro_quest"
