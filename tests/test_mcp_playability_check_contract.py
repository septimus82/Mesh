"""Contract tests for the advisory ``playability_check`` MCP tool.

Builds scenes in a temp sandbox -- via the real authoring tools where possible,
and via direct JSON for the edge cases (camera-less player, ``prefab_id``
references, a tilemap-less ChaseTarget enemy) -- and asserts the advisory
verdicts. The check must never raise on valid-but-incomplete content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.mcp_server import tools

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFABS_PATH = REPO_ROOT / "assets" / "prefabs.json"


@pytest.fixture()
def sandbox(tmp_path) -> str:
    return str(tmp_path)


def _place(sandbox: str, scene_rel: str, prefab_name: str, x: float, y: float) -> str:
    result = tools.add_entity_from_prefab(
        scene_rel, prefab_name, x, y, prefab_path=str(PREFABS_PATH), root=sandbox
    )
    assert result["ok"], result
    return str(result["data"]["entity_name"])


def _write_scene(sandbox: str, name: str, scene: dict[str, Any]) -> str:
    (Path(sandbox) / name).write_text(json.dumps(scene), encoding="utf-8")
    return name


def test_good_scene_is_playable(sandbox: str) -> None:
    tools.create_scene("good", template="empty", root=sandbox)
    _place(sandbox, "good.json", "Player", 400.0, 300.0)
    _place(sandbox, "good.json", "Chaser Enemy", 600.0, 300.0)

    result = tools.playability_check("good.json", root=sandbox)

    assert result["ok"] is True, result
    assert result["warnings"] == [], result
    assert result["summary"]["has_player"] is True
    assert result["summary"]["player_has_camera"] is True
    assert result["summary"]["enemies_targeting_player"] >= 1


def test_player_without_enemy_warns(sandbox: str) -> None:
    tools.create_scene("lonely", template="empty", root=sandbox)
    _place(sandbox, "lonely.json", "Player", 400.0, 300.0)

    result = tools.playability_check("lonely.json", root=sandbox)

    assert result["ok"] is False, result
    assert result["summary"]["has_player"] is True
    assert any("enemy" in w.lower() for w in result["warnings"]), result


def test_player_without_camera_warns(sandbox: str) -> None:
    scene = {
        "name": "No Camera",
        "settings": {"tilemap": None},
        "entities": [
            {
                "name": "Player",
                "tag": "player",
                "behaviours": ["PlayerController"],
                "sprite": "assets/placeholder.png",
                "x": 100,
                "y": 100,
            },
            {
                "name": "Foe",
                "tag": "enemy",
                "behaviours": ["EnemyAI", "Health"],
                "behaviour_config": {"EnemyAI": {"target_tag": "player"}},
                "sprite": "assets/placeholder.png",
                "x": 300,
                "y": 100,
            },
        ],
    }
    _write_scene(sandbox, "no_camera.json", scene)

    result = tools.playability_check("no_camera.json", root=sandbox)

    assert result["ok"] is False, result
    assert result["summary"]["has_player"] is True
    assert result["summary"]["player_has_camera"] is False
    assert result["summary"]["enemies_targeting_player"] >= 1
    assert any("camerafollow" in w.lower() or "camera" in w.lower() for w in result["warnings"]), result


def test_missing_scene_returns_structured_not_raised(sandbox: str) -> None:
    result = tools.playability_check("does_not_exist.json", root=sandbox)
    assert result["ok"] is False
    assert "message" in result


def test_resolves_prefab_id_references(sandbox: str) -> None:
    """Hand-authored ``prefab_id`` entities must be seen via prefab resolution."""
    scene = {
        "name": "By Reference",
        "settings": {"tilemap": None},
        "entities": [
            {"name": "Player", "prefab_id": "player", "x": 100, "y": 100},
            {"name": "Foe", "prefab_id": "chaser_enemy", "x": 300, "y": 100},
        ],
    }
    _write_scene(sandbox, "by_ref.json", scene)

    result = tools.playability_check("by_ref.json", root=sandbox)

    assert result["summary"]["has_player"] is True, result
    assert result["summary"]["player_has_camera"] is True, result
    assert result["summary"]["enemies_targeting_player"] >= 1, result
    assert result["ok"] is True, result


def test_chasetarget_without_tilemap_advises_inert_chase(sandbox: str) -> None:
    scene = {
        "name": "Chase No Tilemap",
        "settings": {"tilemap": None},
        "entities": [
            {
                "name": "Player",
                "tag": "player",
                "behaviours": ["PlayerController", "CameraFollow"],
                "sprite": "assets/placeholder.png",
                "x": 100,
                "y": 100,
            },
            {
                "name": "Stalker",
                "tag": "enemy",
                "behaviours": ["ChaseTarget"],
                "behaviour_config": {"ChaseTarget": {"target_tag": "player"}},
                "sprite": "assets/placeholder.png",
                "x": 300,
                "y": 100,
            },
        ],
    }
    _write_scene(sandbox, "chase_no_tilemap.json", scene)

    result = tools.playability_check("chase_no_tilemap.json", root=sandbox)

    assert result["ok"] is False, result
    assert result["summary"]["enemies_targeting_player"] >= 1
    assert any("tilemap" in w.lower() for w in result["warnings"]), result
