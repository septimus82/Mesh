from __future__ import annotations

import json
from pathlib import Path


def _player_entities(scene_payload: dict) -> list[dict]:
    out: list[dict] = []
    for ent in scene_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        if ent.get("prefab_id") == "player":
            out.append(ent)
    return out


def test_guard_demo_scenes_have_single_player_instance() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for scene_path in [
        "scenes/guard_patrol_chase_demo.json",
        "scenes/guard_patrol_chase_duo_demo.json",
    ]:
        payload = json.loads((repo_root / scene_path).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        players = _player_entities(payload)
        assert len(players) == 1
        assert players[0].get("mesh_name") == "Player"

