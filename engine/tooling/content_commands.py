"""CLI commands for content management."""

import argparse
import json
from pathlib import Path

from engine import json_io
from engine.config import load_config
from engine.content_audit import audit_world
from engine.content_diff import diff_locks
from engine.content_lock import build_lock, read_lock
from engine.paths import get_content_index, resolve_path
from engine.paths import reset_path_caches, set_content_roots
from engine.tooling.content_contract import (
    collect_contract_files,
    run_content_contract,
)
from engine.validators.reference_validator import ReferenceValidator
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)



def index_content_command(args: argparse.Namespace) -> None:
    """Build and summarize the content index."""
    print("[Mesh][Index] Building content index...")
    index = get_content_index(refresh=True)
    index.build()

    count = len(index.entries)
    print(f"[Mesh][Index] Indexed {count} files across {len(index.roots)} roots.")

    # Count per root
    by_root: dict[str, int] = {}
    for entry in index.entries.values():
        root_str = str(entry.providing_root)
        by_root[root_str] = by_root.get(root_str, 0) + 1

    for root in index.roots:
        root_str = str(root)
        c = by_root.get(root_str, 0)
        print(f"  - {root}: {c} files")

def list_overrides_command(args: argparse.Namespace) -> None:
    """List assets that are overridden by higher priority roots."""
    print("[Mesh][Index] Scanning for overrides...")
    index = get_content_index(refresh=True)
    index.build()

    overrides = []
    for key, entry in index.entries.items():
        if entry.shadowed_roots:
            overrides.append(entry)

    if not overrides:
        print("[Mesh][Index] No overrides found.")
        return

    print(f"[Mesh][Index] Found {len(overrides)} overridden assets:")
    for entry in sorted(overrides, key=lambda x: x.key):
        print(f"  {entry.key}")
        print(f"    Active:   {entry.providing_root}")
        for shadowed in entry.shadowed_roots:
            print(f"    Shadowed: {shadowed}")

def where_command(args: argparse.Namespace) -> None:
    """Locate an asset and show its resolution details."""
    key = args.asset_key
    print(f"[Mesh][Where] Resolving '{key}'...")

    # Force index build to get full details
    index = get_content_index(refresh=True)
    index.build()

    entry = index.get_entry(key)
    if entry:
        print(f"  Resolved: {entry.resolved_path}")
        print(f"  Root:     {entry.providing_root}")
        if entry.shadowed_roots:
            print("  Shadows:")
            for s in entry.shadowed_roots:
                print(f"    - {s}")
    else:
        # Fallback check
        resolved = resolve_path(key)
        if resolved.exists():
             print(f"  Resolved: {resolved} (Not in index?)")
        else:
             print("  Not found.")


def validate_refs_command(args: argparse.Namespace) -> None:
    """Validate asset references in a world."""
    validator = ReferenceValidator(
        world_path=args.world_path,
        treat_overrides_as_warn=not args.strict_overrides
    )

    success = validator.validate()

    if validator.warnings:
        print("\nWarnings:")
        for w in validator.warnings:
            print(f"  [WARN] {w}")

    if validator.errors:
        print("\nErrors:")
        for e in validator.errors:
            print(f"  [ERR] {e}")

    if not success:
        print("\n[Mesh][Validate] Validation FAILED.")
        exit(1)
    else:
        print("\n[Mesh][Validate] Validation PASSED.")

def diff_content_command(args: argparse.Namespace) -> None:
    """Compare content locks."""
    print("[Mesh][Diff] Comparing content state...")

    # Load 'from' lock
    try:
        old_lock = read_lock(Path(args.old_lock))
    except Exception as e:
        _log_swallow("CTCM-001", "engine/tooling/content_commands.py blanket swallow", once=True)
        print(f"[Mesh][Diff] ERROR: Failed to read old lock '{args.old_lock}': {e}")
        return

    # Load 'to' lock or build current
    if args.new_lock:
        try:
            new_lock = read_lock(Path(args.new_lock))
        except Exception as e:
            _log_swallow("CTCM-002", "engine/tooling/content_commands.py blanket swallow", once=True)
            print(f"[Mesh][Diff] ERROR: Failed to read new lock '{args.new_lock}': {e}")
            return
    else:
        print("[Mesh][Diff] Building current lock state...")
        new_lock = build_lock()

    diff = diff_locks(old_lock, new_lock)

    if args.json:
        print(json.dumps(diff, indent=2))
        return

    # Human readable output
    print("\n=== Content Diff ===")

    # Packs
    p_added = diff["packs"]["added"]
    p_removed = diff["packs"]["removed"]
    p_changed = diff["packs"]["version_changed"]

    if p_added:
        print(f"\nPacks Added ({len(p_added)}):")
        for p in p_added:
            print(f"  + {p['id']} ({p['version']})")

    if p_removed:
        print(f"\nPacks Removed ({len(p_removed)}):")
        for p in p_removed:
            print(f"  - {p['id']} ({p['version']})")

    if p_changed:
        print(f"\nPack Versions Changed ({len(p_changed)}):")
        for p in p_changed:
            print(f"  * {p['id']}: {p['old']} -> {p['new']}")

    if diff["packs"]["order_changed"]:
        print("\nPack Load Order Changed!")

    # Overrides
    o_delta = diff["overrides"]["total_delta"]
    o_added = len(diff["overrides"]["added"])
    o_removed = len(diff["overrides"]["removed"])
    o_changed = len(diff["overrides"]["changed"])

    if o_added or o_removed or o_changed:
        print(f"\nOverrides Changed (Delta: {o_delta:+d}):")
        print(f"  + Added: {o_added}")
        print(f"  - Removed: {o_removed}")
        print(f"  * Changed: {o_changed}")

    # Content Files
    cf_changed = diff["content_files"]["changed"]
    cf_added = diff["content_files"]["added"]
    cf_removed = diff["content_files"]["removed"]

    if cf_changed or cf_added or cf_removed:
        print("\nKey Content Files Changed:")
        for f in cf_added:
            print(f"  + {f}")
        for f in cf_removed:
            print(f"  - {f}")
        for f in cf_changed:
            print(f"  * {f}")

    if not (p_added or p_removed or p_changed or diff["packs"]["order_changed"] or o_added or o_removed or o_changed or cf_changed or cf_added or cf_removed):
        print("\nNo changes detected.")

def changelog_command(args: argparse.Namespace) -> None:
    """Generate a markdown changelog."""
    try:
        old_lock = read_lock(Path(args.old_lock))
        new_lock = read_lock(Path(args.new_lock))
    except Exception as e:
        _log_swallow("CTCM-003", "engine/tooling/content_commands.py blanket swallow", once=True)
        print(f"[Mesh][Changelog] ERROR: {e}")
        return

    diff = diff_locks(old_lock, new_lock)

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

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[Mesh][Changelog] Wrote changelog to {out_path}")

def audit_content_command(args: argparse.Namespace) -> None:
    """Audit content for unused assets and definitions."""
    print(f"[Mesh][Audit] Auditing content referenced by '{args.world_path}'...")

    config = load_config()
    audit_policy = config.audit_policy

    # Merge config defaults
    if args.ignore is None:
        # Config stores list, args expects comma-separated string or we can just pass list to audit_world
        # audit_world expects list.
        # But args.ignore is parsed as string later?
        # Let's handle it here.
        ignore_patterns = audit_policy.get("ignore", [])
    else:
        ignore_patterns = args.ignore.split(",")

    if args.allow_packs is None:
        allow_packs = audit_policy.get("allow_packs", [])
    else:
        allow_packs = args.allow_packs.split(",")

    report = audit_world(args.world_path, ignore_patterns=ignore_patterns, allow_packs=allow_packs)
    stats = report["stats"]

    # Baseline comparison
    baseline_stats = {}
    deltas = {}

    baseline_path = args.baseline
    if baseline_path == "auto":
        if Path("content.lock.json").exists():
            baseline_path = "content.lock.json"
            print(f"[Mesh][Audit] Auto-detected baseline: {baseline_path}")
        else:
            print("[Mesh][Audit] WARNING: Auto-baseline requested but 'content.lock.json' not found. Skipping baseline comparison.")
            baseline_path = None

    if baseline_path:
        try:
            baseline_lock = read_lock(Path(baseline_path))
            baseline_stats = baseline_lock.get("audit_snapshot", {})
            if not baseline_stats:
                print(f"[Mesh][Audit] WARNING: Baseline lock '{baseline_path}' has no audit snapshot.")
            else:
                # Compute deltas
                for k, v in stats.items():
                    if isinstance(v, int) and k in baseline_stats:
                        deltas[k] = v - baseline_stats[k]

                # Also category deltas
                if "unused_by_category" in stats and "unused_by_category" in baseline_stats:
                    for cat, count in stats["unused_by_category"].items():
                        base_count = baseline_stats["unused_by_category"].get(cat, 0)
                        deltas[f"category_{cat}"] = count - base_count

        except Exception as e:
            _log_swallow("CTCM-004", "engine/tooling/content_commands.py blanket swallow", once=True)
            print(f"[Mesh][Audit] ERROR: Failed to load baseline: {e}")

    # Enrich report with baseline info
    report["baseline"] = {
        "path": baseline_path,
        "stats": baseline_stats,
        "deltas": deltas
    }

    if args.json:
        if args.output:
            json_io.write_json_atomic(args.output, report)
        else:
            print(json.dumps(report, indent=2))

        if _check_thresholds(args, stats, audit_policy, deltas, silent=True):
             exit(1)
        return

    print("\n=== Content Audit Report ===")
    print(f"Total Files Scanned: {stats['total_assets']}")
    print(f"Referenced Assets:   {stats['referenced_assets']}")

    def print_stat(label, key):
        val = stats.get(key, 0)
        delta_str = ""
        if key in deltas:
            d = deltas[key]
            sign = "+" if d > 0 else ""
            delta_str = f" ({sign}{d} vs baseline)"
        print(f"{label:<20} {val}{delta_str}")

    print_stat("Unused Assets:", "unused_assets_count")
    print_stat("Unused Prefabs:", "unused_prefabs_count")
    print_stat("Unused Items:", "unused_items_count")
    print_stat("Unused Quests:", "unused_quests_count")

    if "unused_by_category" in stats:
        print("\nUnused by Category:")
        for cat, count in stats["unused_by_category"].items():
            delta_key = f"category_{cat}"
            delta_str = ""
            if delta_key in deltas:
                d = deltas[delta_key]
                sign = "+" if d > 0 else ""
                delta_str = f" ({sign}{d})"
            print(f"  - {cat}: {count}{delta_str}")

    if stats['unused_assets_count'] > 0:
        print("\nTop Unused Assets:")
        for item in report["unused_assets"][:10]:
            print(f"  - {item['path']} ({item['pack']}) [{item.get('category', 'other')}]")
        if stats['unused_assets_count'] > 10:
            print(f"  ... and {stats['unused_assets_count'] - 10} more.")

    if stats['unused_prefabs_count'] > 0:
        print("\nUnused Prefabs:")
        for item in report["unused_prefabs"][:10]:
            print(f"  - {item['id']}")

    if stats['unused_items_count'] > 0:
        print("\nUnused Items:")
        for item in report["unused_items"][:10]:
            print(f"  - {item['id']}")

    if stats['unused_quests_count'] > 0:
        print("\nUnused Quests (Heuristic):")
        for item in report["unused_quests"][:10]:
            print(f"  - {item['id']}")

    if args.output:
        json_io.write_json_atomic(args.output, report)
        print(f"\nFull report written to {args.output}")

    if _check_thresholds(args, stats, audit_policy, deltas):
        exit(1)

def audit_trend_command(args: argparse.Namespace) -> None:
    """Analyze audit trends across multiple lockfiles."""
    lock_files = []

    # Handle glob patterns
    patterns = args.locks.split(",")
    for pat in patterns:
        # If it's a direct file
        p = Path(pat)
        if p.exists() and p.is_file():
            lock_files.append(p)
        else:
            # Try globbing
            # glob.glob supports recursive with ** if recursive=True, but let's stick to simple glob
            # or pathlib glob.
            # If pat is relative, use cwd
            found = list(Path.cwd().glob(pat))
            lock_files.extend(found)

    # Deduplicate and sort by modification time (or name?)
    # Usually we want chronological order.
    # If they are named like content.lock.v1.json, name sort works.
    # If they are just random backups, mtime works.
    # Let's sort by mtime.
    lock_files = sorted(list(set(lock_files)), key=lambda p: p.stat().st_mtime)

    if not lock_files:
        print("[Mesh][Trend] No lockfiles found matching pattern.")
        return

    trend_data = []

    for p in lock_files:
        try:
            data = read_lock(p)
            snapshot = data.get("audit_snapshot", {})

            entry = {
                "file": p.name,
                "path": str(p),
                "timestamp": p.stat().st_mtime,
                "total_unused": snapshot.get("unused_assets_count", 0),
                "unused_textures": snapshot.get("unused_by_category", {}).get("texture", 0),
                "unused_audio": snapshot.get("unused_by_category", {}).get("audio", 0),
                "unused_data": snapshot.get("unused_by_category", {}).get("data", 0)
            }
            trend_data.append(entry)
        except Exception as e:
            _log_swallow("CTCM-005", "engine/tooling/content_commands.py blanket swallow", once=True)
            print(f"[Mesh][Trend] Warning: Failed to read {p}: {e}")

    # Compute deltas
    for i in range(len(trend_data)):
        curr = trend_data[i]
        if i == 0:
            curr["delta_total"] = 0
        else:
            prev = trend_data[i-1]
            curr["delta_total"] = curr["total_unused"] - prev["total_unused"]

    if args.json:
        print(json.dumps(trend_data, indent=2))
        return

    print(f"\n=== Audit Trend ({len(trend_data)} snapshots) ===")
    print(f"{'Lockfile':<30} {'Total':<10} {'Delta':<10} {'Tex':<8} {'Aud':<8} {'Dat':<8}")
    print("-" * 80)

    for entry in trend_data:
        delta_str = f"{entry['delta_total']:+d}" if entry['delta_total'] != 0 else "-"
        print(f"{entry['file']:<30} {entry['total_unused']:<10} {delta_str:<10} {entry['unused_textures']:<8} {entry['unused_audio']:<8} {entry['unused_data']:<8}")

def _check_thresholds(
    args: argparse.Namespace,
    stats: dict,
    policy: dict,
    deltas: dict | None = None,
    silent: bool = False,
) -> bool:
    """Check if audit stats exceed thresholds. Returns True if failed."""
    failed = False
    deltas = deltas or {}

    # Absolute checks
    checks = [
        ("max_unused_assets", "unused_assets_count", "Unused Assets"),
        ("max_unused_prefabs", "unused_prefabs_count", "Unused Prefabs"),
        ("max_unused_items", "unused_items_count", "Unused Items"),
        ("max_unused_quests", "unused_quests_count", "Unused Quests"),
    ]

    # Category checks
    # We map arg name to category name
    cat_checks = [
        ("max_unused_textures", "texture"),
        ("max_unused_audio", "audio"),
        ("max_unused_data", "data"),
    ]

    for arg_name, stat_key, label in checks:
        limit = getattr(args, arg_name, None)
        if limit is None:
            limit = policy.get(arg_name)

        if limit is not None:
            actual = stats.get(stat_key, 0)
            if actual > limit:
                if not silent:
                    print(f"[Mesh][Audit] FAILURE: {label} count ({actual}) exceeds limit ({limit}).")
                failed = True

    # Category limits
    for arg_name, cat_name in cat_checks:
        limit = getattr(args, arg_name, None)
        if limit is None:
            limit = policy.get(arg_name)

        if limit is not None:
            actual = stats.get("unused_by_category", {}).get(cat_name, 0)
            if actual > limit:
                if not silent:
                    print(f"[Mesh][Audit] FAILURE: Unused {cat_name} count ({actual}) exceeds limit ({limit}).")
                failed = True

    # Delta checks
    if args.max_unused_delta is not None:
        # Check total assets delta
        d = deltas.get("unused_assets_count", 0)
        if d > args.max_unused_delta:
            if not silent:
                print(f"[Mesh][Audit] FAILURE: Unused assets increased by {d} (Limit: +{args.max_unused_delta}).")
            failed = True

    if args.fail_on_unused:
        total_unused = (stats["unused_assets_count"] + stats["unused_prefabs_count"] +
                        stats["unused_items_count"] + stats["unused_quests_count"])
        if total_unused > 0:
            if not silent:
                print(f"[Mesh][Audit] FAILURE: Found {total_unused} unused elements (fail-on-unused is active).")
            failed = True

    return failed


def content_contract_command(args: argparse.Namespace) -> int:
    repo_root = Path(str(getattr(args, "repo_root", "") or ".")).resolve()
    raw_paths = list(getattr(args, "paths", []) or [])
    with_prefabs = bool(getattr(args, "with_prefabs", False))
    with_behaviours = bool(getattr(args, "with_behaviours", False))
    log_path_raw = getattr(args, "log", None)
    log_path = Path(str(log_path_raw)) if log_path_raw else None

    set_content_roots([repo_root])
    try:
        files = collect_contract_files(raw_paths, repo_root)
        result = run_content_contract(
            files,
            repo_root,
            with_prefabs=with_prefabs,
            with_behaviours=with_behaviours,
        )
    finally:
        reset_path_caches()

    lines = list(result.messages)
    exit_code = 0 if result.ok else 2

    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            _log_swallow("CTCM-006", "engine/tooling/content_commands.py blanket swallow", once=True)
            print(f"[Mesh][Contract] ERROR failed to write log: {exc}")
            return 1

    for line in lines:
        print(line)

    if getattr(args, "_capture_result", False):
        setattr(args, "_result", result)

    return exit_code

def add_content_commands(subparsers) -> None:
    """Register content commands."""

    # index-content
    parser_index = subparsers.add_parser("index-content", help="Build and summarize content index")
    parser_index.add_argument("--refresh", action="store_true", help="Force refresh")
    parser_index.set_defaults(func=index_content_command)

    # list-overrides
    parser_overrides = subparsers.add_parser("list-overrides", help="List overridden assets")
    parser_overrides.set_defaults(func=list_overrides_command)

    # where
    parser_where = subparsers.add_parser("where", help="Locate an asset")
    parser_where.add_argument("asset_key", help="Relative path to asset")
    parser_where.set_defaults(func=where_command)

    # validate-refs
    parser_val = subparsers.add_parser("validate-refs", help="Validate asset references")
    parser_val.add_argument("world_path", help="Path to world file")
    parser_val.add_argument("--strict-overrides", action="store_true", help="Treat overrides as errors")
    parser_val.set_defaults(func=validate_refs_command)

    # diff-content
    parser_diff = subparsers.add_parser("diff-content", help="Compare content locks")
    parser_diff.add_argument("--from", dest="old_lock", required=True, help="Path to old lockfile")
    parser_diff.add_argument("--to", dest="new_lock", help="Path to new lockfile (default: current state)")
    parser_diff.add_argument("--json", action="store_true", help="Output JSON")
    parser_diff.set_defaults(func=diff_content_command)

    # changelog
    parser_log = subparsers.add_parser("changelog", help="Generate content changelog")
    parser_log.add_argument("--from", dest="old_lock", required=True, help="Path to old lockfile")
    parser_log.add_argument("--to", dest="new_lock", required=True, help="Path to new lockfile")
    parser_log.add_argument("--out", required=True, help="Output markdown file")
    parser_log.set_defaults(func=changelog_command)

    # audit-content
    parser_audit = subparsers.add_parser("audit-content", help="Audit content for unused assets")
    parser_audit.add_argument("world_path", help="Path to world file")
    parser_audit.add_argument("--json", action="store_true", help="Output JSON report")
    parser_audit.add_argument("--output", help="Output file for JSON report")
    parser_audit.add_argument("--ignore", help="Comma-separated list of glob patterns to ignore")
    parser_audit.add_argument("--allow-packs", help="Comma-separated list of pack IDs to allow unused assets from")
    parser_audit.add_argument("--fail-on-unused", action="store_true", help="Fail if any unused content is found")
    parser_audit.add_argument("--max-unused-assets", type=int, help="Max allowed unused assets")
    parser_audit.add_argument("--max-unused-prefabs", type=int, help="Max allowed unused prefabs")
    parser_audit.add_argument("--max-unused-items", type=int, help="Max allowed unused items")
    parser_audit.add_argument("--max-unused-quests", type=int, help="Max allowed unused quests")
    parser_audit.add_argument("--max-unused-textures", type=int, help="Max allowed unused textures")
    parser_audit.add_argument("--max-unused-audio", type=int, help="Max allowed unused audio files")
    parser_audit.add_argument("--max-unused-data", type=int, help="Max allowed unused data files")
    parser_audit.add_argument("--baseline", help="Path to baseline lockfile for delta comparison")
    parser_audit.add_argument("--max-unused-delta", type=int, help="Max allowed increase in unused assets vs baseline")
    parser_audit.set_defaults(func=audit_content_command)

    # audit-trend
    parser_trend = subparsers.add_parser("audit-trend", help="Analyze audit trends across lockfiles")
    parser_trend.add_argument("locks", help="Comma-separated list of lockfiles or patterns")
    parser_trend.add_argument("--json", action="store_true", help="Output JSON")
    parser_trend.set_defaults(func=audit_trend_command)

    parser_contract = subparsers.add_parser("content-contract", help="Validate content contract for FX references")
    parser_contract.add_argument(
        "--paths",
        action="append",
        help="File, directory, or glob to scan (repeatable). Defaults to packs/**/scenes, scenes, worlds.",
    )
    parser_contract.add_argument(
        "--repo-root",
        default=".",
        help="Repo root for resolving relative paths (default: cwd).",
    )
    parser_contract.add_argument(
        "--log",
        help="Optional file path to write the contract output log.",
    )
    parser_contract.add_argument(
        "--with-prefabs",
        action="store_true",
        help="Validate prefab references in entity data.",
    )
    parser_contract.add_argument(
        "--with-behaviours",
        action="store_true",
        help="Validate behaviour names against the registry.",
    )
    parser_contract.set_defaults(func=content_contract_command)
