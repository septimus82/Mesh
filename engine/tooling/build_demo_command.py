import argparse
import shutil
import time
from pathlib import Path

from engine import json_io
from engine.tooling import check, polish
from mesh_cli.version_info import get_tool_version


def handle_build_demo(args: argparse.Namespace) -> int:
    print("[Mesh][Build] Starting demo build...")

    # 1. Quality Gate
    print("[Mesh][Build] Running quality gate...")
    if not check.run_check(full=True, check_refs=True):
        print("[Mesh][Build] Quality gate failed. Aborting.")
        return 1

    # 1.5 Content Audit (Warning Mode)
    print("[Mesh][Build] Auditing content usage...")
    from engine.config import load_config
    from engine.content_audit import audit_world

    config = load_config()
    audit_policy = config.audit_policy

    # Use config for ignore/allow
    ignore_patterns = audit_policy.get("ignore", [])
    allow_packs = audit_policy.get("allow_packs", [])

    audit_report = audit_world(world_path="worlds/main_world.json", ignore_patterns=ignore_patterns, allow_packs=allow_packs)
    stats = audit_report["stats"]

    unused_count = stats["unused_assets_count"]
    max_unused = audit_policy.get("max_unused_assets", 0)

    failed = False
    if unused_count > max_unused:
        msg = f"Found {unused_count} unused assets (Limit: {max_unused})."
        if args.strict_audit:
            print(f"[Mesh][Build] FAILURE: {msg}")
            failed = True
        else:
            print(f"[Mesh][Build] WARNING: {msg}")

    # Check other types
    for key in ["unused_prefabs_count", "unused_items_count", "unused_quests_count"]:
        limit_key = key.replace("_count", "").replace("unused_", "max_unused_")
        limit = audit_policy.get(limit_key, 0)

        if stats[key] > limit:
             msg = f"Found {stats[key]} {key.replace('_count', '').replace('_', ' ')} (Limit: {limit})."
             if args.strict_audit:
                 print(f"[Mesh][Build] FAILURE: {msg}")
                 failed = True
             else:
                 print(f"[Mesh][Build] WARNING: {msg}")

    if failed:
        print("[Mesh][Build] Strict audit failed. Aborting.")
        return 1
    else:
        if unused_count == 0 and all(stats[k] == 0 for k in ["unused_prefabs_count", "unused_items_count", "unused_quests_count"]):
            print("[Mesh][Build] Content audit clean.")

    # 2. Polish World
    world_path = "worlds/main_world.json" # Default for now
    print(f"[Mesh][Build] Polishing world: {world_path}")
    # polish.main returns 0 on success
    if polish.main(world_path, compact_scenes=True, export_graph_path="dist/demo_world.dot") != 0:
        print("[Mesh][Build] Polish failed. Aborting.")
        return 1

    # 3. Copy Content
    dist_dir = Path("dist/demo_content")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    # Copy essential folders
    # We should probably use a manifest or config for this
    folders_to_copy = ["assets", "scenes", "worlds", "engine"] # Engine needed? Maybe just content.
    # If we are building a standalone, we need engine. If just content pack, no.
    # "Copies required content into dist/demo_content/"

    for folder in folders_to_copy:
        src = Path(folder)
        if src.exists():
            shutil.copytree(src, dist_dir / folder)

    # Copy config
    if Path("config.json").exists():
        shutil.copy("config.json", dist_dir / "config.json")

    # 4. Manifest & Lockfile
    from engine.content_lock import build_lock, compute_content_fingerprint, write_lock

    print("[Mesh][Build] Generating lockfile and fingerprint...")
    lock_data = build_lock(world_path)
    write_lock(dist_dir / "content.lock.json", lock_data)

    fingerprint = compute_content_fingerprint(lock_data)
    print(f"[Mesh][Build] Content Fingerprint: {fingerprint[:12]}")
    manifest = {
        "build_timestamp": time.time(),
        "engine_version": get_tool_version(),
        "world_id": "main_world",
        "content_fingerprint": fingerprint,
        "audit_summary": {
            "unused_assets": audit_report["stats"]["unused_assets_count"],
            "unused_prefabs": audit_report["stats"]["unused_prefabs_count"],
            "unused_items": audit_report["stats"]["unused_items_count"]
        },
        "schema_versions": {
            "scene": 1,
            "world": 1,
            "trace": 1
        },
        "packs": [
            {
                "id": p["id"],
                "version": p["version"],
                "type": p["type"]
            } for p in lock_data["packs"]
        ]
    }

    # 5. Diff & Changelog (Optional)
    if args.diff_from:
        print(f"[Mesh][Build] Generating changelog from {args.diff_from}...")
        try:
            from engine.content_diff import diff_locks
            from engine.content_lock import read_lock

            old_lock = read_lock(Path(args.diff_from))
            diff = diff_locks(old_lock, lock_data)

            # Write diff JSON
            json_io.write_json_atomic(dist_dir / "content.diff.json", diff)

            # Write Changelog
            lines = ["# Content Changelog", ""]

            # Packs
            p_added = diff["packs"]["added"]
            p_removed = diff["packs"]["removed"]
            p_changed = diff["packs"]["version_changed"]

            if p_added or p_removed or p_changed:
                lines.append("## Pack Changes")
                for p in p_added:
                    lines.append(f"- **Added** `{p['id']}` ({p['version']})")
                for p in p_removed:
                    lines.append(f"- **Removed** `{p['id']}` ({p['version']})")
                for p in p_changed:
                    lines.append(f"- **Updated** `{p['id']}`: {p['old']} -> {p['new']}")
                lines.append("")

            # Content Files
            cf_changed = diff["content_files"]["changed"]
            cf_added = diff["content_files"]["added"]
            cf_removed = diff["content_files"]["removed"]

            if cf_changed or cf_added or cf_removed:
                lines.append("## Asset Changes")
                for f in cf_added:
                    lines.append(f"- Added: `{f}`")
                for f in cf_removed:
                    lines.append(f"- Removed: `{f}`")
                for f in cf_changed:
                    lines.append(f"- Modified: `{f}`")
                lines.append("")

            (dist_dir / "content.changelog.md").write_text("\n".join(lines), encoding="utf-8")

            manifest["changelog"] = "content.changelog.md"
            manifest["diff"] = "content.diff.json"

        except Exception as e:
            print(f"[Mesh][Build] WARNING: Failed to generate changelog: {e}")

    json_io.write_json_atomic(dist_dir / "build_manifest.json", manifest)

    print(f"[Mesh][Build] Demo build complete in {dist_dir}")
    return 0

def add_build_demo_command(subparsers) -> None:
    """Register the build-demo command."""
    parser = subparsers.add_parser("build-demo", help="Build the demo content pack")
    parser.add_argument("--diff-from", help="Path to old lockfile for changelog generation")
    parser.add_argument("--strict-audit", action="store_true", help="Fail build if audit thresholds are exceeded")
    parser.set_defaults(func=handle_build_demo)
