from __future__ import annotations

import re
from typing import Any

ALLOWED_AI_ACTIONS: dict[str, dict[str, Any]] = {
    "init_pack": {
        "description": "Initialize a new content pack under packs/.",
        "required_args": {
            "path": "string (e.g., 'packs/my_pack')",
            "id": "string (pack id)"
        },
        "optional_args": {
            "wip": "bool (mark pack as WIP)"
        },
    },
    "create_scene": {
        "description": "Create a new scene file from a template.",
        "required_args": {
            "path": "string (e.g., 'scenes/my_scene.json')",
            "template": "string (e.g., 'empty', 'dungeon', 'hub')"
        },
        "optional_args": {
            "with_boss": "bool",
            "region_prefix": "string",
            "scene_kind": "string",
            "region_template": "string",
            "region_theme": "string",
            "encounter_set": "string",
            "difficulty": "string",
            "perks": "list[string]",
        }
    },
    "add_npc": {
        "description": "Add an NPC to an existing scene.",
        "required_args": {
            "scene_path": "string (path to scene file)",
            "role": "string (e.g., 'guard', 'merchant', 'quest_giver')"
        },
        "optional_args": {
            "x": "integer",
            "y": "integer",
            "name": "string (NPC name)",
            "quest_id": "string (Quest ID to offer)",
            "tags": "list[string] (e.g. ['guard', 'important'])"
        }
    },
    "add_transition": {
        "description": "Add a transition trigger to a scene.",
        "required_args": {
            "scene_path": "string (path to source scene)",
            "target_scene": "string (path to target scene)",
            "x": "integer",
            "y": "integer"
        }
    },
    "add_puzzle_switch_door": {
        "description": "Add a switch-door puzzle to a scene.",
        "required_args": {
            "scene_path": "string (path to scene file)",
            "switch": "object (x, y)",
            "door": "object (x, y)"
        },
        "optional_args": {
            "reward": "object",
            "id_prefix": "string",
            "event_id": "string",
        }
    },
    "create_quest": {
        "description": "Add a new quest definition.",
        "required_args": {
            "path": "string (path to quests.json)",
            "id": "string (unique ID)",
            "title": "string",
            "type": "string (e.g., 'main', 'side')"
        }
    },
    "add_npc_dialogue": {
        "description": "Set dialogue for an NPC in a scene.",
        "required_args": {
            "scene_path": "string (path to scene file)",
            "npc_name": "string (Name of the NPC)",
            "lines": "list[string] (Dialogue lines)"
        },
        "optional_args": {
            "dialogue_id": "string (Optional ID for the dialogue)",
            "speaker_alias": "string (Optional speaker name override)"
        }
    },
    "wire_world": {
        "description": "Register a scene in a world, and optionally link it from another scene id.",
        "required_args": {
            "world_path": "string (path to world file)",
            "scene_id": "string (scene id in world)",
            "scene_path": "string (path to scene file)"
        },
        "optional_args": {
            "link_from": "string (scene id to link from)"
        },
    },
    "auto_wire_transitions": {
        "description": "Auto-generate transitions between linked scenes in a world.",
        "required_args": {
            "world_path": "string (path to world file)"
        },
    },
    "polish_scene": {
        "description": "Apply compact/polish pass to a scene.",
        "required_args": {
            "path": "string (path to scene file)"
        },
        "optional_args": {
            "compact_only": "bool"
        },
    },
    "validate": {
        "description": "Validate a scene or world.",
        "required_args": {
            "scene_path": "string (path to scene file)"
        },
        "optional_args": {
            "check_refs": "bool"
        },
    }
}

_SLUG_SAFE_RE = re.compile(r"[^a-z0-9]+")


def _slugify_scene_stem(prompt: str) -> str:
    text = str(prompt or "").strip().lower()
    text = _SLUG_SAFE_RE.sub("_", text).strip("_")
    if not text:
        return "ai_scene"
    return text[:32].strip("_") or "ai_scene"


def generate_plan_skeleton(prompt: str, *, allow_todos: bool = False) -> dict[str, Any]:
    """
    Generate a skeleton AI plan based on the prompt.

    Default behavior is strict: avoid placeholder tokens (TODO/TBD) in any string fields.
    Use allow_todos=True to opt into the older placeholder-heavy skeleton.
    """
    if allow_todos:
        return {
            "wizard": "ai-generated",
            "version": 1,
            "inputs": {
                "prompt": prompt,
                "target_pack": "TODO: pack_id_here (optional)",
            },
            "actions": [
                {
                    "type": "create_scene",
                    "args": {
                        "path": "scenes/TODO_scene_name.json",
                        "template": "empty",
                    },
                    "description": "TODO: Create a new scene based on the prompt",
                },
                {
                    "type": "add_npc",
                    "args": {
                        "scene_path": "scenes/TODO_scene_name.json",
                        "role": "guard",
                        "x": 10,
                        "y": 10,
                    },
                    "description": "TODO: Add an NPC",
                },
                {
                    "type": "add_npc_dialogue",
                    "args": {
                        "scene_path": "scenes/TODO_scene_name.json",
                        "npc_name": "TODO_npc_name",
                        "lines": [
                            "TODO: dialogue line 1",
                            "TODO: dialogue line 2",
                        ],
                    },
                    "description": "TODO: Add dialogue to NPC",
                },
            ],
        }

    stem = _slugify_scene_stem(prompt)
    scene_path = f"scenes/{stem}.json"
    npc_name = "Guide"

    return {
        "wizard": "ai-generated",
        "version": 1,
        "inputs": {
            "prompt": str(prompt or ""),
        },
        "actions": [
            {
                "type": "create_scene",
                "args": {
                    "path": scene_path,
                    "template": "empty",
                },
                "description": "Create a new scene for the prompt.",
            },
            {
                "type": "add_npc",
                "args": {
                    "scene_path": scene_path,
                    "role": "quest_giver",
                    "name": npc_name,
                    "x": 160,
                    "y": 120,
                },
                "description": "Add a guide NPC to the new scene.",
            },
            {
                "type": "add_npc_dialogue",
                "args": {
                    "scene_path": scene_path,
                    "npc_name": npc_name,
                    "lines": [
                        "Welcome!",
                        "Tell me what you want to build next.",
                    ],
                },
                "description": "Add initial dialogue for the guide NPC.",
            },
        ],
    }

def generate_ai_schema() -> dict[str, Any]:
    """Generate a simplified schema for AI authoring."""
    return {
        "version": 1,
        "description": "Simplified Plan Schema for AI Authoring",
        "allowed_actions": ALLOWED_AI_ACTIONS
    }
