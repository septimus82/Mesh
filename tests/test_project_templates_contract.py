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
    assert "demo_slice" not in ids  # retired (#656): a pre-schema scene that couldn't start

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
    # One player for the whole game: the room says where it starts, the project's "player" prefab what it is.
    players = [entity for entity in data.get("entities", []) if entity.get("prefab_id") == "player"]
    assert len(players) == 1 and set(players[0]) == {"id", "x", "y", "prefab_id"}
    prefabs = json.loads((root / "assets/prefabs.json").read_text("utf-8"))
    assert next(p for p in prefabs if p["id"] == "player")["entity"]["tag"] == "player"

def test_apply_template_lighting_playground(tmp_path):
    """The lighting playground in the current room format (#656): lit, two lamps, a wall, the shared player."""
    from engine.scene_loader import SceneLoader

    root = tmp_path / "light_proj"
    create_project(root, "LightTest", template_id="lighting_playground")

    start_scene = root / "packs/core_regions/scenes/start.json"
    data = json.loads(start_scene.read_text("utf-8"))
    assert "layers" not in data or isinstance(data["layers"], list)
    assert len(data["lights"]) == 2
    assert data["settings"]["lighting_enabled"] is True
    assert any(e.get("prefab_id") == "player" for e in data["entities"])
    assert not SceneLoader().validate_scene_file(str(start_scene)).errors

    config = json.loads((root / "config.json").read_text("utf-8"))
    assert config["lighting_enabled"] is True
