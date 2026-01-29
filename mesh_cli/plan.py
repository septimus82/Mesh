from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from engine import json_io

def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # Plan
    from engine.tooling import plan_cli

    plan_parser = subparsers.add_parser("plan", help="Manage content plans")
    plan_cli.add_plan_arguments(plan_parser)


def handle(args: argparse.Namespace) -> int:
    from engine.tooling import plan_fix_command

    if getattr(args, "plan_command", None) == "fix-from-doctor":
        return plan_fix_command.run_plan_fix_command(args)
    if getattr(args, "plan_command", None) == "lint":
        return _handle_plan_lint(args)
    if getattr(args, "plan_command", None) == "lint-ai":
        return _handle_plan_lint_ai(args)
    if getattr(args, "plan_command", None) == "diff":
        return _handle_plan_diff(args)
    if getattr(args, "plan_command", None) == "history":
        return _handle_plan_history(args)
    if getattr(args, "plan_command", None) == "show":
        return _handle_plan_show(args)
    if getattr(args, "plan_command", None) == "test":
        return _handle_plan_test(args)
    if getattr(args, "plan_command", None) == "test-ai":
        return _handle_plan_test_ai(args)
    if getattr(args, "plan_command", None) == "summarize":
        return _handle_plan_summarize(args)

    # Some plan subcommands (e.g. schema) are implemented via args.func.
    func = getattr(args, "func", None)
    if callable(func):
        result = func(args)
        return int(result) if isinstance(result, int) else 0

    print("[Mesh][CLI] Error: missing plan subcommand")
    return 2


def _handle_plan_lint(args: argparse.Namespace) -> int:
    from engine.tooling import plan_linter
    from engine.tooling.plan_types import Action, Plan

    try:
        with open(args.plan_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        actions = [Action(**a) for a in data.pop("actions")]
        plan = Plan(actions=actions, **data)

        issues = plan_linter.lint_plan(plan)

        if args.json:
            print(json.dumps([asdict(i) for i in issues], indent=2))
        else:
            if not issues:
                print("[Mesh][Lint] No issues found.")
            for i in issues:
                print(f"[{i.severity.upper()}] {i.code}: {i.message} (Action {i.action_index})")

        return 1 if any(i.severity == "error" for i in issues) else 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _handle_plan_lint_ai(args: argparse.Namespace) -> int:
    from engine.tooling import plan_linter
    from engine.tooling.plan_types import Action, Plan

    try:
        with open(args.plan_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        actions = [Action(**a) for a in data.pop("actions")]
        plan = Plan(actions=actions, **data)

        issues = plan_linter.lint_ai_plan(plan)

        if args.json:
            print(json.dumps([asdict(i) for i in issues], indent=2))
        else:
            if not issues:
                print("[Mesh][Lint-AI] No issues found.")
            for i in issues:
                print(f"[{i.severity.upper()}] {i.code}: {i.message} (Action {i.action_index})")

        return 1 if any(i.severity == "error" for i in issues) else 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _handle_plan_test_ai(args: argparse.Namespace) -> int:
    from engine.test_reports.junit_writer import write_junit_report
    from engine.tooling.plan_tester import PlanTester
    from engine.tooling.plan_types import Action, Plan

    try:
        plan_path = Path(args.plan_path)
        if not plan_path.exists():
            print(f"[Mesh][CLI] Plan file not found: {plan_path}")
            return 1

        data = json.loads(plan_path.read_text(encoding="utf-8"))
        actions = [Action(**a) for a in data.pop("actions", [])]
        plan = Plan(actions=actions, **data)

        tester = PlanTester(Path("."))
        report = tester.run_ai_tests(plan)

        if args.out:
            json_io.write_json_atomic(args.out, asdict(report))
            print(f"[Mesh][Tester] Report written to {args.out}")

        if args.junit:
            write_junit_report(asdict(report), str(Path(args.junit)))
            print(f"[Mesh][Tester] JUnit report written to {args.junit}")

        if not report.passed:
            print("[Mesh][Tester] Tests FAILED.")
            return 1

        print("[Mesh][Tester] Tests PASSED.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _handle_plan_diff(args: argparse.Namespace) -> int:
    from engine.tooling import plan_diff
    from engine.tooling.plan_types import Action, Plan

    try:
        with open(args.plan_a, "r", encoding="utf-8") as f:
            data_a = json.load(f)
        plan_a = Plan(actions=[Action(**a) for a in data_a.pop("actions")], **data_a)

        with open(args.plan_b, "r", encoding="utf-8") as f:
            data_b = json.load(f)
        plan_b = Plan(actions=[Action(**a) for a in data_b.pop("actions")], **data_b)

        diff = plan_diff.diff_plans(plan_a, plan_b)

        if args.json:
            print(json.dumps(diff, indent=2))
        else:
            print("Plan Diff:")
            print(f"  Actions Added: {len(diff['actions_added'])}")
            print(f"  Actions Removed: {len(diff['actions_removed'])}")
            print(f"  Actions Changed: {len(diff['actions_changed'])}")
            print(f"  Files Touched: {len(diff['estimated_files_touched'])}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def _handle_plan_test(args: argparse.Namespace) -> int:
    from engine.test_reports.junit_writer import write_junit_report
    from engine.tooling.plan_tester import PlanTester
    from engine.tooling.plan_types import Action, Plan

    try:
        plan_path = Path(args.plan_path)
        if not plan_path.exists():
            print(f"[Mesh][CLI] Plan file not found: {plan_path}")
            return 1

        data = json.loads(plan_path.read_text(encoding="utf-8"))
        # Handle legacy plans that might not have actions list wrapped
        if "actions" not in data and isinstance(data, list):
            # This shouldn't happen with new plans, but just in case
            actions = [Action(**a) for a in data]
            plan = Plan(actions=actions, wizard="unknown", version=1, inputs={})
        else:
            actions = [Action(**a) for a in data.pop("actions", [])]
            plan = Plan(actions=actions, **data)

        tester = PlanTester(Path("."))

        if args.sandbox or args.sandbox_full:
            report = tester.run_tests_in_sandbox(plan, full_sandbox=args.sandbox_full)
        else:
            tests = tester.infer_tests(plan)
            report = tester.run_tests(tests, total_actions=len(plan.actions))

        # Print report summary
        print("\n[Mesh][Tester] Report:")
        print(f"  Passed: {report.passed}")
        print(f"  Tests: {len(report.tests)}")
        print(
            f"  Coverage: {report.coverage.get('actions_covered', 0)}/{report.coverage.get('actions_total', 0)} ({report.coverage_ratio:.1%})"
        )

        if not report.passed:
            print("\nFailures:")
            for t in report.tests:
                if not t["passed"]:
                    print(f"  - {t['name']}: {t['error']}")

        # Outputs
        report_dict = asdict(report)
        if args.out:
            json_io.write_json_atomic(args.out, report_dict)
            print(f"[Mesh][Tester] JSON report written to {args.out}")

        if args.junit:
            write_junit_report(report_dict, args.junit)
            print(f"[Mesh][Tester] JUnit report written to {args.junit}")

        # Coverage check
        if args.min_coverage is not None:
            if report.coverage_ratio < args.min_coverage:
                print(f"[Mesh][Tester] FAIL: Coverage {report.coverage_ratio:.2f} is below threshold {args.min_coverage}")
                return 1

        return 0 if report.passed else 1
    except Exception as e:
        print(f"[Mesh][CLI] Error testing plan: {e}")
        return 1


def _handle_plan_history(_args: argparse.Namespace) -> int:
    from engine.tooling import plan_history

    history = plan_history.list_history()
    print(f"{'ID':<20} {'Timestamp':<12} {'Wizard':<15} {'Actions':<8}")
    print("-" * 60)
    for h in history:
        print(f"{h['id']:<20} {h['timestamp']:<12} {h['wizard']:<15} {h['actions']:<8}")
    return 0


def _handle_plan_show(args: argparse.Namespace) -> int:
    from engine.tooling import plan_history

    record = plan_history.get_history(args.id)
    if not record:
        print(f"History record '{args.id}' not found.")
        return 1
    print(json.dumps(record, indent=2))
    return 0


def _handle_plan_summarize(args: argparse.Namespace) -> int:
    from engine.tooling.plan_summary import summarize_plan

    print(summarize_plan(args.plan_path))
    return 0
