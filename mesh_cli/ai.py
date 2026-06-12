"""AI and Planning commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import ai_history, json_io
from engine.ai_audit import run_ai_audit
from engine.ai_bundle import build_ai_bundle
from engine.tooling import ai_plan_command, plan_history, plan_linter
from engine.tooling.ai_context_exporter import export_ai_context
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Action, Plan


def handle(args: argparse.Namespace) -> int:
    if args.command == "apply-plan":
        return _handle_apply_plan(args)
    if args.command == "undo-last-plan":
        return _handle_undo_last_plan(args)
    if args.command == "ai-generate-plan":
        return _handle_ai_generate_plan(args)
    if args.command == "ai-export-context":
        return _handle_ai_export_context(args)
    if args.command == "ai-bundle":
        return _handle_ai_bundle(args)
    if args.command == "ai-history":
        return _handle_ai_history(args)
    if args.command == "ai-audit":
        result = run_ai_audit(json_output=args.json)
        if args.json and result:
            print(json.dumps(result, indent=2))
        return 0
    return 1


def register(subparsers: argparse._SubParsersAction) -> None:
    # Apply Plan
    apply_plan_parser = subparsers.add_parser("apply-plan", help="Apply a content plan", description="Apply a content plan")
    apply_plan_parser.add_argument("plan_path", nargs="?", help="Path to plan file")
    apply_plan_parser.add_argument("--from-triage", action="store_true", help="Use last triage plan")
    apply_plan_parser.add_argument("--no-lint", action="store_true", help="Skip linting")
    apply_plan_parser.add_argument("--dry-run", action="store_true", help="Dry run")
    apply_plan_parser.add_argument("--run-tests", action="store_true", help="Run tests after apply")
    apply_plan_parser.add_argument("--ai-safe", action="store_true", help="Run AI safety checks (lint-ai + test-ai) before applying")

    # Undo Last Plan
    subparsers.add_parser("undo-last-plan", help="Undo last applied plan", description="Undo last applied plan")

    # AI Generate Plan
    ai_gen_parser = subparsers.add_parser("ai-generate-plan", help="Generate plan from prompt", description="Generate plan from prompt")
    ai_gen_parser.add_argument("prompt", help="Prompt text")
    ai_gen_parser.add_argument("--out", required=True, help="Output file")
    ai_gen_parser.add_argument(
        "--allow-todos",
        action="store_true",
        help="Allow placeholder TODO/TBD tokens in the generated plan (default: strict).",
    )

    # AI Export Context
    ai_export_parser = subparsers.add_parser("ai-export-context", help="Export scene context for AI", description="Export scene context for AI")
    ai_export_parser.add_argument("scene_paths", nargs="+", help="Paths to scene files")
    ai_export_parser.add_argument("--out", help="Output JSON file path")

    # AI Bundle
    ai_bundle_parser = subparsers.add_parser("ai-bundle", help="Create AI bundle", description="Create AI bundle")
    ai_bundle_parser.add_argument("--scenes", nargs="+", required=True, help="Scene paths")
    ai_bundle_parser.add_argument("--goal", required=True, help="Goal description")
    ai_bundle_parser.add_argument("--out", required=True, help="Output file")

    # AI History
    ai_history_parser = subparsers.add_parser("ai-history", help="Show AI plan history", description="Show AI plan history")
    ai_history_parser.add_argument("--scene", help="Filter by scene ID")
    ai_history_parser.add_argument("--plan", help="Filter by plan path")
    ai_history_parser.add_argument("--limit", type=int, default=20, help="Limit number of entries")
    ai_history_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # AI Audit
    ai_audit_parser = subparsers.add_parser("ai-audit", help="Audit scenes and quests for AI completeness", description="Audit scenes and quests for AI completeness")
    ai_audit_parser.add_argument("--json", action="store_true", help="Output as JSON")


def _handle_apply_plan(args: argparse.Namespace) -> int:
    """Apply a content plan."""
    if getattr(args, "from_triage", False):
        triage_plan = Path("artifacts/triage_last_plan.json")
        if triage_plan.exists():
            args.plan_path = str(triage_plan)
        else:
            print("Error: No triage plan found at artifacts/triage_last_plan.json")
            return 1

        args.ai_safe = True
        print(f"[Mesh][CLI] Using triage plan: {args.plan_path}")

    if not args.plan_path:
        print("Error: plan_path is required.")
        return 1

    try:
        with open(args.plan_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Convert actions dicts to Action objects
        actions = [Action(**a) for a in data.pop("actions")]
        plan = Plan(actions=actions, **data)

        # AI Safety Checks
        if args.ai_safe:
            print("[Mesh][CLI] Running AI safety checks...")

            # 1. Lint AI
            issues = plan_linter.lint_ai_plan(plan)
            errors = [i for i in issues if i.severity == "error"]
            if errors:
                print(f"[Mesh][CLI] AI Plan linting failed with {len(errors)} errors:")
                for err in errors:
                    print(f"  - [{err.code}] {err.message} (Action {err.action_index})")
                return 1

            # 2. Test AI (Sandbox)
            from engine.tooling.plan_tester import PlanTester
            tester = PlanTester(Path("."))
            report = tester.run_ai_tests(plan)
            if not report.passed:
                print("[Mesh][CLI] AI Plan tests failed in sandbox.")
                return 1

            print("[Mesh][CLI] AI safety checks passed.")

        # Lint unless disabled
        if not args.no_lint:
            issues = plan_linter.lint_plan(plan)
            errors = [i for i in issues if i.severity == "error"]
            if errors:
                print(f"[Mesh][CLI] Plan linting failed with {len(errors)} errors:")
                for err in errors:
                    print(f"  - [{err.code}] {err.message} (Action {err.action_index})")
                return 1
            if issues:
                print(f"[Mesh][CLI] Plan linting passed with {len(issues)} warnings.")

        executor = PlanExecutor(dry_run=args.dry_run, safe_paths_only=True)
        executor.execute(plan, profile="cli_apply", ai_safe=args.ai_safe)
        print(f"[Mesh][CLI] Plan '{args.plan_path}' applied successfully.")

        # AI History Logging
        if args.ai_safe and not args.dry_run:
            scenes = ai_history.extract_scenes_from_plan({"actions": plan.actions})
            goal = plan.inputs.get("prompt") or plan.inputs.get("goal")
            ai_history.append_history_entry(args.plan_path, scenes, goal=goal)

        # Run tests if requested
        test_results = None
        tests_passed = True
        if args.run_tests and not args.dry_run:
            print("[Mesh][CLI] Running post-apply tests...")
            from engine.tooling.plan_tester import PlanTester
            tester = PlanTester(Path("."))
            tests = tester.infer_tests(plan)
            report = tester.run_tests(tests, total_actions=len(plan.actions))
            tests_passed = report.passed
            test_results = {
                "passed": report.passed,
                "count": len(report.tests),
                "coverage": report.coverage,
                "details": report.tests
            }
            if not tests_passed:
                print("[Mesh][CLI] Tests failed!")

        # Record history
        if not args.dry_run:
            result = {
                "success": True,
                "summary": executor.summary,
                "tests": test_results
            }
            plan_history.record_history(plan, result, profile="cli_apply")

        if getattr(args, "from_triage", False):
            print("\nNext commands:")
            print("  mesh preset lint")
            print(f"  mesh plan test-ai --path {args.plan_path}")

        return 0 if tests_passed else 1
    except Exception as e:
        print(f"[Mesh][CLI] Failed to apply plan: {e}")
        return 1


def _handle_undo_last_plan(args: argparse.Namespace) -> int:
    """Undo the last applied plan."""
    try:
        executor = PlanExecutor()
        executor.undo_last()
        print("[Mesh][CLI] Undo successful.")
        return 0
    except Exception as e:
        print(f"[Mesh][CLI] Undo failed: {e}")
        return 1


def _handle_ai_generate_plan(args: argparse.Namespace) -> int:
    """Generate a plan skeleton from a prompt."""
    print(f"[Mesh][AI] Generating plan for prompt: '{args.prompt}'")

    plan = ai_plan_command.generate_plan_skeleton(args.prompt, allow_todos=bool(getattr(args, "allow_todos", False)))

    json_io.write_json_atomic(args.out, plan)

    print(f"[Mesh][AI] Plan written to '{args.out}'")
    return 0


def _handle_ai_export_context(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.scene_paths]
    try:
        context = export_ai_context(paths)

        if args.out:
            json_io.write_json_atomic(args.out, context)
            print(f"[Mesh][AI] Context exported to {args.out}")
        else:
            print(json.dumps(context, indent=2))

        return 0
    except Exception as e:
        print(f"[Mesh][AI] Error exporting context: {e}")
        return 1


def _handle_ai_bundle(args: argparse.Namespace) -> int:
    scene_paths = [Path(p) for p in args.scenes]
    try:
        bundle = build_ai_bundle(scene_paths, args.goal)
        json_io.write_json_atomic(args.out, bundle)
        print(f"[Mesh][AI] Bundle written to '{args.out}'")
        return 0
    except Exception as e:
        print(f"Error creating bundle: {e}")
        return 1


def _handle_ai_history(args: argparse.Namespace) -> int:
    entries = ai_history.load_history()
    filtered = ai_history.filter_history(entries, scene=args.scene, plan_path=args.plan)

    # Sort reverse chronological (newest first)
    filtered.sort(key=lambda x: x["timestamp"], reverse=True)

    # Limit default 20
    limit = getattr(args, "limit", 20)
    filtered = filtered[:limit]

    if args.json:
        print(json.dumps(filtered, indent=2))
    else:
        if not filtered:
            print("No history found.")
            return 0

        for entry in filtered:
            ts = entry.get("timestamp", "???")
            pp = entry.get("plan_path", "???")
            scenes = ", ".join(entry.get("scenes_touched", []))
            res = entry.get("result", "applied")
            goal = entry.get("goal")

            print(f"{ts}")
            print(f"  plan: {pp}")
            print(f"  scenes: {scenes}")
            print(f"  result: {res}")
            if goal:
                print(f"  goal: {goal}")
            print("")

    return 0
