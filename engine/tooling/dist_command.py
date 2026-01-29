import argparse
import json
import shutil
from pathlib import Path

from engine import json_io
from engine.tooling import build_demo_command, check, cli_snapshot_command, plan_schema_command, release_command
from engine.version import ENGINE_VERSION


def handle_dist(args: argparse.Namespace) -> int:
    dist_dir = Path(args.out) if args.out else Path("dist") / f"mesh_dist_{ENGINE_VERSION}"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    print(f"[Mesh][Dist] Building distribution v{ENGINE_VERSION} to {dist_dir}...")

    # 1. Quality Gate (Full)
    print("\n[Mesh][Dist] Step 1/6: Quality Gate")
    if not check.run_check(full=True):
        print("[Mesh][Dist] Quality gate failed.")
        return 1

    # 2. Release Check
    print("\n[Mesh][Dist] Step 2/6: Release Check")
    # Construct args for release check
    release_args = argparse.Namespace(
        profile=args.profile,
        world_path=args.world,
        baseline="auto",
        max_unused_assets=None,
        max_unused_prefabs=None,
        max_unused_items=None,
        max_unused_quests=None,
        ignore=None,
        allow_packs=None,
        max_unused_delta=None,
        diff_from=None,
        emit_changelog=None,
        require_golden_replays=None
    )
    try:
        release_command.release_check_command(release_args)
    except SystemExit as e:
        if e.code != 0:
            print("[Mesh][Dist] Release check failed.")
            return 1

    # 3. Build Demo
    print("\n[Mesh][Dist] Step 3/6: Build Demo")
    build_args = argparse.Namespace(
        strict_audit=True,
        diff_from=None
    )
    if build_demo_command.handle_build_demo(build_args) != 0:
        print("[Mesh][Dist] Build demo failed.")
        return 1

    # Move demo content
    demo_src = Path("dist/demo_content")
    if demo_src.exists():
        # If dist_dir/demo_content exists, remove it first (though we cleaned dist_dir)
        shutil.move(str(demo_src), str(dist_dir / "demo_content"))

    # 4. CLI Snapshot
    print("\n[Mesh][Dist] Step 4/6: CLI Snapshot")
    cli_out = dist_dir / "cli_snapshot.json"
    cli_args = argparse.Namespace(
        out=str(cli_out),
        verify=False
    )
    try:
        cli_snapshot_command.cli_snapshot_command(cli_args)
    except SystemExit as e:
        if e.code != 0:
            print("[Mesh][Dist] CLI snapshot generation failed.")
            return 1

    # 5. Plan Schema
    print("\n[Mesh][Dist] Step 5/6: Plan Schema")
    schema_out = dist_dir / "plan_schema.json"
    schema_args = argparse.Namespace(
        out=str(schema_out),
        verify=False
    )
    try:
        plan_schema_command.plan_schema_command(schema_args)
    except SystemExit as e:
        if e.code != 0:
            print("[Mesh][Dist] Plan schema generation failed.")
            return 1

    # Copy content.lock.json
    if Path("content.lock.json").exists():
        shutil.copy("content.lock.json", dist_dir / "content.lock.json")

    # 6. Demo Notes
    if args.profile == "demo_v0_3":
        print("\n[Mesh][Dist] Step 6/6: Generating Demo Notes")
        notes = """# Mesh Engine Demo v0.3

## Controls
- **WASD**: Move
- **SPACE**: Attack / Interact
- **Q**: Quest Log
- **I**: Inventory
- **C**: Character Sheet

## Regions Included
- Ridge Outpost (Hub, Interior, Dungeon)
- Hollow Grove (Hub, Interior, Dungeon)
- Ashen (Hub, Interior, Dungeon)

## Quest Types
- Fetch (Ridge)
- Kill (Ridge, Ashen)
- Exploration (Hollow)

## Suggested Path
1. Talk to the Guide in Ridge Outpost.
2. Accept the supply quest from the Merchant.
3. Explore the Ridge Dungeon to find supplies.
4. Return to Merchant.
5. Travel to Hollow Grove via the World Map (if enabled) or Exits.
"""
        (dist_dir / "demo_notes.md").write_text(notes, encoding="utf-8")

    # Create Dist Manifest
    dist_manifest = {
        "engine_version": ENGINE_VERSION,
        "profile": args.profile,
        "world": args.world,
        "components": [
            "demo_content",
            "cli_snapshot.json",
            "plan_schema.json",
            "content.lock.json"
        ]
    }

    json_io.write_json_atomic(dist_dir / "dist_manifest.json", dist_manifest)

    print(f"\n[Mesh][Dist] Distribution complete: {dist_dir}")
    return 0

def add_dist_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", required=True, help="Release profile")
    parser.add_argument("--world", required=True, help="World file to build")
    parser.add_argument("--out", help="Output directory")

def add_dist_command(subparsers) -> None:
    parser = subparsers.add_parser("dist", help="Build a distribution release")
    add_dist_arguments(parser)
    parser.set_defaults(func=handle_dist)
