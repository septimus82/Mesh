from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import json_io
from engine.tooling.doctor import DoctorRunner
from engine.tooling.explain import ExplainRunner
from engine.tooling import plan_fix_command
from engine.tooling.plan_executor import PlanExecutor


def add_triage_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("triage", help="Run doctor, explain, and generate fix plan")
    parser.add_argument("--world", help="World to check")
    parser.add_argument("--out", required=True, help="Output plan path")
    parser.add_argument("--write-artifacts", action="store_true", help="Write doctor and explain artifacts to disk")
    parser.set_defaults(func=run_triage_command)


def run_triage_command(args: argparse.Namespace) -> int:
    # 1. Run Doctor
    doctor_runner = DoctorRunner()
    result = doctor_runner.run_result(world=args.world)
    
    # 2. Store artifact (ensure "last artifact" is written)
    explain_runner = ExplainRunner()
    if result.exit_code != 0:
        explain_runner.store_last_failure(result)
    
    # 3. Generate Fix Plan
    # We need the report dict for generate_fix_plan
    report = result.to_doctor_report_dict()
    artifact_path = str(explain_runner._last_failure_path).replace("\\", "/")
    
    plan = plan_fix_command.generate_fix_plan(report, artifact_path)

    # Validate plan is safe to apply with --ai-safe (touches coverage).
    plan_is_valid = True
    plan_validation_warning = {"id": "plan_invalid_touches", "message": "Plan invalid: touches mismatch"}
    try:
        # Dry-run + writer callback ensures no filesystem mutation while reusing PlanExecutor ai_safe checks.
        executor = PlanExecutor(dry_run=True, writer=lambda _p, _c: None)
        from io import StringIO
        import sys

        capture_exec = StringIO()
        original_stdout_exec = sys.stdout
        sys.stdout = capture_exec
        try:
            executor.execute(plan, ai_safe=True)
        finally:
            sys.stdout = original_stdout_exec
    except ValueError:
        plan_is_valid = False
    
    # 4. Run Explain and print JSON
    # We use the result we just got, effectively "explain --last" but without reloading from disk if we have it in memory
    explanation_str = explain_runner.explain_result(result, json_output=True)
    
    try:
        explanation_data = json.loads(explanation_str)
        
        # 5. Consistency Check: Plan vs Action Hints
        action_hints = explanation_data.get("action_hints", [])
        triage_warnings: list[dict] = []
        
        # Build a set of (action_type, target_path) from hints for fast lookup
        hint_targets = set()
        for hint in action_hints:
            # Normalize target path
            target = hint.get("target", "").replace("\\", "/")
            hint_targets.add((hint.get("suggested_action"), target))
            
        for action in plan.actions:
            # Check if this action matches any hint
            found_match = False
            
            # We check if the action type matches and if ANY of the args match the target path
            for arg_value in action.args.values():
                if isinstance(arg_value, str):
                    normalized_arg = arg_value.replace("\\", "/")
                    if (action.type, normalized_arg) in hint_targets:
                        found_match = True
                        break
            
            if not found_match:
                # Try to find a path-like arg for the message
                path_arg = action.args.get("path") or action.args.get("scene_path") or action.args.get("target_scene") or "unknown"
                triage_warnings.append(
                    {
                        "id": "action_hints_mismatch",
                        "message": f"Plan action '{action.type}' on '{path_arg}' has no corresponding action_hint.",
                    }
                )
        
        if triage_warnings:
            explanation_data["warnings"] = triage_warnings

        if not plan_is_valid:
            explanation_data.setdefault("warnings", []).append(plan_validation_warning)

        if "warnings" in explanation_data:
            warnings = [w for w in (explanation_data.get("warnings") or []) if isinstance(w, dict)]
            warnings = sorted(warnings, key=lambda w: (str(w.get("id") or ""), str(w.get("message") or "")))
            explanation_data["warnings"] = warnings

        # Inject plan_meta
        explanation_data["plan_meta"] = {
            "touches": plan.inputs.get("meta", {}).get("touches", []),
            "unfixable": plan.inputs.get("meta", {}).get("unfixable", [])
        }
        print(json.dumps(explanation_data, indent=2))
    except json.JSONDecodeError:
        # Fallback if explanation isn't valid JSON (shouldn't happen with json_output=True)
        print(explanation_str)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Serialize plan (reusing logic from plan_fix_command would be nice, but it's embedded in run_plan_fix_command)
    # I should probably extract the serialization logic in plan_fix_command to reuse it, 
    # or just duplicate the simple serialization here. 
    # Given "Minimal diffs", I will duplicate the serialization if it's small, 
    # or better: refactor plan_fix_command to expose save_plan.
    
    # Let's duplicate for now to avoid touching plan_fix_command again unless necessary, 
    # as I just finished it. It's just a few lines.
    
    plan_data = {
        "wizard": plan.wizard,
        "version": plan.version,
        "meta": plan.inputs.get("meta", {}),
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
    
    # Handle meta field placement
    plan_data["meta"] = plan.inputs["meta"]
    if "meta" in plan_data["inputs"]:
        del plan_data["inputs"]["meta"]

    # Ensure deterministic output
    # Sort touches in meta
    if "touches" in plan_data["meta"]:
        plan_data["meta"]["touches"] = sorted(plan_data["meta"]["touches"])
    if "unfixable" in plan_data["meta"]:
        plan_data["meta"]["unfixable"] = sorted(plan_data["meta"]["unfixable"])

    json_io.write_json_atomic(out_path, plan_data)
    
    # Write artifacts if requested
    if getattr(args, "write_artifacts", False):
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        doctor_path = artifacts_dir / "triage_last_doctor.json"
        json_io.write_json_atomic(doctor_path, report)
        
        explain_path = artifacts_dir / "triage_last_explain.json"
        # explanation is a JSON string, parse it back to dump it prettily or just write it?
        # explain_result returns a string.
        try:
            # We already parsed and modified it above
            json_io.write_json_atomic(explain_path, explanation_data)
        except (json.JSONDecodeError, UnboundLocalError):
            explain_path.write_text(explanation_str, encoding="utf-8")
            
        plan_artifact_path = artifacts_dir / "triage_last_plan.json"
        if not plan_is_valid:
            if plan_artifact_path.exists():
                plan_artifact_path.unlink()
        else:
            json_io.write_json_atomic(plan_artifact_path, plan_data)

        print(f"\nArtifacts written:")
        print(f"  {doctor_path.as_posix()}")
        print(f"  {explain_path.as_posix()}")
        if plan_is_valid:
            print(f"  {plan_artifact_path.as_posix()}")

    # 5. Print next commands
    print(f"\nNext commands:")
    print("  mesh preset lint")
    print(f"  mesh apply-plan --ai-safe {args.out}")
    print(f"  mesh plan test-ai {args.out}")
    
    return 0
