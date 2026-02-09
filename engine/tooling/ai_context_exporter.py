"""Exports a compact, AI-friendly snapshot of scenes."""

import json
from pathlib import Path
from typing import Any, Dict, List

from engine.paths import resolve_path
from engine.scene_loader import SceneLoader


def export_ai_context(scene_paths: List[Path]) -> Dict[str, Any]:
    """
    Loads the specified scenes and produces a compact JSON summary suitable for AI context.
    """
    loader = SceneLoader()

    # Load quest definitions to resolve titles
    quest_definitions = _load_quest_definitions()

    scenes_summary = []

    for path in scene_paths:
        if not path.exists():
            raise FileNotFoundError(f"Scene file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                raw_scene = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in scene file {path}: {e}")

        # Apply defaults to ensure we have a consistent view
        scene_data = loader.apply_scene_defaults(raw_scene)

        summary = _summarize_scene(path, scene_data, quest_definitions)
        scenes_summary.append(summary)

    return {"scenes": scenes_summary}

def _load_quest_definitions() -> Dict[str, str]:
    """
    Loads quest definitions and returns a map of quest_id -> quest_title.
    """
    definitions: Dict[str, str] = {}

    # Core quests
    core_quests_path = resolve_path("assets/data/quests.json")
    if core_quests_path.exists():
        try:
            with core_quests_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                quests = data.get("quests", []) if isinstance(data, dict) else data
                if isinstance(quests, list):
                    for q in quests:
                        if not isinstance(q, dict):
                            continue
                        qid = q.get("id")
                        if not isinstance(qid, str) or not qid:
                            continue
                        title = q.get("title")
                        if not isinstance(title, str) or not title.strip():
                            title = qid
                        definitions[qid] = title
        except Exception:
            pass # Ignore errors in quest loading for context export

    # Core quests are usually sufficient for context; pack quests can be added later if needed.

    return definitions

def _summarize_scene(path: Path, data: Dict[str, Any], quest_defs: Dict[str, str]) -> Dict[str, Any]:
    """
    Summarizes a single scene.
    """
    scene_id = path.stem

    # Determine kind
    kind = "unknown"
    # Heuristic based on template or tags if available, or filename
    if "hub" in scene_id or "overworld" in scene_id:
        kind = "overworld"
    elif "dungeon" in scene_id:
        kind = "dungeon"
    elif "interior" in scene_id:
        kind = "interior"

    # Collect entities
    npcs = []
    transitions = []
    quests = []

    entities = data.get("entities", [])

    for entity in entities:
        # NPCs
        if entity.get("tag") == "npc" or "Dialogue" in entity.get("behaviours", []):
            npc_info = {
                "name": entity.get("name", "Unknown NPC"),
                "position": {"x": entity.get("x", 0), "y": entity.get("y", 0)}
            }

            if "id" in entity:
                npc_info["id"] = entity["id"]

            # Role/Tags
            tags = entity.get("tags", [])
            if entity.get("tag"):
                tags.append(entity["tag"])
            # Deduplicate
            npc_info["tags"] = list(set(tags))

            # Try to infer role from tags or name
            role = None
            for t in npc_info["tags"]:
                if t in ["guard", "merchant", "quest_giver"]:
                    role = t
                    break
            if role:
                npc_info["role"] = role

            # Dialogue
            dialogue = entity.get("dialogue", {})
            if "id" in dialogue:
                npc_info["dialogue_id"] = dialogue["id"]

            npcs.append(npc_info)

        # Transitions
        if "SceneTransition" in entity.get("behaviours", []):
            config = entity.get("behaviour_config", {}).get("SceneTransition", {})
            target = config.get("target_scene")
            if target:
                trans_info = {
                    "to_scene": target,
                    "kind": "unknown" # Could infer from sprite or name
                }
                if "door" in entity.get("name", "").lower():
                    trans_info["kind"] = "door"
                elif "stairs" in entity.get("name", "").lower():
                    trans_info["kind"] = "stairs"

                transitions.append(trans_info)

        # Quests (via QuestGiver behaviour or similar hooks)
        # Currently Mesh seems to link quests via dialogue or specific behaviours
        # We can check for "QuestGiver" behaviour if it exists, or check dialogue hooks?
        # The user prompt mentions "quest_hook_count".
        # Let's check behaviour_config for quest references.
        b_config = entity.get("behaviour_config", {})
        if "QuestGiver" in entity.get("behaviours", []):
            q_config = b_config.get("QuestGiver", {})
            q_id = q_config.get("quest_id")
            if q_id:
                quests.append({
                    "id": q_id,
                    "title": quest_defs.get(q_id, q_id),
                    "status": "hook_only" # We don't know runtime status
                })

    # Deduplicate quests
    unique_quests = {q["id"]: q for q in quests}.values()

    return {
        "scene_id": scene_id,
        "kind": kind,
        "summary": {
            "npc_count": len(npcs),
            "transition_count": len(transitions),
            "quest_hook_count": len(unique_quests)
        },
        "npcs": npcs,
        "transitions": transitions,
        "quests": list(unique_quests)
    }
