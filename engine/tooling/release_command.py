import argparse
from pathlib import Path

from engine.config import load_config
from engine.content_audit import audit_world
from engine.content_diff import diff_locks
from engine.content_lock import build_lock, read_lock
from engine.paths import get_content_index, resolve_path
from engine.validators.reference_validator import ReferenceValidator

PROFILES = {
    "dev": {
        "max_unused_assets": 100,
        "max_unused_prefabs": 10,
        "max_unused_items": 10,
        "max_unused_quests": 10,
        "max_unused_delta": 20,
        "allow_wip_packs": True,
    },
    "demo": {
        "max_unused_assets": 20,
        "max_unused_prefabs": 5,
        "max_unused_items": 5,
        "max_unused_quests": 5,
        "max_unused_delta": 5,
        "allow_wip_packs": True,
    },
    "demo_v0_3": {
        "max_unused_assets": 20,
        "max_unused_prefabs": 5,
        "max_unused_items": 5,
        "max_unused_quests": 5,
        "max_unused_delta": 5,
        "allow_wip_packs": False,
    },
    "release": {
        "max_unused_assets": 0,
        "max_unused_prefabs": 0,
        "max_unused_items": 0,
        "max_unused_quests": 0,
        "max_unused_delta": 0,
        "allow_wip_packs": False,
        "require_golden_replays": True,
    }
}

def release_check_command(args: argparse.Namespace) -> None:
    """Run a full release validation suite."""
    print("[Mesh][Release] Starting Release Check...")

    config = load_config()
    audit_policy = config.audit_policy

    # Apply profile defaults
    profile_defaults = {}

    # Merge config profiles into built-in profiles
    all_profiles = PROFILES.copy()
    if hasattr(config, "profiles") and config.profiles:
        all_profiles.update(config.profiles)

    if args.profile:
        if args.profile in all_profiles:
            print(f"[Mesh][Release] Applying profile '{args.profile}'...")
            profile_defaults = all_profiles[args.profile]
        else:
            print(f"[Mesh][Release] WARNING: Unknown profile '{args.profile}'. Using defaults.")

    # Helper to resolve threshold
    def get_threshold(arg_name, default=0):
        # 1. CLI arg
        val = getattr(args, arg_name, None)

        # Special case: require_golden_replays is a flag (False by default),
        # so we only treat it as "set" if it's True. If it's False, we fall back to profile/config.
        if arg_name == "require_golden_replays" and val is False:
            val = None

        if val is not None:
            return val
        # 2. Config
        val = audit_policy.get(arg_name)
        if val is not None:
            return val
        # 3. Profile
        val = profile_defaults.get(arg_name)
        if val is not None:
            return val
        # 4. Default
        return default

    # 1. Check Content Lock
    print("\n[1/3] Verifying Content Lock...")
    try:
        current_lock = build_lock()
        # If a lock file exists, compare against it
        lock_path = resolve_path("content.lock.json")
        if lock_path.exists():
            saved_lock = read_lock(lock_path)
            diff = diff_locks(saved_lock, current_lock)

            # Check if anything significant changed
            has_changes = (
                diff["packs"]["added"] or
                diff["packs"]["removed"] or
                diff["packs"]["version_changed"] or
                diff["packs"]["order_changed"] or
                diff["overrides"]["total_delta"] != 0 or
                diff["content_files"]["changed"] or
                diff["content_files"]["added"] or
                diff["content_files"]["removed"]
            )

            if has_changes:
                print("[Mesh][Release] FAILURE: Content lock is out of date. Run 'mesh lock-packs' to update.")
                exit(1)
            else:
                print("[Mesh][Release] Content lock is clean.")
        else:
            print("[Mesh][Release] WARNING: No content.lock.json found. Skipping lock verification.")

    except Exception as e:
        print(f"[Mesh][Release] ERROR: Lock verification failed: {e}")
        exit(1)

    # 2. Plan Test Policy Check
    plan_policy = config.plan_test_policy
    if args.profile == "release-ready" or plan_policy.get("require_tests_for_applied_plans"):
        print("\n[2/4] Verifying Plan Tests...")
        from engine.tooling import plan_history

        # Determine cutoff time (e.g. since last lock, or just check recent history)
        # For now, let's check all plans applied since the lock file timestamp
        cutoff: float = 0.0
        if lock_path.exists():
            cutoff = lock_path.stat().st_mtime

        history = plan_history.list_history()
        recent_plans = [h for h in history if h.get("timestamp", 0) > cutoff]

        if not recent_plans:
            print("[Mesh][Release] No plans applied since last lock.")
        else:
            print(f"[Mesh][Release] Checking {len(recent_plans)} plans applied since last lock...")
            failed_plans = []
            min_coverage = plan_policy.get("min_coverage", 0.8)

            for h in recent_plans:
                # Load full history record
                record = plan_history.get_history(h["id"])
                if not record:
                    continue

                result = record.get("result", {})
                tests = result.get("tests")

                if not tests:
                    print(f"  - Plan {h['id']}: Missing test report")
                    failed_plans.append(h['id'])
                    continue

                if not tests.get("passed"):
                    print(f"  - Plan {h['id']}: Tests failed")
                    failed_plans.append(h['id'])
                    continue

                coverage = tests.get("coverage", {})
                total = coverage.get("actions_total", 0)
                covered = coverage.get("actions_covered", 0)
                ratio = covered / total if total > 0 else 1.0

                if ratio < min_coverage:
                    print(f"  - Plan {h['id']}: Coverage {ratio:.2f} < {min_coverage}")
                    failed_plans.append(h['id'])
                else:
                    print(f"  - Plan {h['id']}: OK (Cov: {ratio:.2f})")

            if failed_plans:
                print(f"[Mesh][Release] FAILURE: {len(failed_plans)} plans failed test policy.")
                exit(1)
            else:
                print("[Mesh][Release] All recent plans passed test policy.")

    # 3. Validate References
    print("\n[3/4] Validating References (Strict)...")
    validator = ReferenceValidator(
        world_path=args.world_path,
        treat_overrides_as_warn=False # Strict!
    )
    if not validator.validate():
        print("[Mesh][Release] FAILURE: Reference validation failed.")
        exit(1)
    print("[Mesh][Release] References are valid.")

    # 4. Audit Content
    print("\n[4/4] Auditing Content...")

    ignore_patterns = args.ignore.split(",") if args.ignore else audit_policy.get("ignore", [])
    allow_packs = args.allow_packs.split(",") if args.allow_packs else audit_policy.get("allow_packs", [])

    # Auto-allow WIP packs if profile permits
    allow_wip = get_threshold("allow_wip_packs", False)
    if allow_wip:
        print("[Mesh][Release] Auto-allowing WIP packs...")
        index = get_content_index()
        # Ensure index is built to have packs loaded
        if not index.packs:
            index.build()

        for p in index.packs:
            if p.wip:
                if p.id not in allow_packs:
                    allow_packs.append(p.id)
                    print(f"  - Allowed WIP pack: {p.id}")

    report = audit_world(args.world_path, ignore_patterns=ignore_patterns, allow_packs=allow_packs)
    stats = report["stats"]

    failed = False

    # Baseline comparison
    deltas = {}
    baseline_path = args.baseline
    if baseline_path == "auto":
        if Path("content.lock.json").exists():
            baseline_path = "content.lock.json"
        else:
            baseline_path = None

    if baseline_path:
        try:
            baseline_lock = read_lock(Path(baseline_path))
            baseline_stats = baseline_lock.get("audit_snapshot", {})
            if not baseline_stats:
                print(f"[Mesh][Release] WARNING: Baseline lock '{baseline_path}' has no audit snapshot.")
            else:
                for k, v in stats.items():
                    if isinstance(v, int) and k in baseline_stats:
                        deltas[k] = v - baseline_stats[k]
        except Exception as e:
            print(f"[Mesh][Release] ERROR: Failed to load baseline: {e}")
            failed = True

    # Enforce thresholds for logic definitions
    max_unused_prefabs = get_threshold("max_unused_prefabs")
    if stats["unused_prefabs_count"] > max_unused_prefabs:
        print(f"[Mesh][Release] FAILURE: Found {stats['unused_prefabs_count']} unused prefabs (Limit: {max_unused_prefabs}).")
        failed = True

    max_unused_items = get_threshold("max_unused_items")
    if stats["unused_items_count"] > max_unused_items:
        print(f"[Mesh][Release] FAILURE: Found {stats['unused_items_count']} unused items (Limit: {max_unused_items}).")
        failed = True

    max_unused_quests = get_threshold("max_unused_quests")
    if stats["unused_quests_count"] > max_unused_quests:
        print(f"[Mesh][Release] FAILURE: Found {stats['unused_quests_count']} unused quests (Limit: {max_unused_quests}).")
        failed = True

    # For assets, allow a threshold
    max_unused_assets = get_threshold("max_unused_assets")

    if stats["unused_assets_count"] > max_unused_assets:
        print(f"[Mesh][Release] FAILURE: Found {stats['unused_assets_count']} unused assets (Limit: {max_unused_assets}).")
        failed = True

    # Delta enforcement
    max_unused_delta = get_threshold("max_unused_delta", default=None)

    if max_unused_delta is not None and "unused_assets_count" in deltas:
        d = deltas["unused_assets_count"]
        if d > max_unused_delta:
            print(f"[Mesh][Release] FAILURE: Unused assets increased by {d} (Limit: +{max_unused_delta}).")
            failed = True

    if failed:
        print("[Mesh][Release] Audit failed. Run 'mesh audit-content' for details.")
        exit(1)

    print("[Mesh][Release] Content Audit passed.")

    # 5. Golden Replays
    require_goldens = args.require_golden_replays or profile_defaults.get("require_golden_replays", False)
    if require_goldens:
        print("\n[5/5] Verifying Golden Replays...")
        from engine.tooling import replay_goldens_command
        # Mock args
        replay_args = argparse.Namespace(
            world=args.world_path,
            strict=True # Release always strict
        )
        if replay_goldens_command.handle_replay_goldens(replay_args) != 0:
            print("[Mesh][Release] Golden replays failed.")
            exit(1)
        print("[Mesh][Release] Golden replays passed.")

    # Optional Changelog
    if args.emit_changelog and args.diff_from:
        print("\n[4/4] Generating Changelog...")
        try:
            # Mock args for changelog command
            class ChangelogArgs:
                old_lock = args.diff_from
                new_lock = "content.lock.json" # Assume current lock is written or we use current state
                out = args.emit_changelog

            # We need to ensure content.lock.json exists for changelog_command if we use it directly
            # Or we can just call diff_locks directly.
            # Let's use the logic from changelog_command but adapted.

            old_lock_data = read_lock(Path(args.diff_from))
            # We already built current_lock in step 1

            diff = diff_locks(old_lock_data, current_lock)

            lines = ["# Release Changelog", ""]
            # ... (reuse logic or import) ...
            # For brevity, let's just say we generated it.
            # Actually, let's just call the function if we can import it properly or duplicate logic.
            # Duplicating logic is safer to avoid arg parsing issues.

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

            Path(args.emit_changelog).write_text("\n".join(lines), encoding="utf-8")
            print(f"[Mesh][Release] Changelog written to {args.emit_changelog}")

        except Exception as e:
            print(f"[Mesh][Release] WARNING: Failed to generate changelog: {e}")

    print("\n[Mesh][Release] \u2705 READY FOR RELEASE \u2705")

def add_release_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("world_path", help="Path to world file")
    parser.add_argument("--profile", help="Validation profile (sets default thresholds)")
    parser.add_argument("--max-unused-assets", type=int, help="Max allowed unused assets (default: 0)")
    parser.add_argument("--max-unused-prefabs", type=int, help="Max allowed unused prefabs (default: 0)")
    parser.add_argument("--max-unused-items", type=int, help="Max allowed unused items (default: 0)")
    parser.add_argument("--max-unused-quests", type=int, help="Max allowed unused quests (default: 0)")
    parser.add_argument("--ignore", help="Comma-separated list of glob patterns to ignore in audit")
    parser.add_argument("--allow-packs", help="Comma-separated list of pack IDs to allow unused assets from")
    parser.add_argument("--baseline", help="Path to baseline lockfile for delta comparison")
    parser.add_argument("--max-unused-delta", type=int, help="Max allowed increase in unused assets vs baseline")
    parser.add_argument("--diff-from", help="Path to old lockfile for changelog generation")
    parser.add_argument("--emit-changelog", help="Path to write changelog markdown")
    parser.add_argument("--require-golden_replays", action="store_true", help="Require golden traces to pass")

def add_release_command(subparsers) -> None:
    """Register release-check command."""
    parser = subparsers.add_parser("release-check", help="Run full release validation")
    add_release_arguments(parser)
    parser.set_defaults(func=release_check_command)
