import json
from pathlib import Path

from engine.ai_ops import AIOps


def test_add_world_scene_and_links(tmp_path: Path):
    base = tmp_path
    world_path = base / "worlds" / "main_world.json"
    world_path.parent.mkdir(parents=True)
    world_path.write_text(
        json.dumps({"id": "main", "scenes": {}, "links": []}, indent=2),
        encoding="utf-8",
    )
    ops = AIOps(base)
    res = ops.apply_job(
        {
            "operations": [
                {
                    "type": "add_world_scene",
                    "world_path": str(world_path),
                    "scene_key": "village",
                    "path": "scenes/village.json",
                    "label": "Village",
                    "tags": ["hub"],
                },
                {
                    "type": "link_world_scenes",
                    "world_path": str(world_path),
                    "from_key": "village",
                    "to_key": "forest",
                    "via": "Door",
                    "bidirectional": False,
                },
                {
                    "type": "set_world_start",
                    "world_path": str(world_path),
                    "start_scene": "village",
                    "start_spawn": "gate",
                },
            ]
        }
    )
    assert res["ok"] is True
    data = json.loads(world_path.read_text(encoding="utf-8"))
    assert data["scenes"]["village"]["path"] == "scenes/village.json"
    assert any(link["from"] == "village" and link["to"] == "forest" for link in data["links"])
    assert data["start_scene"] == "village"
    assert data["start_spawn"] == "gate"


def test_add_update_delete_quest_definition(tmp_path: Path):
    quests_path = tmp_path / "quests.json"
    quests_path.write_text(json.dumps({"quests": {}}, indent=2), encoding="utf-8")
    ops = AIOps(tmp_path)
    job = {
        "operations": [
            {
                "type": "add_quest_definition",
                "quest_id": "intro",
                "quest": {"id": "intro", "title": "Intro Quest"},
                "quests_path": str(quests_path),
            },
            {
                "type": "update_quest_definition",
                "quest_id": "intro",
                "quest": {"description": "Meet the elder"},
                "quests_path": str(quests_path),
            },
        ]
    }
    res = ops.apply_job(job)
    assert res["ok"] is True
    payload = json.loads(quests_path.read_text(encoding="utf-8"))
    assert payload["quests"]["intro"]["title"] == "Intro Quest"
    assert payload["quests"]["intro"]["description"] == "Meet the elder"

    # delete
    res = ops.apply_job(
        {
            "operations": [
                {
                    "type": "delete_quest_definition",
                    "quest_id": "intro",
                    "quests_path": str(quests_path),
                }
            ]
        }
    )
    assert res["ok"] is True
    payload = json.loads(quests_path.read_text(encoding="utf-8"))
    assert "intro" not in payload.get("quests", {})
