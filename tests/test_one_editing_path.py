"""Milestone 13: lights, object removal and behaviour settings have one implementation.

Mesh Studio, the authoring API, MCP ``apply_ops`` (on Studio projects and on any other scene file) and the in-game
console's AI jobs all edit through ``project_ops``. The same request gives the same room, and is refused for the
same reason, whoever asks. AIOps keeps only its request shapes (``{"light": {...}}``, an object named by its name).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from engine import project_ops as ops
from engine.ai_ops import AIOps
from engine.mcp_server import tools
from engine.project_scaffold import create_project

pytestmark = pytest.mark.fast
ROOM = "packs/core_regions/scenes/start.json"


@pytest.fixture
def game(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _room(root: Path) -> dict:
    return json.loads((root / ROOM).read_text(encoding="utf-8"))


def _loose_copy(root: Path, tmp_path: Path) -> Path:
    """The same room as a plain scene file outside any Studio project (the AIOps path)."""
    loose = tmp_path / "loose"
    loose.mkdir()
    shutil.copy(root / ROOM, loose / "start.json")
    return loose


def test_a_light_comes_out_the_same_from_studio_ops_mcp_and_aiops(game: Path, tmp_path: Path) -> None:
    loose = _loose_copy(game, tmp_path)
    by_ops, _ = ops.add_light(_room(game), 100.4, 64, color="#ffddaa", radius=200)
    by_mcp = tools.apply_ops([{"type": "add_light", "scene_path": ROOM, "light": {"x": 100.4, "y": 64, "radius": 200}}],
                             root=str(game))
    assert by_mcp["ok"], by_mcp
    by_aiops = AIOps(loose).add_light("start.json", {"x": 100.4, "y": 64, "radius": 200})
    assert by_aiops.ok, by_aiops.message
    loose_room = json.loads((loose / "start.json").read_text(encoding="utf-8"))
    assert ops.lights(_room(game)) == ops.lights(by_ops) == ops.lights(loose_room)


def test_light_changes_are_validated_the_same_everywhere(game: Path, tmp_path: Path) -> None:
    loose = _loose_copy(game, tmp_path)
    aiops = AIOps(loose)
    assert aiops.add_light("start.json", {"x": 1, "y": 1, "mode": "hard"}).ok
    stored = json.loads((loose / "start.json").read_text(encoding="utf-8"))["lights"][0]
    assert stored["mode"] == "hard" and stored["color"] == "#ffddaa"
    bad = aiops.update_light("start.json", 0, {"radius": 3})
    assert not bad.ok and "Size" in bad.message, "too small: the same refusal as in Studio"
    unknown = aiops.update_light("start.json", 0, {"sparkle": 2})
    assert not unknown.ok and "'sparkle'" in unknown.message, unknown.message
    lamp = aiops.update_light("start.json", 0, {"intensity": 2, "elevation": 80})  # an HD-2D lamp's (Stage 6A)
    assert lamp.ok and lamp.data["light"]["intensity"] == 2.0 and lamp.data["light"]["elevation"] == 80.0
    assert not aiops.update_light("start.json", 0, {"elevation": -1}).ok, "validated like every other setting"
    missing = aiops.delete_light("start.json", 5)
    assert not missing.ok
    with pytest.raises(ops.OpError):
        ops.set_light(_room(game), 0, radius=3)


def test_objects_are_removed_and_given_behaviours_by_id_or_unique_name(game: Path, tmp_path: Path) -> None:
    loose = _loose_copy(game, tmp_path)
    aiops = AIOps(loose)
    room = json.loads((loose / "start.json").read_text(encoding="utf-8"))
    room["entities"] += [{"id": "a", "name": "Crate", "x": 0, "y": 0}, {"name": "Barrel", "x": 32, "y": 0},
                         {"id": "c1", "name": "Twin", "x": 0, "y": 32}, {"id": "c2", "name": "Twin", "x": 32, "y": 32}]
    (loose / "start.json").write_text(json.dumps(room), encoding="utf-8")
    assert aiops.set_behaviour_params("start.json", "Barrel", "Patrol", {"patrol_speed": 30}).ok
    barrel = next(e for e in json.loads((loose / "start.json").read_text(encoding="utf-8"))["entities"]
                  if e.get("name") == "Barrel")
    assert barrel["id"] and barrel["behaviour_config"]["Patrol"]["patrol_speed"] == 30.0, "an older id-less object gets an id"
    refused = aiops.set_behaviour_params("start.json", "Crate", "Patrol", {"no_such_setting": 1})
    assert not refused.ok and "no setting called 'no_such_setting'" in refused.message
    twin = aiops.delete_entity("start.json", "Twin")
    assert not twin.ok and "use an id" in twin.message
    assert aiops.delete_entity("start.json", "c1").ok and aiops.delete_entity("start.json", "Crate").ok
    names = [e.get("name") for e in json.loads((loose / "start.json").read_text(encoding="utf-8"))["entities"]]
    assert "Crate" not in names and names.count("Twin") == 1


def test_a_partial_dialogue_patch_keeps_the_rest(game: Path, tmp_path: Path) -> None:
    loose = _loose_copy(game, tmp_path)
    aiops = AIOps(loose)
    room = json.loads((loose / "start.json").read_text(encoding="utf-8"))
    room["entities"].append({"id": "g", "name": "Guide", "x": 0, "y": 0, "behaviours": ["Dialogue"],
                             "behaviour_config": {"Dialogue": {"dialogue": {"start": "hello", "speaker": "Guide"}}}})
    (loose / "start.json").write_text(json.dumps(room), encoding="utf-8")
    assert aiops.edit_dialogue("start.json", "Guide", {"start": "welcome"}).ok
    guide = next(e for e in json.loads((loose / "start.json").read_text(encoding="utf-8"))["entities"] if e.get("id") == "g")
    assert guide["behaviour_config"]["Dialogue"]["dialogue"] == {"start": "welcome", "speaker": "Guide"}


def test_the_one_call_mcp_add_tool_uses_the_shared_path_on_a_studio_project(game: Path) -> None:
    result = tools.add_entity_from_prefab(ROOM, "person", 96, 96, root=str(game))
    assert result["ok"], result
    placed = [e for e in _room(game)["entities"] if e.get("name") == "Person"]
    assert len(placed) == 1 and placed[0]["id"] and placed[0]["x"] == 96.0, "placed by place_prefab, with an id"
