"""CLI commands for content pack management."""

import argparse
import fnmatch
import json
from pathlib import Path

from engine.content_audit import audit_world
from engine.content_lock import build_lock, read_lock, write_lock
from engine.content_packs import validate_pack_dependencies
from engine.paths import get_content_index, get_content_roots


def init_content_pack_command(args: argparse.Namespace) -> None:
    """Initialize a new content pack."""
    pack_id = args.pack_id

    # Find a writable root
    roots = get_content_roots()
    if not roots:
        print("[Mesh][Init] ERROR: No content roots configured.")
        return

    # Use first root by default
    target_root = roots[0]
    pack_dir = target_root / pack_id

    if pack_dir.exists():
        print(f"[Mesh][Init] ERROR: Pack directory '{pack_dir}' already exists.")
        return

    print(f"[Mesh][Init] Creating pack '{pack_id}' in {target_root}...")

    try:
        pack_dir.mkdir(parents=True)
        (pack_dir / "scenes").mkdir()
        (pack_dir / "assets").mkdir()
        (pack_dir / "assets" / "audio").mkdir()

        manifest = {
            "id": pack_id,
            "name": pack_id.replace("_", " ").title(),
            "version": "0.1.0",
            "type": args.type,
            "wip": args.wip,
            "overrides": [],
            "requires": []
        }

        (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print(f"[Mesh][Init] Pack initialized successfully at {pack_dir}")

    except Exception as e:
        print(f"[Mesh][Init] ERROR: Failed to create pack: {e}")

def validate_packs_command(args: argparse.Namespace) -> None:
    """Validate pack manifests, dependencies, and override intent."""
    print("[Mesh][Packs] Validating content packs...")

    index = get_content_index(refresh=True)
    index.build()

    packs = index.packs

    # 1. Dependency Check
    dep_errors = validate_pack_dependencies(packs)
    if dep_errors:
        print("\nDependency Errors:")
        for err in dep_errors:
            print(f"  [ERR] {err}")
    else:
        print("  Dependencies: OK")

    # 2. Override Intent Check
    print("\nChecking override intent...")
    override_warnings = []
    override_errors = []

    pack_map = {p.id: p for p in packs}
    pack_stats = {} # pack_id -> {total: 0, undeclared: 0}

    # Scan all indexed entries for shadowing
    for key, entry in index.entries.items():
        if not entry.shadowed_pack_ids:
            continue

        # The active pack is providing_pack_id
        active_pack = pack_map.get(entry.providing_pack_id)
        if not active_pack:
            continue

        if active_pack.id not in pack_stats:
            pack_stats[active_pack.id] = {"total": 0, "undeclared": 0}

        pack_stats[active_pack.id]["total"] += 1

        # If active pack is implicit or core, maybe we don't care?
        # But if it's a mod, it should declare overrides.
        if active_pack.type == "core":
            continue

        # Check if this key is covered by 'overrides' globs
        declared = False
        for pattern in active_pack.overrides:
            if fnmatch.fnmatch(key, pattern):
                declared = True
                break

        if not declared:
            pack_stats[active_pack.id]["undeclared"] += 1
            msg = f"Pack '{active_pack.id}' overrides '{key}' but does not declare it in manifest."
            if args.strict_overrides:
                override_errors.append(msg)
            else:
                override_warnings.append(msg)

    if pack_stats:
        print("\nOverride Summary:")
        for pid, stats in pack_stats.items():
            print(f"  Pack '{pid}': {stats['total']} overrides ({stats['undeclared']} undeclared)")
    else:
        print("\nOverride Summary: No overrides found.")

    if override_warnings:
        print("\nOverride Warnings (Undeclared):")
        for w in override_warnings:
            print(f"  [WARN] {w}")

    if override_errors:
        print("\nOverride Errors (Undeclared):")
        for e in override_errors:
            print(f"  [ERR] {e}")

    if dep_errors or override_errors:
        print("\n[Mesh][Packs] Validation FAILED.")
        exit(1)
    else:
        print("\n[Mesh][Packs] Validation PASSED.")

def list_packs_command(args: argparse.Namespace) -> None:
    """List loaded packs in priority order."""
    index = get_content_index(refresh=True)
    index.build()

    print(f"[Mesh][Packs] Loaded {len(index.packs)} packs (Priority Order):")
    for i, pack in enumerate(index.packs):
        meta = []
        if pack.is_implicit:
            meta.append("implicit")
        if pack.type != "mod":
            meta.append(pack.type)

        meta_str = f" ({', '.join(meta)})" if meta else ""
        print(f"  {i+1}. {pack.name} [{pack.version}] ({pack.id}){meta_str}")
        print(f"     Root: {pack.root}")
        if pack.requires:
            reqs = [r.id for r in pack.requires]
            print(f"     Requires: {', '.join(reqs)}")

def lock_packs_command(args: argparse.Namespace) -> None:
    """Generate a content lockfile."""
    out_path = Path(args.out) if args.out else Path("content.lock.json")

    if args.update_audit_snapshot:
        print("[Mesh][Lock] Updating audit snapshot only...")
        if not out_path.exists():
            print(f"[Mesh][Lock] ERROR: Lockfile '{out_path}' does not exist. Cannot update snapshot.")
            return

        try:
            lock_data = read_lock(out_path)
            # Re-run audit
            # Assuming main_world.json as default for now, similar to build_lock default
            # Ideally we should get this from config or args, but build_lock defaults to it.
            print("  Running audit...")
            report = audit_world("worlds/main_world.json")
            lock_data["audit_snapshot"] = report["stats"]

            write_lock(out_path, lock_data)
            print(f"[Mesh][Lock] Updated audit snapshot in {out_path}")
            return
        except Exception as e:
            print(f"[Mesh][Lock] ERROR: Failed to update snapshot: {e}")
            return

    print("[Mesh][Lock] Generating content lockfile...")

    lock_data = build_lock()

    write_lock(out_path, lock_data)

    pack_count = len(lock_data["packs"])
    override_count = len(lock_data["overrides"])

    print(f"[Mesh][Lock] Wrote lockfile to {out_path}")
    print(f"  Packs: {pack_count}")
    print(f"  Overrides: {override_count}")

def add_pack_commands(subparsers) -> None:
    """Register pack commands."""

    # validate-packs
    parser_val = subparsers.add_parser("validate-packs", help="Validate content packs")
    parser_val.add_argument("--strict-overrides", action="store_true", help="Fail on undeclared overrides")
    parser_val.set_defaults(func=validate_packs_command)

    # packs
    parser_list = subparsers.add_parser("packs", help="List loaded packs")
    parser_list.set_defaults(func=list_packs_command)

    # lock-packs
    parser_lock = subparsers.add_parser("lock-packs", help="Generate content lockfile")
    parser_lock.add_argument("--out", help="Output path (default: content.lock.json)")
    parser_lock.add_argument("--update-audit-snapshot", action="store_true", help="Only update the audit snapshot in existing lockfile")
    parser_lock.set_defaults(func=lock_packs_command)

    # init-content-pack
    parser_init = subparsers.add_parser("init-content-pack", help="Initialize a new content pack")
    parser_init.add_argument("pack_id", help="ID of the new pack")
    parser_init.add_argument("--type", choices=["mod", "dlc", "demo", "test"], default="mod", help="Pack type")
    parser_init.add_argument("--wip", action="store_true", help="Mark pack as Work In Progress")
    parser_init.set_defaults(func=init_content_pack_command)
    parser_list.set_defaults(func=list_packs_command)
