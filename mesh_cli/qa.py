"""Validation & QA commands for Mesh Engine."""

import argparse
import subprocess
import sys

from engine.tooling import (
    check,
    doctor_command,
    event_validator,
    explain,
    validate_all,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    # Check
    check_parser = subparsers.add_parser("check", help="Run quality checks", description="Run quality checks")
    check.add_check_arguments(check_parser)

    # Validate All
    validate_all_parser = subparsers.add_parser("validate-all", help="Run all validators", description="Run all validators")
    validate_all_parser.add_argument("--path", default=".", help="Root path")
    validate_all_parser.add_argument("--strict", action="store_true", help="Enforce strict validation (no unknown fields)")
    validate_all_parser.add_argument("--schema-strict", action="store_true", help="Enforce strict schema rules")
    validate_all_parser.add_argument("--strict-compact", action="store_true", help="Enforce compact format")
    validate_all_parser.add_argument("--check-reachability", action="store_true", help="Check scene reachability")
    validate_all_parser.add_argument("--check-orphans", action="store_true", help="Check for orphan files")
    validate_all_parser.add_argument("--check-refs", action="store_true", help="Check for missing asset references")

    # Validate Events
    subparsers.add_parser("validate-events", help="Validate event definitions", description="Validate event definitions")

    # Doctor
    doctor_parser = subparsers.add_parser("doctor", help="Diagnose project health", description="Diagnose project health")
    doctor_parser.add_argument("--world", help="World file to validate")
    doctor_parser.add_argument("--quiet", action="store_true", help="Only summary + suggested commands")
    doctor_parser.add_argument("--explain", action="store_true", help="Output explain format (same as mesh explain)")
    doctor_parser.add_argument("--json", action="store_true", help="Machine-readable output")

    # Explain
    explain_parser = subparsers.add_parser("explain", help="Explain doctor/validation failures", description="Explain doctor/validation failures")
    explain_group = explain_parser.add_mutually_exclusive_group()
    explain_group.add_argument("--world", help="World file to validate")
    explain_group.add_argument("--last", action="store_true", help="Explain the most recent stored failure")
    explain_parser.add_argument("--json", action="store_true", help="Machine-readable output")

    # CLI Smoke
    subparsers.add_parser("cli-smoke", help="Run CLI smoke tests", description="Run CLI smoke tests")


def handle(args: argparse.Namespace) -> int:
    if args.command == "check":
        return _handle_check(args)
    if args.command == "validate-all":
        return _handle_validate_all(args)
    if args.command == "validate-events":
        return _handle_validate_events(args)
    if args.command == "doctor":
        return _handle_doctor(args)
    if args.command == "explain":
        return _handle_explain(args)
    if args.command == "cli-smoke":
        return _handle_cli_smoke(args)
    return 1


def _handle_check(args: argparse.Namespace) -> int:
    """Run the quality gate check."""
    return 0 if check.run_check(args.world, args.full, args.replay_trace, frozen=args.frozen) else 1


def _handle_validate_all(args: argparse.Namespace) -> int:
    """Run the unified validator."""
    # Reconstruct argv for the tool's main function
    tool_argv = []
    # Only add path if explicitly provided (not default ".")
    if args.path and args.path != ".":
        tool_argv.append(args.path)
    if args.strict_compact:
        tool_argv.append("--strict-compact")
    if args.strict:
        tool_argv.append("--strict")
    if args.check_reachability:
        tool_argv.append("--check-reachability")
    if args.check_orphans:
        tool_argv.append("--check-orphans")
    if getattr(args, "check_refs", False):
        tool_argv.append("--check-refs")
    if getattr(args, "schema_strict", False):
        tool_argv.append("--schema-strict")
    return validate_all.main(tool_argv if tool_argv else None)


def _handle_validate_events(args: argparse.Namespace) -> int:
    """Run the event validator."""
    return event_validator.main()


def _handle_doctor(args: argparse.Namespace) -> int:
    """Diagnose project health."""
    return doctor_command.doctor_command(args)


def _handle_explain(args: argparse.Namespace) -> int:
    """Explain doctor/validation failures."""
    runner = explain.ExplainRunner()
    code, output = runner.run(
        world=getattr(args, "world", None),
        last=bool(getattr(args, "last", False)),
        json_output=bool(getattr(args, "json", False)),
    )
    print(output, end="")
    return int(code)


def _handle_cli_smoke(args: argparse.Namespace) -> int:
    """Run a quick smoke test of the CLI tools."""
    commands = [
        ["doctor", "--json"],
        ["docs", "--verify"],
        ["cli-snapshot", "--verify", "--out", "docs/generated/cli_snapshot.json"],
        ["plan", "schema", "--verify", "--out", "docs/generated/plan_schema.json"]
    ]

    print("[Mesh][Smoke] Running CLI smoke tests...")
    failed = False
    for cmd in commands:
        print(f"[Mesh][Smoke] Running: mesh {' '.join(cmd)}")
        res = subprocess.run([sys.executable, "mesh_cli.py"] + cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[Mesh][Smoke] FAILED: {' '.join(cmd)}")
            print(res.stdout)
            print(res.stderr)
            failed = True
        else:
            print(f"[Mesh][Smoke] PASSED: {' '.join(cmd)}")

    return 1 if failed else 0
