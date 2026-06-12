import re
from dataclasses import dataclass
from typing import Any, List, Optional

from engine.tooling.ai_plan_command import ALLOWED_AI_ACTIONS
from engine.tooling.plan_types import Plan


@dataclass
class Issue:
    severity: str  # "error" | "warn"
    code: str
    message: str
    action_index: Optional[int] = None

ALLOWED_AI_ROOTS = ("scenes/", "packs/", "worlds/", "assets/")

def is_allowed_ai_path(path: str) -> bool:
    """Check if path is within allowed AI roots."""
    return path.startswith(ALLOWED_AI_ROOTS)

ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "init_pack": {"required": ["path", "id"], "optional": ["wip"]},
    "create_scene": {"required": ["path", "template"], "optional": []},
    "add_npc": {"required": ["scene_path", "role"], "optional": ["x", "y", "tags", "name", "quest_id"]},
    "create_quest": {"required": ["path", "id", "title", "type"], "optional": []},
    "wire_world": {"required": ["world_path", "scene_id", "scene_path"], "optional": ["link_from"]},
    "auto_wire_transitions": {"required": ["world_path"], "optional": []},
    "polish_scene": {"required": ["path"], "optional": ["compact_only"]},
    "validate": {"required": ["scene_path"], "optional": ["check_refs"], "writes_files": False},
    "add_transition": {"required": ["scene_path", "target_scene"], "optional": ["x", "y", "name", "sprite", "spawn_id", "allow_interact"]},
    "add_puzzle_switch_door": {"required": ["scene_path"], "optional": ["switch", "door", "reward", "id_prefix", "event_id"]},
    "add_npc_dialogue": {"required": ["scene_path", "npc_name", "lines"], "optional": ["dialogue_id", "speaker_alias"]},
}

NON_WRITING_ACTIONS: set[str] = {k for k, v in ACTION_SCHEMAS.items() if v.get("writes_files") is False}
WRITING_ACTIONS: set[str] = set(ACTION_SCHEMAS.keys()) - NON_WRITING_ACTIONS

def lint_plan(plan: Plan) -> List[Issue]:
    issues = []

    # 1. Validate Version
    if plan.version != 1:
        issues.append(Issue("error", "INVALID_VERSION", f"Unsupported plan version: {plan.version}"))

    # 2. Validate Actions
    for i, action in enumerate(plan.actions):
        schema = ACTION_SCHEMAS.get(action.type)
        if not schema:
            issues.append(Issue("error", "UNKNOWN_ACTION", f"Unknown action type: {action.type}", i))
            continue

        # Check required args
        for req in schema["required"]:
            if req not in action.args:
                issues.append(Issue("error", "MISSING_ARG", f"Missing required argument: {req}", i))

        # Check for unknown args (optional, but good for strictness)
        # allowed = set(schema["required"]) | set(schema["optional"])
        # for arg in action.args:
        #     if arg not in allowed:
        #         issues.append(Issue("warn", "UNKNOWN_ARG", f"Unknown argument: {arg}", i))

        # Check paths
        for key, val in action.args.items():
            if key.endswith("path") and isinstance(val, str):
                # Basic path validation
                if ".." in val:
                     issues.append(Issue("warn", "SUSPICIOUS_PATH", f"Path contains '..': {val}", i))

                # Check if path is absolute (should be relative usually, or absolute within workspace)
                # For now, just warn if it looks like a system path
                if val.startswith("/") or (len(val) > 1 and val[1] == ":"):
                     # It's absolute. Check if it's inside workspace?
                     # We don't have workspace root easily here without context.
                     # But we can check if it's trying to escape.
                     pass

    return issues


def lint_ai_plan(plan: Plan) -> List[Issue]:
    """Strict linting for AI-generated plans."""
    issues = []

    placeholder_hits: list[tuple[int | None, str, str]] = []

    def _iter_strings(value: object, path: str) -> None:
        if isinstance(value, str):
            placeholder_hits.append((_path_action_index(path), path, value))
            return
        if isinstance(value, dict):
            for k in sorted(value.keys(), key=lambda x: str(x)):
                v = value[k]
                _iter_strings(v, f"{path}.{k}" if path else str(k))
            return
        if isinstance(value, list):
            for idx, item in enumerate(value):
                _iter_strings(item, f"{path}[{idx}]")
            return

    def _path_action_index(path: str) -> int | None:
        m = re.match(r"^actions\[(\d+)\]", str(path or ""))
        if not m:
            return None
        try:
            return int(m.group(1))
        except ValueError:
            return None

    def _has_placeholder(text: str) -> str | None:
        lower = text.lower()
        if "todo" in lower:
            return "TODO"
        if re.search(r"\btbd\b", lower):
            return "TBD"
        return None

    # 1. Validate Version
    if plan.version != 1:
        issues.append(Issue("error", "INVALID_VERSION", f"Unsupported plan version: {plan.version}"))

    # 1b. Reject placeholder strings anywhere in the plan
    try:
        from dataclasses import asdict  # noqa: PLC0415

        plan_dict = asdict(plan)
    except (AttributeError, RecursionError, TypeError):
        # REASON: placeholder lint falls back to direct attributes when
        # dataclass flattening fails on partial or mocked plan objects
        plan_dict = {"wizard": plan.wizard, "version": plan.version, "inputs": plan.inputs, "actions": plan.actions}

    _iter_strings(plan_dict, "")
    for action_index, path, text in sorted(placeholder_hits, key=lambda x: ((x[0] is not None), x[0] or -1, x[1])):
        hit = _has_placeholder(text)
        if hit is None:
            continue
        issues.append(
            Issue(
                "error",
                "PLACEHOLDER_TEXT",
                f"Plan contains placeholder token '{hit}' at '{path}': {text!r}",
                action_index=action_index,
            )
        )

    # 2. Validate Actions
    for i, action in enumerate(plan.actions):
        if action.type not in ALLOWED_AI_ACTIONS:
            issues.append(Issue("error", "DISALLOWED_ACTION", f"Action '{action.type}' is not allowed in AI plans.", i))
            continue

        schema = ALLOWED_AI_ACTIONS[action.type]
        required_args_raw = schema.get("required_args", {})
        optional_args_raw = schema.get("optional_args", {})
        required_args: dict[str, Any] = required_args_raw if isinstance(required_args_raw, dict) else {}
        optional_args: dict[str, Any] = optional_args_raw if isinstance(optional_args_raw, dict) else {}

        # Check required args
        for req in required_args:
            if req not in action.args:
                issues.append(Issue("error", "MISSING_ARG", f"Missing required argument: {req}", i))
            else:
                val = action.args.get(req)
                if isinstance(val, str) and not val.strip():
                    issues.append(
                        Issue(
                            "error",
                            "EMPTY_REQUIRED_STRING",
                            f"Required argument '{req}' must not be empty (actions[{i}].args.{req}).",
                            i,
                        )
                    )

        # Check for unknown args
        allowed_args = set(required_args.keys()) | set(optional_args.keys())
        for arg in action.args:
            if arg not in allowed_args:
                issues.append(Issue("error", "UNKNOWN_ARG", f"Unknown argument '{arg}' for action '{action.type}'", i))

        # Check paths
        for key, val in action.args.items():
            if isinstance(val, str):
                if ".." in val:
                    issues.append(Issue("error", "UNSAFE_PATH", f"Path contains '..': {val}", i))

                # Check allowed directories for path-like arguments
                if key.endswith("path") or key in ["scene", "target_scene"]:
                     if not is_allowed_ai_path(val):
                         issues.append(Issue("error", "UNSAFE_PATH", f"Path must start with {', '.join(ALLOWED_AI_ROOTS)}: {val}", i))

        # Specific validation for add_npc_dialogue
        if action.type == "add_npc_dialogue":
            lines = action.args.get("lines")
            if lines is not None:
                if not isinstance(lines, list):
                    issues.append(Issue("error", "INVALID_TYPE", "Argument 'lines' must be a list of strings.", i))
                else:
                    if len(lines) > 8:
                        issues.append(Issue("error", "CONSTRAINT_VIOLATION", f"Too many dialogue lines ({len(lines)} > 8).", i))
                    for line in lines:
                        if not isinstance(line, str):
                            issues.append(Issue("error", "INVALID_TYPE", "Dialogue lines must be strings.", i))
                        elif len(line) > 120:
                            issues.append(Issue("error", "CONSTRAINT_VIOLATION", f"Dialogue line too long ({len(line)} > 120 chars).", i))

    return issues
