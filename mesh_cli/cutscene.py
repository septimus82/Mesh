"""Cutscene commands for Mesh Engine CLI.

Commands:
    mesh_cli cutscene simulate - Simulate cutscene script execution
    mesh_cli cutscene validate - Validate cutscene script file
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engine.persistence_io import dumps_json_deterministic, write_json_atomic


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register cutscene commands."""
    # Cutscene simulate
    simulate_parser = subparsers.add_parser(
        "cutscene-simulate",
        help="Simulate cutscene script execution",
        description="Run a deterministic cutscene simulation with a dt schedule",
    )
    simulate_parser.add_argument("--script", required=True, help="Path to cutscene script JSON")
    simulate_parser.add_argument(
        "--dt",
        type=str,
        default="0.0",
        help="Comma-separated dt values (e.g., '0.0,0.5,0.5,1.0') or single value repeated",
    )
    simulate_parser.add_argument(
        "--dt-repeat",
        type=int,
        default=1,
        help="Repeat single dt value this many times",
    )
    simulate_parser.add_argument(
        "--flags",
        type=str,
        default="",
        help="Initial flags as JSON object (e.g., '{\"flag1\": true}')",
    )
    simulate_parser.add_argument("--out", help="Optional path to write result JSON")
    simulate_parser.add_argument("--verbose", action="store_true", help="Print step-by-step output")

    # Cutscene validate
    validate_parser = subparsers.add_parser(
        "cutscene-validate",
        help="Validate cutscene script file",
        description="Validate cutscene script JSON file",
    )
    validate_parser.add_argument("path", help="Path to cutscene script JSON")
    validate_parser.add_argument("--out", help="Optional path to write validation result JSON")


def handle(args: argparse.Namespace) -> int:
    """Handle cutscene commands."""
    if args.command == "cutscene-simulate":
        return _handle_simulate(args)
    if args.command == "cutscene-validate":
        return _handle_validate(args)
    return 1


def _parse_dt_schedule(dt_str: str, dt_repeat: int) -> list[float]:
    """Parse dt string into schedule list."""
    if not dt_str:
        return [0.0]
    
    parts = dt_str.split(",")
    schedule: list[float] = []
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            value = float(part)
            schedule.append(value)
        except ValueError:
            continue
    
    if not schedule:
        schedule = [0.0]
    
    # If single value and repeat > 1, repeat it
    if len(schedule) == 1 and dt_repeat > 1:
        schedule = schedule * dt_repeat
    
    return schedule


def _parse_flags(flags_str: str) -> dict[str, bool]:
    """Parse flags JSON string."""
    if not flags_str:
        return {}
    try:
        data = json.loads(flags_str)
        if isinstance(data, dict):
            return {k: bool(v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _handle_simulate(args: argparse.Namespace) -> int:
    """Handle cutscene-simulate command."""
    from engine.cutscene_runtime.runner import simulate_cutscene
    
    script_path = Path(args.script)
    if not script_path.exists():
        result: dict[str, Any] = {
            "ok": False,
            "code": 1,
            "error": "cutscene.script.not_found",
            "message": f"Script file not found: {script_path}",
        }
        sys.stdout.write(dumps_json_deterministic(result, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    
    try:
        with script_path.open("r", encoding="utf-8") as f:
            script = json.load(f)
    except json.JSONDecodeError as e:
        result = {
            "ok": False,
            "code": 1,
            "error": "cutscene.script.invalid_json",
            "message": str(e),
        }
        sys.stdout.write(dumps_json_deterministic(result, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    
    # Parse arguments
    dt_schedule = _parse_dt_schedule(args.dt, args.dt_repeat)
    flags = _parse_flags(args.flags)
    
    # Run simulation
    simulation_result = simulate_cutscene(script, dt_schedule, flags=flags)
    
    # Build output
    output: dict[str, Any] = {
        "ok": simulation_result["ok"],
        "script": str(script_path),
        "dt_schedule": dt_schedule,
        "dt_count": len(dt_schedule),
    }
    
    if simulation_result["ok"]:
        output["final_state"] = simulation_result["final_state"]
        output["step_count"] = len(simulation_result["steps"])
        output["emitted_count"] = len([
            e for e in simulation_result["emitted_events"]
            if e["type"] not in ("cutscene_started", "cutscene_completed", "cutscene_stopped")
        ])
        output["flags"] = simulation_result.get("flags", {})
        
        if args.verbose:
            output["steps"] = simulation_result["steps"]
            output["emitted_events"] = simulation_result["emitted_events"]
    else:
        output["errors"] = simulation_result["errors"]
    
    # Write output
    if args.out:
        write_json_atomic(Path(args.out), output, indent=2, sort_keys=True, trailing_newline=True)
    
    sys.stdout.write(dumps_json_deterministic(output, indent=2, sort_keys=True, trailing_newline=True))
    return 0 if simulation_result["ok"] else 1


def _handle_validate(args: argparse.Namespace) -> int:
    """Handle cutscene-validate command."""
    from engine.cutscene_runtime.schema import (
        migrate_cutscene_script,
        validate_cutscene_script,
    )
    
    script_path = Path(args.path)
    if not script_path.exists():
        result: dict[str, Any] = {
            "ok": False,
            "code": 1,
            "error": "cutscene.script.not_found",
            "message": f"Script file not found: {script_path}",
        }
        sys.stdout.write(dumps_json_deterministic(result, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    
    try:
        with script_path.open("r", encoding="utf-8") as f:
            script = json.load(f)
    except json.JSONDecodeError as e:
        result = {
            "ok": False,
            "code": 1,
            "error": "cutscene.script.invalid_json",
            "message": str(e),
        }
        sys.stdout.write(dumps_json_deterministic(result, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    
    # Migrate
    try:
        script = migrate_cutscene_script(script)
    except ValueError as e:
        result = {
            "ok": False,
            "code": 1,
            "error": "cutscene.migration.failed",
            "message": str(e),
        }
        sys.stdout.write(dumps_json_deterministic(result, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    
    # Validate
    errors = validate_cutscene_script(script, file_path=str(script_path))
    
    result = {
        "ok": len(errors) == 0,
        "script": str(script_path),
        "error_count": len(errors),
        "errors": [
            {
                "file_path": e.file_path,
                "json_path": e.json_path,
                "code": e.code,
                "message": e.message,
                "hint": e.hint,
            }
            for e in errors
        ],
    }
    
    # Write output
    if args.out:
        write_json_atomic(Path(args.out), result, indent=2, sort_keys=True, trailing_newline=True)
    
    sys.stdout.write(dumps_json_deterministic(result, indent=2, sort_keys=True, trailing_newline=True))
    return 0 if result["ok"] else 1
