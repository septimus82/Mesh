import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from engine.tooling.plan_types import Plan


def load_plan(plan_path: str) -> Plan:
    """Load and validate a plan from a file path."""
    path = Path(plan_path)
    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in plan file: {e}")

    return Plan.from_dict(data)


def summarize_plan(plan_path: str) -> str:
    """Generate a human-readable summary of a plan."""
    try:
        plan = load_plan(plan_path)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: {e}"

    lines = []
    lines.append(f"Plan: {plan_path}")
    lines.append("")

    # Group actions by type
    actions_by_type: Dict[str, List[Any]] = defaultdict(list)
    for action in plan.actions:
        actions_by_type[action.type].append(action)

    # 1. Dialogue Actions
    dialogue_actions = actions_by_type.pop("add_npc_dialogue", [])
    if dialogue_actions:
        lines.append("NPC Dialogue:")
        for action in dialogue_actions:
            args = action.args
            scene = args.get("scene_path", "unknown").replace("scenes/", "").replace(".json", "")
            npc = args.get("npc_name", "unknown")
            dialogue_id = args.get("dialogue_id", "")
            line_count = len(args.get("lines", []))

            lines.append(f"  - scene: {scene}")
            lines.append(f"    npc: {npc}")
            if dialogue_id:
                lines.append(f"    dialogue_id: {dialogue_id}")
            lines.append(f"    lines: {line_count}")
            lines.append("")

    # 2. Other Actions
    if actions_by_type:
        lines.append("Other actions:")
        for action_type, actions in actions_by_type.items():
            for action in actions:
                desc = action.description or "No description"
                lines.append(f"  - {action_type}: {desc}")
                # Print key args for context
                if action_type == "add_npc":
                    npc_name = action.args.get("name") or action.args.get("role", "unknown")
                    scene = action.args.get("scene_path", "").replace("scenes/", "").replace(".json", "")
                    lines.append(f"    (Add {npc_name} to {scene})")
                elif action_type == "create_scene":
                    path = action.args.get("path", "")
                    template = action.args.get("template", "")
                    lines.append(f"    (Create {path} from {template})")
                elif action_type == "add_transition":
                    target = action.args.get("target_scene", "")
                    lines.append(f"    (To {target})")

                lines.append("")

    return "\n".join(lines)
