import argparse
import sys
from pathlib import Path
from typing import Any

from engine import json_io
from engine.tooling import ai_plan_command
from engine.tooling.plan_linter import ACTION_SCHEMAS

# Metadata registry for augmenting linter schema with descriptions and types
METADATA = {
    "init_pack": {
        "description": "Initialize a new content pack",
        "arg_types": {"id": "string", "path": "string", "wip": "boolean"},
        "defaults": {"wip": True}
    },
    "create_scene": {
        "description": "Create a new scene from a template",
        "arg_types": {"path": "string", "template": "string"},
        "choices": {"template": ["empty", "topdown", "dialogue-playground"]}
    },
    "add_npc": {
        "description": "Add an NPC to a scene",
        "arg_types": {"scene_path": "string", "role": "string", "name": "string", "x": "integer", "y": "integer", "tags": "list[string]", "quest_id": "string"},
        "defaults": {"x": 300, "y": 300}
    },
    "create_quest": {
        "description": "Create a new quest entry",
        "arg_types": {"path": "string", "id": "string", "title": "string", "type": "string"}
    },
    "wire_world": {
        "description": "Add a scene to the world map",
        "arg_types": {"world_path": "string", "scene_id": "string", "scene_path": "string", "link_from": "string"}
    },
    "polish_scene": {
        "description": "Polish a scene file",
        "arg_types": {"path": "string", "compact_only": "boolean"},
        "defaults": {"compact_only": False}
    },
    "auto_wire_transitions": {
        "description": "Automatically wire transitions between scenes",
        "arg_types": {"world_path": "string"}
    },
    "add_transition": {
        "description": "Add a transition trigger to a scene",
        "arg_types": {
            "scene_path": "string",
            "target_scene": "string",
            "x": "integer",
            "y": "integer",
            "name": "string",
            "sprite": "string",
            "spawn_id": "string",
            "allow_interact": "boolean",
        }
    },
    "add_puzzle_switch_door": {
        "description": "Add a puzzle switch and door to a scene",
        "arg_types": {"scene_path": "string", "switch": "string", "door": "string", "reward": "string", "id_prefix": "string", "event_id": "string"}
    },
    "add_npc_dialogue": {
        "description": "Add dialogue to an NPC",
        "arg_types": {"scene_path": "string", "npc_name": "string", "lines": "list[string]", "dialogue_id": "string", "speaker_alias": "string"}
    },
    "validate": {
        "description": "Validate a scene",
        "arg_types": {"scene_path": "string", "check_refs": "boolean"},
        "defaults": {"check_refs": False}
    }
}

NO_METADATA_ACTIONS: set[str] = set()

def build_plan_schema() -> dict[str, Any]:
    """
    Build the external plan schema from the internal linter schema.
    This ensures a single source of truth.
    """
    actions: dict[str, Any] = {}

    # We need descriptions and type info which are not fully in ACTION_SCHEMAS yet.
    # However, for now we will generate a best-effort schema based on linter requirements.
    # Ideally, ACTION_SCHEMAS should be richer, or we merge with a description registry.

    # Since we are replacing the manual dictionary, we need to preserve the descriptions and types
    # that were there.
    # Let's define a metadata registry here that augments the linter schema.

    for action_type, linter_def in sorted(ACTION_SCHEMAS.items()):
        meta: dict[str, Any] = METADATA.get(action_type, {})

        args_schema: dict[str, Any] = {}

        # Process required args
        for arg in linter_def.get("required", []):
            args_schema[arg] = {
                "type": meta.get("arg_types", {}).get(arg, "string"),
                "required": True
            }
            if "choices" in meta and arg in meta["choices"]:
                args_schema[arg]["choices"] = meta["choices"][arg]

        # Process optional args
        for arg in linter_def.get("optional", []):
            args_schema[arg] = {
                "type": meta.get("arg_types", {}).get(arg, "string"),
                "required": False
            }
            if "defaults" in meta and arg in meta["defaults"]:
                args_schema[arg]["default"] = meta["defaults"][arg]
            if "choices" in meta and arg in meta["choices"]:
                args_schema[arg]["choices"] = meta["choices"][arg]

        action_schema = {
            "description": meta.get("description", f"Action: {action_type}"),
            "args": args_schema
        }

        if linter_def.get("writes_files") is False:
            action_schema["writes_files"] = False

        actions[action_type] = action_schema

    return {"actions": actions}

PLAN_SCHEMA = build_plan_schema()

def plan_schema_command(args: argparse.Namespace) -> None:
    """Generate a snapshot of the Plan Action schema."""

    if args.ai_out:
        ai_schema = ai_plan_command.generate_ai_schema()
        output_json = json_io.dumps_stable(ai_schema)
        out_path = Path(args.ai_out)
        json_io.write_json_atomic(out_path, ai_schema)
        print(f"[Mesh][Schema] Wrote AI Plan schema to {out_path}")
        return

    output_json = json_io.dumps_stable(PLAN_SCHEMA)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if args.verify:
            if not out_path.exists():
                print(f"[Mesh][Schema] FAILURE: Schema file '{out_path}' does not exist.")
                sys.exit(1)

            existing = out_path.read_text(encoding="utf-8")
            # Normalize newlines
            existing = existing.replace("\r\n", "\n")
            output_json = output_json.replace("\r\n", "\n")

            if existing.strip() != output_json.strip():
                print("[Mesh][Schema] FAILURE: Plan schema mismatch.")
                print(f"Run 'mesh plan schema --out {args.out}' to update.")
                sys.exit(1)
            else:
                print("[Mesh][Schema] Plan schema verified.")
        else:
            json_io.write_json_atomic(out_path, PLAN_SCHEMA)
            print(f"[Mesh][Schema] Wrote Plan schema to {out_path}")
    else:
        print(output_json)

def add_plan_schema_command(subparsers) -> None:
    parser = subparsers.add_parser("schema", help="Generate Plan Action schema snapshot")
    parser.add_argument("--out", help="Output JSON file path")
    parser.add_argument("--ai-out", help="Output AI-focused schema JSON file path")
    parser.add_argument("--verify", action="store_true", help="Verify against existing snapshot")
    parser.set_defaults(func=plan_schema_command)
