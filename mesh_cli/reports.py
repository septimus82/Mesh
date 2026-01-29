"""Report commands for Mesh Engine."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from engine.encounter_report_diff import diff_reports, load_report
from engine.logging_tools import suppress_stdout
from engine.persistence_io import dumps_json_deterministic, write_json_atomic


def register(subparsers: argparse._SubParsersAction) -> None:
    # Encounter Report
    encounter_report_parser = subparsers.add_parser(
        "encounter-report",
        help="Generate encounter balance report",
        description="Generate encounter balance report",
    )
    encounter_report_parser.add_argument("path", nargs="+", help="World file, scene file, directory, or 'diff <old> <new>'")
    encounter_report_parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    encounter_report_parser.add_argument("--out", help="Output file path")
    encounter_report_parser.add_argument("--themes", help="Comma-separated list of themes to filter")
    encounter_report_parser.add_argument("--difficulty", help="Comma-separated list of difficulties (default: easy,normal,hard)")
    encounter_report_parser.add_argument("--only-dungeons", action="store_true", help="Only process dungeon scenes")
    encounter_report_parser.add_argument("--max-elite-delta", type=int, help="Fail if elite count delta exceeds this")
    encounter_report_parser.add_argument("--max-spawn-delta", type=int, help="Fail if spawn count delta exceeds this")
    encounter_report_parser.add_argument("--max-cost-overrun", type=float, help="Fail if cost overrun exceeds this")
    encounter_report_parser.add_argument("--fail-on-overrun", action="store_true", help="Fail if any cost overrun increases")

    # Drift Check
    drift_check_parser = subparsers.add_parser(
        "drift-check",
        help="Run encounter drift check with presets",
        description="Run encounter drift check with presets",
    )
    drift_check_parser.add_argument("preset", help="Preset name (strict, standard, lenient)")
    drift_check_parser.add_argument("old_path", help="Baseline report or file")
    drift_check_parser.add_argument("new_path", help="New report or file")
    drift_check_parser.add_argument("--json", action="store_true", help="Output JSON")
    drift_check_parser.add_argument("--out", help="Output file path")


def handle(args: argparse.Namespace) -> int:
    if args.command == "encounter-report":
        return _handle_encounter_report(args)
    # if args.command == "drift-check":
    #     return _handle_drift_check(args)
    return 1


def _resolve_scene_paths(path: str) -> list[str]:
    scene_paths = []
    if path.endswith(".json"):
        # Check if it's a world file
        try:
            with open(path, "r") as f:
                data = json.load(f)
                scenes = data.get("scenes") if isinstance(data, dict) else None
                if isinstance(scenes, list):
                    # It's a world file
                    for s in scenes:
                        if isinstance(s, dict) and "path" in s:
                            scene_paths.append(s["path"])
                        elif isinstance(s, str):
                            scene_paths.append(s)
                elif isinstance(scenes, dict):
                    for scene_id in sorted(scenes.keys()):
                        s = scenes.get(scene_id)
                        if isinstance(s, dict) and "path" in s:
                            scene_paths.append(s["path"])
                        elif isinstance(s, str):
                            scene_paths.append(s)
                else:
                    # Assume it's a single scene
                    scene_paths.append(path)
        except Exception as e:
            print(f"Error reading {path}: {e}")
            return []
    elif os.path.isdir(path):
        # Walk directory
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".json"):
                    scene_paths.append(os.path.join(root, file))
    else:
        print(f"Invalid path: {path}")
        return []
    return sorted(scene_paths)


def _process_diff_result(diff, args: argparse.Namespace) -> int:
    # Output
    if args.json or args.out:
        output_data = asdict(diff)
        if args.out:
            out_path = Path(args.out)
            write_json_atomic(out_path, output_data)
            print(f"Diff report written to {out_path}")
        else:
            print(json.dumps(output_data, indent=2, sort_keys=True))
    else:
        # Text summary
        print(f"Encounter Diff: {len(diff.scene_diffs)} scenes compared")

    # Check thresholds
    from engine.encounter_report_diff import check_thresholds

    errors = check_thresholds(
        diff,
        max_elite_delta=args.max_elite_delta,
        max_spawn_delta=args.max_spawn_delta,
        max_cost_overrun=args.max_cost_overrun,
        fail_on_overrun=args.fail_on_overrun
    )

    if errors:
        print("\n[Encounter Diff] Thresholds Exceeded:")
        for error in errors[:5]:
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more.")
        return 1

    return 0


def _handle_encounter_diff(old_path: str, new_path: str, args: argparse.Namespace) -> int:
    from . import legacy_impl as legacy_mod

    try:
        old_report = legacy_mod.load_report(old_path)
        new_report = legacy_mod.load_report(new_path)
    except Exception as e:
        print(f"Error loading reports: {e}")
        return 1

    diff = legacy_mod.diff_reports(old_report, new_report)
    return legacy_mod._process_diff_result(diff, args)


def _handle_encounter_compare(baseline_path: str, target_path: str, args: argparse.Namespace) -> int:
    from . import legacy_impl as legacy_mod

    scene_paths = legacy_mod._resolve_scene_paths(target_path)
    if not scene_paths:
        return 1

    difficulties = args.difficulty.split(",") if args.difficulty else None
    themes = args.themes.split(",") if args.themes else None

    new_report = legacy_mod.generate_encounter_report(
        scene_paths=scene_paths,
        difficulties=difficulties,
        theme_filter=themes,
        only_dungeons=args.only_dungeons
    )

    try:
        old_report = load_report(baseline_path)
    except Exception as e:
        print(f"Error loading baseline {baseline_path}: {e}")
        return 1

    diff = diff_reports(old_report, new_report)
    return _process_diff_result(diff, args)


def _handle_encounter_report(args: argparse.Namespace) -> int:
    """Generate an encounter balance report."""
    from . import legacy_impl as legacy_mod

    paths = args.path

    if paths[0] == "diff":
        if len(paths) < 3:
            print("Usage: mesh encounter-report diff <old.json> <new.json>")
            return 1
        return _handle_encounter_diff(paths[1], paths[2], args)

    if paths[0] == "compare":
        if len(paths) < 3:
            print("Usage: mesh encounter-report compare <baseline.json> <world_or_scenes>")
            return 1
        return _handle_encounter_compare(paths[1], paths[2], args)

    path = paths[0]

    scene_paths = legacy_mod._resolve_scene_paths(path)
    if not scene_paths:
        return 1

    difficulties = args.difficulty.split(",") if args.difficulty else None
    themes = args.themes.split(",") if args.themes else None

    if args.json or args.out:
        with suppress_stdout():
            report = legacy_mod.generate_encounter_report(
                scene_paths=scene_paths,
                difficulties=difficulties,
                theme_filter=themes,
                only_dungeons=args.only_dungeons,
            )
            output_data = asdict(report)

            if args.out:
                write_json_atomic(Path(args.out), output_data, indent=2, sort_keys=True, trailing_newline=True)

        sys.stdout.write(dumps_json_deterministic(output_data, indent=2, sort_keys=True, trailing_newline=True))
        return 0

    report = legacy_mod.generate_encounter_report(
        scene_paths=scene_paths,
        difficulties=difficulties,
        theme_filter=themes,
        only_dungeons=args.only_dungeons,
    )

    # Output
    # Text summary
    print(f"Encounter Report for {len(report.scenes)} scenes")
    # Print summary stats
    total_spawns = sum(s.spawn_count for s in report.scenes)
    total_elites = sum(s.elite_count for s in report.scenes)
    print(f"  Total Spawns: {total_spawns}")
    print(f"  Total Elites: {total_elites}")

    return 0
