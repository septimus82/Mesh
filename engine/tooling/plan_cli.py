import argparse

from engine.tooling import plan_fix_command, plan_schema_command


def add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    plan_subparsers = parser.add_subparsers(dest="plan_command", required=True)

    # Plan Fix from Doctor
    plan_fix_command.add_plan_fix_command(plan_subparsers)

    # Plan Lint
    lint_parser = plan_subparsers.add_parser("lint", help="Lint a plan")
    lint_parser.add_argument("plan_path", help="Path to plan file")
    lint_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Plan Lint AI
    lint_ai_parser = plan_subparsers.add_parser("lint-ai", help="Lint an AI plan")
    lint_ai_parser.add_argument("plan_path", help="Path to plan file")
    lint_ai_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Plan Diff
    diff_parser = plan_subparsers.add_parser("diff", help="Diff two plans")
    diff_parser.add_argument("plan_a", help="First plan")
    diff_parser.add_argument("plan_b", help="Second plan")
    diff_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Plan History
    plan_subparsers.add_parser("history", help="Show plan history")

    # Plan Show
    show_parser = plan_subparsers.add_parser("show", help="Show plan details")
    show_parser.add_argument("id", help="History ID")

    # Plan Test
    test_parser = plan_subparsers.add_parser("test", help="Test a plan")
    test_parser.add_argument("plan_path", help="Path to plan file")
    test_parser.add_argument("--sandbox", action="store_true", help="Run in sandbox")
    test_parser.add_argument("--sandbox-full", action="store_true", help="Run in full sandbox")
    test_parser.add_argument("--out", help="Output report path")
    test_parser.add_argument("--junit", help="Output JUnit report")
    test_parser.add_argument("--min-coverage", type=float, help="Minimum coverage ratio")

    # Plan Test AI
    test_ai_parser = plan_subparsers.add_parser("test-ai", help="Test an AI plan in sandbox")
    test_ai_parser.add_argument("plan_path", help="Path to plan file")
    test_ai_parser.add_argument("--out", help="Output report path")
    test_ai_parser.add_argument("--junit", help="Output JUnit report")

    # Plan Summarize
    summarize_parser = plan_subparsers.add_parser("summarize", help="Summarize a plan")
    summarize_parser.add_argument("plan_path", help="Path to plan file")

    # Plan Schema
    plan_schema_command.add_plan_schema_command(plan_subparsers)
