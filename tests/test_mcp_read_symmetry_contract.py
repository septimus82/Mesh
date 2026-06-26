"""Contract tests for the MCP read-symmetry tools.

``read_dialogue`` / ``read_world`` / ``read_tilemap`` are the read counterparts to
the dialogue / world / tilemap write ops, each keyed on the SAME identity its
write op uses (entity name / world_path / scene_path). Exercised against real
repo content where it exists, plus a tmp sandbox for the empty/missing cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.mcp_server import tools

ROOT = "."


def _write_scene(sandbox: str, name: str, scene: dict[str, Any]) -> str:
    (Path(sandbox) / name).write_text(json.dumps(scene), encoding="utf-8")
    return name


# --------------------------------------------------------------- read_dialogue
def test_read_dialogue_returns_speaker_and_lines() -> None:
    result = tools.read_dialogue("scenes/showcase_dungeon.json", "Dungeon Boss", ROOT)
    assert result["ok"] is True, result
    assert result["has_dialogue"] is True, result
    dialogue = result["dialogue"]
    assert isinstance(dialogue, dict)
    assert dialogue.get("speaker") == "Guard", dialogue
    assert isinstance(dialogue.get("lines"), list) and dialogue["lines"], dialogue


def test_read_dialogue_missing_entity_is_structured() -> None:
    result = tools.read_dialogue("scenes/showcase_dungeon.json", "Nope_Missing", ROOT)
    assert result["ok"] is False
    assert "message" in result


def test_read_dialogue_missing_scene_is_structured() -> None:
    result = tools.read_dialogue("scenes/does_not_exist.json", "Whoever", ROOT)
    assert result["ok"] is False
    assert "message" in result


def test_read_dialogue_entity_without_dialogue(tmp_path) -> None:
    scene = {"name": "S", "entities": [{"name": "Mute", "behaviours": []}]}
    name = _write_scene(str(tmp_path), "mute.json", scene)
    result = tools.read_dialogue(name, "Mute", str(tmp_path))
    assert result["ok"] is True
    assert result["has_dialogue"] is False
    assert result["dialogue"] is None


# ------------------------------------------------------------------ read_world
def test_read_world_returns_graph() -> None:
    result = tools.read_world("worlds/main_world.json", ROOT)
    assert result["ok"] is True, result
    assert result["start_scene"] == "door_field", result
    assert result["start_spawn"] == "default", result
    assert result["scenes"], "expected a non-empty scenes list"
    sample = result["scenes"][0]
    assert set(sample) == {"key", "path", "label", "tags"}, sample
    assert isinstance(result["links"], list) and result["links"]


def test_read_world_defaults_to_main_world() -> None:
    result = tools.read_world(None, ROOT)
    assert result["ok"] is True
    assert result["world_path"] == "worlds/main_world.json"


def test_read_world_missing_is_structured(tmp_path) -> None:
    result = tools.read_world("worlds/nope.json", str(tmp_path))
    assert result["ok"] is False
    assert "message" in result


# ---------------------------------------------------------------- read_tilemap
def test_read_tilemap_returns_layers_and_tiles() -> None:
    result = tools.read_tilemap("scenes/combat_tutorial_demo.json", ROOT)
    assert result["ok"] is True, result
    assert result["has_tilemap"] is True, result
    assert result["collision_layer_id"] == "platforms", result
    layer_names = {layer["name"] for layer in result["layers"]}
    assert {"ground", "platforms"} <= layer_names, result["layers"]
    for layer in result["layers"]:
        assert "z" in layer
    assert "platforms" in result["tiles"], result["tiles"].keys()
    assert isinstance(result["tiles"]["platforms"], list) and result["tiles"]["platforms"]


def test_read_tilemap_no_tilemap_is_not_error() -> None:
    result = tools.read_tilemap("scenes/combat_vignette_01.json", ROOT)
    assert result["ok"] is True, result
    assert result["has_tilemap"] is False, result


def test_read_tilemap_missing_scene_is_structured() -> None:
    result = tools.read_tilemap("scenes/does_not_exist.json", ROOT)
    assert result["ok"] is False
    assert "message" in result


# --------------------------------------------------------------- symmetry guard
def test_read_tools_keyed_on_same_identity_as_writes() -> None:
    # read_dialogue is keyed on entity name -- the identity inspect_entity uses.
    inspected = tools.inspect_entity("scenes/showcase_dungeon.json", "Dungeon Boss", ROOT)
    assert inspected["ok"] is True
    assert inspected["name"] == "Dungeon Boss"
    dialogue = tools.read_dialogue("scenes/showcase_dungeon.json", inspected["name"], ROOT)
    assert dialogue["ok"] is True and dialogue["entity_id"] == "Dungeon Boss"

    # read_world default world_path matches the AIOps write default.
    from engine.ai_ops import AIOps

    default_world = AIOps(base_dir=".")._world_path(None)
    assert default_world.as_posix().endswith("worlds/main_world.json")
    assert tools.read_world(None, ROOT)["world_path"] == "worlds/main_world.json"

    # read_tilemap is keyed on scene_path (same identity paint_tiles uses).
    scene_path = "scenes/combat_tutorial_demo.json"
    assert tools.read_tilemap(scene_path, ROOT)["scene_path"] == scene_path
