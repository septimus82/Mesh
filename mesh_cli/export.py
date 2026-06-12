"""Export bundle commands for Mesh CLI.

Commands:
    mesh_cli export build   - Build a shippable bundle
    mesh_cli export plan    - Preview what would be included
    mesh_cli export diff    - Compare two bundles
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.persistence_io import write_json_atomic


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register export commands."""
    export_parser = subparsers.add_parser(
        "export",
        help="Export bundle utilities",
        description="Build and manage shippable bundles",
    )
    export_subparsers = export_parser.add_subparsers(
        dest="export_command",
        help="Export subcommand",
    )

    # build
    build_parser = export_subparsers.add_parser(
        "build",
        help="Build a shippable bundle",
        description="Build a deterministic export bundle with only required assets",
    )
    build_parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory",
    )
    build_parser.add_argument(
        "--out",
        default="dist/bundle",
        help="Output directory for the bundle",
    )
    build_parser.add_argument(
        "--include-unused",
        action="store_true",
        help="Include all assets, not just referenced ones",
    )
    build_parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Don't fail on missing dependencies",
    )
    build_parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Write deterministic manifest metadata (no wall-clock timestamps)",
    )

    # plan
    plan_parser = export_subparsers.add_parser(
        "plan",
        help="Preview export plan",
        description="Print what would be included in the bundle without building",
    )
    plan_parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory",
    )
    plan_parser.add_argument(
        "--include-unused",
        action="store_true",
        help="Include all assets in the plan",
    )
    plan_parser.add_argument(
        "--json",
        action="store_true",
        help="Output plan as JSON",
    )
    plan_parser.add_argument(
        "--list-files",
        action="store_true",
        help="List all files to be included",
    )
    plan_parser.add_argument(
        "--list-excluded",
        action="store_true",
        help="List excluded (unused) assets",
    )
    plan_parser.add_argument(
        "--out",
        help="Write plan to JSON file",
    )

    # diff
    diff_parser = export_subparsers.add_parser(
        "diff",
        help="Compare two bundles",
        description="Compare two export bundles and show differences",
    )
    diff_parser.add_argument(
        "--bundle-a",
        required=True,
        help="First bundle directory (baseline)",
    )
    diff_parser.add_argument(
        "--bundle-b",
        required=True,
        help="Second bundle directory (comparison)",
    )
    diff_parser.add_argument(
        "--json",
        action="store_true",
        help="Output diff as JSON",
    )
    diff_parser.add_argument(
        "--out",
        help="Write diff to JSON file",
    )


def handle(args: argparse.Namespace) -> int:
    """Handle export commands."""
    export_cmd = getattr(args, "export_command", None)

    if export_cmd == "build":
        return _handle_export_build(args)
    if export_cmd == "plan":
        return _handle_export_plan(args)
    if export_cmd == "diff":
        return _handle_export_diff(args)

    print("[Mesh][CLI] Error: missing export subcommand")
    return 2


def _handle_export_build(args: argparse.Namespace) -> int:
    """Handle export build command."""
    from tooling.export_bundle import build_bundle

    repo_root = Path(str(getattr(args, "repo_root", ".") or ".")).resolve()
    out_raw = str(getattr(args, "out", "") or "dist/bundle")
    output_dir = Path(out_raw)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    include_unused = bool(getattr(args, "include_unused", False))
    fail_on_missing = not bool(getattr(args, "allow_missing", False))
    deterministic = bool(getattr(args, "deterministic", False))

    print(f"[Mesh][Export] building bundle from {repo_root}...")

    exit_code, manifest = build_bundle(
        repo_root,
        output_dir,
        include_unused=include_unused,
        fail_on_missing=fail_on_missing,
        deterministic=deterministic,
    )

    if exit_code == 0 and manifest is not None:
        print(f"[Mesh][Export] OK ({manifest.file_count} files, {manifest.total_size:,} bytes)")
        print(f"[Mesh][Export] wrote bundle to {output_dir}")

    return exit_code


def _handle_export_plan(args: argparse.Namespace) -> int:
    """Handle export plan command."""
    from tooling.export_bundle import compute_export_plan

    repo_root = Path(str(getattr(args, "repo_root", ".") or ".")).resolve()
    include_unused = bool(getattr(args, "include_unused", False))
    output_json = bool(getattr(args, "json", False))
    list_files = bool(getattr(args, "list_files", False))
    list_excluded = bool(getattr(args, "list_excluded", False))
    out_path_raw = getattr(args, "out", None)

    print(f"[Mesh][Export] computing plan for {repo_root}...")

    plan = compute_export_plan(repo_root, include_unused=include_unused)
    print(plan.summary())

    if list_files:
        print("\nFiles to include:")
        for f in plan.files:
            print(f"  {f.category:8s} {f.rel_path}")

    if list_excluded and plan.excluded_assets:
        print("\nExcluded assets (unused):")
        for asset in plan.excluded_assets:
            print(f"  - {asset}")

    if output_json:
        import json
        print("\nJSON output:")
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))

    if out_path_raw:
        out_path = Path(out_path_raw)
        if not out_path.is_absolute():
            out_path = repo_root / out_path
        write_json_atomic(out_path, plan.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
        print(f"\n[Mesh][Export] wrote plan to {out_path}")

    return 0 if plan.ok else 1


def _handle_export_diff(args: argparse.Namespace) -> int:
    """Handle export diff command."""
    from tooling.export_bundle import diff_bundles

    bundle_a = Path(str(getattr(args, "bundle_a", ""))).resolve()
    bundle_b = Path(str(getattr(args, "bundle_b", ""))).resolve()
    output_json = bool(getattr(args, "json", False))
    out_path_raw = getattr(args, "out", None)

    if not bundle_a.is_dir():
        print(f"[Mesh][Export] ERROR: bundle_a not found: {bundle_a}")
        return 1

    if not bundle_b.is_dir():
        print(f"[Mesh][Export] ERROR: bundle_b not found: {bundle_b}")
        return 1

    print("[Mesh][Export] comparing bundles...")
    print(f"  A: {bundle_a}")
    print(f"  B: {bundle_b}")

    diff = diff_bundles(bundle_a, bundle_b)
    print(diff.summary())

    if output_json:
        import json
        print("\nJSON output:")
        print(json.dumps(diff.to_dict(), indent=2, sort_keys=True))

    if out_path_raw:
        out_path = Path(out_path_raw)
        write_json_atomic(out_path, diff.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
        print(f"\n[Mesh][Export] wrote diff to {out_path}")

    # Return 0 if identical, 1 if different
    return 0 if not diff.has_changes else 1
