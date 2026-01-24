from typing import Any, Dict, Set

from engine.tooling.plan_types import Action, Plan


def diff_plans(plan_a: Plan, plan_b: Plan) -> Dict[str, Any]:
    """Compare two plans and return a summary of differences."""

    diff: Dict[str, Any] = {
        "actions_added": [],
        "actions_removed": [],
        "actions_changed": [], # (index, old, new)
        "estimated_files_touched": [],
        "pack_targets": set(),
        "world_targets": set()
    }

    # Compare actions
    len_a = len(plan_a.actions)
    len_b = len(plan_b.actions)

    for i in range(max(len_a, len_b)):
        if i < len_a and i < len_b:
            act_a = plan_a.actions[i]
            act_b = plan_b.actions[i]
            if act_a != act_b:
                diff["actions_changed"].append({
                    "index": i,
                    "old": _action_summary(act_a),
                    "new": _action_summary(act_b)
                })
        elif i < len_a:
            diff["actions_removed"].append(_action_summary(plan_a.actions[i]))
        else:
            diff["actions_added"].append(_action_summary(plan_b.actions[i]))

    # Analyze files touched in plan_b (the new plan)
    files: Set[str] = set()
    packs: Set[str] = set()
    worlds: Set[str] = set()

    for action in plan_b.actions:
        _analyze_action_targets(action, files, packs, worlds)

    diff["estimated_files_touched"] = sorted(list(files))
    diff["pack_targets"] = sorted(list(packs))
    diff["world_targets"] = sorted(list(worlds))

    return diff

def _action_summary(action: Action) -> str:
    return f"[{action.type}] {action.description}"

def _analyze_action_targets(action: Action, files: Set[str], packs: Set[str], worlds: Set[str]):
    args = action.args

    # Extract paths
    for key, val in args.items():
        if key.endswith("path") and isinstance(val, str):
            files.add(val)

    # Extract specific targets
    if action.type == "init_pack":
        packs.add(args.get("id", "unknown"))
    elif action.type == "wire_world":
        if "world_path" in args:
            worlds.add(args["world_path"])
