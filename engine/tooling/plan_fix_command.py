from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from engine import json_io
from engine.tooling.explain import ExplainRunner
from engine.tooling.plan_types import Action, Plan
from engine.tooling.plan_linter import is_allowed_ai_path
from engine.tooling.issue_mapper import IssueHint, map_issue_to_hint


def add_plan_fix_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("fix-from-doctor", help="Generate a fix plan from doctor report")
    parser.add_argument("--last", action="store_true", help="Use last doctor failure")
    parser.add_argument("--path", help="Path to doctor report JSON")
    parser.add_argument("--out", required=True, help="Output plan path")


def run_plan_fix_command(args: argparse.Namespace) -> int:
    runner = ExplainRunner()
    report: Dict[str, Any] | None = None

    if args.last:
        report = runner.load_last_failure()
        artifact_path = str(runner._last_failure_path).replace("\\", "/")
    elif args.path:
        p = Path(args.path)
        if p.exists():
            report = json_io.read_json(p)
            artifact_path = str(p).replace("\\", "/")
        else:
            print(f"Error: Report not found: {args.path}")
            return 1
    else:
        print("Error: Must specify --last or --path")
        return 1

    if not report:
        print("Error: No doctor report found.")
        return 1

    plan = generate_fix_plan(report, artifact_path)
    
    out_path = Path(args.out)
    
    # Serialize manually to match expected JSON format
    plan_data = {
        "wizard": plan.wizard,
        "version": plan.version,
        "meta": plan.inputs.get("meta", {}),  # Store meta in inputs for now as Plan dataclass might not have meta field yet
        "inputs": {k: v for k, v in plan.inputs.items() if k != "meta"},
        "actions": [
            {
                "type": a.type,
                "args": a.args,
                "description": a.description
            }
            for a in plan.actions
        ]
    }
    
    json_io.write_json_atomic(out_path, plan_data)
    print(f"Generated fix plan: {out_path}")
    return 0


def generate_fix_plan(report: Dict[str, Any], artifact_path: str) -> Plan:
    actions: List[Action] = []
    notes: List[str] = []
    touched_files: Set[str] = set()
    unfixable_files: List[str] = []

    # Collect issues
    issues = []
    for item in report.get("errors", []):
        issues.append(item)
    for item in report.get("warnings", []):
        issues.append(item)

    # Sort deterministically: file (handle None), then source/id
    issues.sort(key=lambda x: (str(x.get("file") or ""), x.get("source", "")))

    for issue in issues:
        source = issue.get("source", "")
        msg = issue.get("message", "")
        file_path = issue.get("file")
        
        if file_path:
            file_path = file_path.replace("\\", "/")
            
            # Root enforcement
            if not is_allowed_ai_path(file_path):
                notes.append(f"Unfixable {source}: {msg} ({file_path}) - outside allowed roots")
                unfixable_files.append(file_path)
                continue

        hint = map_issue_to_hint(source, msg, file_path)
        action = _hint_to_action(hint) if hint else None
        
        if action:
            actions.append(action)
            # Collect touched files from action args
            for key, val in action.args.items():
                if isinstance(val, str) and (key.endswith("path") or key in ["scene", "target_scene"]):
                    touched_files.add(val.replace("\\", "/"))
        else:
            notes.append(f"Unfixable {source}: {msg} ({file_path})")

    # Deduplicate actions
    unique_actions: List[Action] = []
    seen_signatures = set()
    
    for action in actions:
        # Create a signature based on type and args
        # args is a dict, so we need to serialize it to make it hashable
        sig = (action.type, json_io.dumps_stable(action.args))
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            unique_actions.append(action)
            
    actions = unique_actions

    return Plan(
        wizard="fix-from-doctor",
        version=1,
        inputs={
            "meta": {
                "source": "doctor",
                "artifact": artifact_path,
                "notes": notes,
                "touches": sorted(list(touched_files)),
                "unfixable": sorted(list(set(unfixable_files))) if unfixable_files else []
            }
        },
        actions=actions
    )


def _hint_to_action(hint: IssueHint) -> Optional[Action]:
    action_type = hint["suggested_action"]
    target = hint["target"]
    
    if action_type == "create_scene":
        return Action(
            type="create_scene",
            args={
                "path": target,
                "template": "empty"
            },
            description=f"Create missing scene: {target}"
        )
    
    if action_type == "validate":
        return Action(
            type="validate",
            args={
                "scene_path": target
            },
            description=f"Validate file: {target}"
        )
        
    return None
