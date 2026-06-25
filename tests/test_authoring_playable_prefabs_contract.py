"""Contract test for authoring-playable prefabs (player fix + chaser enemy).

Exercises the REAL AI authoring path (``engine.mcp_server.tools``, which wraps
``engine.ai_ops.AIOps``) in a temporary sandbox to prove that:

* placing the ``player`` prefab yields a player with ``CameraFollow`` and the
  runtime tag ``"player"`` (so the camera follows it and EnemyAI/ChaseTarget can
  target it), and
* placing ``chaser_enemy`` yields an ``EnemyAI`` + ``Health`` enemy tagged
  ``"enemy"`` whose ``EnemyAI.target_tag`` is ``"player"`` (so it can target the
  placed player).

It also guards the prefab *source* so the player fix can't silently regress, and
asserts the prefab file still passes :class:`PrefabValidator`.

The placed entity's ``tag`` is the value the scene-load path assigns to
``sprite.mesh_tag`` (``engine/scene_controller_parts/entity_factory.py:101``),
which is what the enemy behaviours match against -- so asserting it on the
authored entity is equivalent to asserting the resolved runtime tag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from engine.mcp_server import tools
from engine.validators.prefab_validator import PrefabValidator

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFABS_PATH = REPO_ROOT / "assets" / "prefabs.json"


def _load_prefabs() -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", json.loads(PREFABS_PATH.read_text(encoding="utf-8")))


def _prefab_by_id(prefab_id: str) -> dict:
    for entry in _load_prefabs():
        if isinstance(entry, dict) and entry.get("id") == prefab_id:
            return entry
    raise AssertionError(f"prefab '{prefab_id}' not found in {PREFABS_PATH}")


@pytest.fixture()
def sandbox(tmp_path) -> str:
    return str(tmp_path)


def _place(sandbox: str, scene_rel: str, prefab_name: str, x: float, y: float) -> str:
    result = tools.add_entity_from_prefab(
        scene_rel,
        prefab_name,
        x,
        y,
        prefab_path=str(PREFABS_PATH),
        root=sandbox,
    )
    assert result["ok"], result
    return str(result["data"]["entity_name"])


def test_player_prefab_gains_camera_and_tag_via_ai_path(sandbox: str) -> None:
    create = tools.create_scene("playable", template="empty", root=sandbox)
    assert create["ok"], create

    name = _place(sandbox, "playable.json", "Player", 400.0, 300.0)
    info = tools.inspect_entity("playable.json", name, root=sandbox)

    assert info["ok"], info
    assert "PlayerController" in info["behaviours"], info
    assert "CameraFollow" in info["behaviours"], info
    assert info["tag"] == "player", info


def test_chaser_enemy_targets_player_via_ai_path(sandbox: str) -> None:
    tools.create_scene("playable", template="empty", root=sandbox)
    _place(sandbox, "playable.json", "Player", 400.0, 300.0)

    name = _place(sandbox, "playable.json", "Chaser Enemy", 600.0, 300.0)
    info = tools.inspect_entity("playable.json", name, root=sandbox)

    assert info["ok"], info
    assert "EnemyAI" in info["behaviours"], info
    assert "Health" in info["behaviours"], info
    assert info["tag"] == "enemy", info
    enemy_cfg = info["behaviour_config"].get("EnemyAI", {})
    assert enemy_cfg.get("target_tag") == "player", info


def test_player_prefab_source_has_camera_and_tag() -> None:
    """Regression guard: the player prefab entity block must keep these."""
    entity = _prefab_by_id("player")["entity"]
    assert "PlayerController" in entity.get("behaviours", []), entity
    assert "CameraFollow" in entity.get("behaviours", []), entity
    assert entity.get("tag") == "player", entity


def test_chaser_enemy_prefab_source_shape() -> None:
    entity = _prefab_by_id("chaser_enemy")["entity"]
    assert entity.get("behaviours") == ["EnemyAI", "Health"], entity
    assert entity.get("tag") == "enemy", entity
    config = entity.get("behaviour_config", {})
    assert config["Health"]["max_hp"] == 10, entity
    assert config["EnemyAI"]["target_tag"] == "player", entity


def test_prefab_file_validates_clean() -> None:
    validator = PrefabValidator()
    ok = validator.validate_path(str(PREFABS_PATH))
    assert ok, validator.errors
    assert not validator.errors, validator.errors
