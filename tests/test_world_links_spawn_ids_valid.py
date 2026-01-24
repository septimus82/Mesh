from __future__ import annotations

import json
from pathlib import Path


def _scene_spawn_ids(scene_payload: dict) -> set[str]:
    ids: set[str] = set()
    for ent in scene_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        if ent.get("tag") != "spawn_point":
            continue
        spawn_id = ent.get("spawn_id")
        if isinstance(spawn_id, str) and spawn_id.strip():
            ids.add(spawn_id.strip())
    return ids


def _find_transition_entity(scene_payload: dict, *, via: str) -> dict | None:
    for ent in scene_payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        if ent.get("name") != via:
            continue
        return ent
    return None


def test_world_links_spawn_ids_valid() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    world = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))
    scenes_map = world["scenes"]
    links = world["links"]

    errors: list[str] = []

    for link in sorted(links, key=lambda l: (str(l.get("from") or ""), str(l.get("to") or ""), str(l.get("via") or ""))):
        if not isinstance(link, dict):
            continue
        via = link.get("via")
        if not isinstance(via, str) or not via.strip():
            continue
        from_key = str(link.get("from") or "")
        to_key = str(link.get("to") or "")
        if from_key not in scenes_map or to_key not in scenes_map:
            continue
        from_path = str(scenes_map[from_key].get("path") or "")
        to_path = str(scenes_map[to_key].get("path") or "")
        if not from_path or not to_path:
            continue

        from_scene_file = repo_root / Path(from_path.replace("\\", "/"))
        to_scene_file = repo_root / Path(to_path.replace("\\", "/"))
        if not from_scene_file.exists():
            from_path_display = from_path.replace("\\", "/")
            errors.append(f"missing_scene from={from_key} path={from_path_display}")
            continue
        if not to_scene_file.exists():
            to_path_display = to_path.replace("\\", "/")
            errors.append(f"missing_scene to={to_key} path={to_path_display}")
            continue

        from_scene = json.loads(from_scene_file.read_text(encoding="utf-8"))
        to_scene = json.loads(to_scene_file.read_text(encoding="utf-8"))
        if not isinstance(from_scene, dict) or not isinstance(to_scene, dict):
            continue

        ent = _find_transition_entity(from_scene, via=via.strip())
        if ent is None:
            # Some world links are conceptual (e.g., menu routing) and not backed by a SceneTransition entity.
            continue
        cfg_root = ent.get("behaviour_config")
        cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
        if not isinstance(cfg, dict):
            continue
        spawn_id = cfg.get("spawn_point") or cfg.get("spawn_id") or ""
        spawn_id = str(spawn_id or "").strip()
        if not spawn_id or spawn_id == "default":
            continue

        spawn_ids = _scene_spawn_ids(to_scene)
        if spawn_id not in spawn_ids:
            to_path_display = to_path.replace("\\", "/")
            errors.append(
                f"missing_spawn_id target_scene={to_path_display} spawn_id={spawn_id} (via {via})",
            )

    assert errors == []
