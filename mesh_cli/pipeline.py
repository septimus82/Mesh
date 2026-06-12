"""Pipeline & Preset commands for Mesh Engine."""

import argparse

from engine.tooling import (
    pipeline_runner,
    preset_commands,
    recipes_command,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    # Pipeline
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Apply plan, validate, and optionally run demo/preset",
        description="Apply plan, validate, and optionally run demo/preset",
    )
    pipeline_parser.add_argument("plan_path", nargs="?", help="Path to plan file")
    pipeline_parser.add_argument("path", nargs="?", help="Path to world or scene file to validate")
    pipeline_parser.add_argument("--plan", dest="plan_path_opt", help="Path to plan file")
    pipeline_parser.add_argument("--world", dest="path_opt", help="World/scene path to validate")
    pipeline_parser.add_argument("--ai-safe", action="store_true", help="Use AI-safe apply-plan path")
    pipeline_parser.add_argument("--dry-run", action="store_true", help="Dry run apply-plan (no writes)")
    pipeline_parser.add_argument("--strict", action="store_true", help="Pass --strict to validate-all")
    pipeline_parser.add_argument("--strict-compact", action="store_true", help="Pass --strict-compact to validate-all")
    pipeline_parser.add_argument("--check-reachability", action="store_true", help="Pass --check-reachability to validate-all")
    pipeline_parser.add_argument("--check-orphans", action="store_true", help="Pass --check-orphans to validate-all")
    pipeline_parser.add_argument("--check-refs", action="store_true", help="Pass --check-refs to validate-all")
    pipeline_run = pipeline_parser.add_mutually_exclusive_group()
    pipeline_run.add_argument("--demo", action="store_true", help="Run demo after validation")
    pipeline_run.add_argument("--preset", help="Run a preset after validation")

    # Recipes
    recipes_parser = subparsers.add_parser(
        "recipes",
        help="Show workflow recipes",
        description="Show workflow recipes",
    )

    # Run Preset
    preset_parser = subparsers.add_parser(
        "run-preset",
        help="Run a command preset",
        description="Run a command preset",
    )
    preset_parser.add_argument("name", help="Preset name")

    # Preset Management
    preset_group_parser = subparsers.add_parser(
        "preset",
        help="Preset management",
        description="Preset management",
    )
    preset_subparsers = preset_group_parser.add_subparsers(dest="preset_command", help="Preset commands")

    # Preset Lint
    preset_subparsers.add_parser(
        "lint",
        help="Lint presets in config",
        description="Lint presets in config",
    )


def handle(args: argparse.Namespace) -> int:
    if args.command == "pipeline":
        return _handle_pipeline(args)
    if args.command == "recipes":
        return _handle_recipes(args)
    if args.command == "run-preset":
        return _handle_run_preset(args)
    if args.command == "preset":
        return _handle_preset(args)
    return 1


def _handle_pipeline(args: argparse.Namespace) -> int:
    plan_path = args.plan_path or getattr(args, "plan_path_opt", None)
    target_path = args.path or getattr(args, "path_opt", None)
    if not plan_path or not target_path:
        print("[PIPELINE] Missing required --plan and --world/path.")
        return 1

    result = pipeline_runner.run_pipeline(
        plan_path=plan_path,
        path=target_path,
        ai_safe=bool(args.ai_safe),
        dry_run=bool(args.dry_run),
        strict=bool(args.strict),
        strict_compact=bool(args.strict_compact),
        check_reachability=bool(args.check_reachability),
        check_orphans=bool(args.check_orphans),
        check_refs=bool(getattr(args, "check_refs", False)),
        demo=bool(getattr(args, "demo", False)),
        preset=getattr(args, "preset", None),
    )
    return int(result) if isinstance(result, int) else 0


def _handle_recipes(args: argparse.Namespace) -> int:
    recipes_command.recipes_command(args)
    return 0


def _handle_run_preset(args: argparse.Namespace) -> int:
    preset_commands.run_preset_command(args)
    return 0


def _handle_preset(args: argparse.Namespace) -> int:
    if getattr(args, "preset_command", None) == "lint":
        result = preset_commands.run_preset_lint_command(args)
        return int(result) if isinstance(result, int) else 0
    print("[Mesh][CLI] Error: missing preset subcommand")
    return 2
