import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from engine.actions import validate_bound_actions
from engine.config import load_config
from engine.content_lock import build_lock, read_lock
from engine.content_packs import validate_pack_dependencies
from engine.paths import get_content_index
from engine.tooling import preset_commands
from engine.ui_contract import PERSISTENT_UI_ATTRS, missing_persistent_ui_attrs

from .validate_all import UnifiedValidator


def run_check(
    world_path: str = "worlds/main_world.json",
    full: bool = False,
    replay_trace: Optional[str] = None,
    check_refs: bool = False,
    frozen: bool = False,
) -> bool:
    """Run daily-driver quality checks."""
    # 0. Preset Lint
    config = load_config()
    lint_stage = preset_commands.build_preset_lint_stage_result(config)
    if not lint_stage["ok"]:
        print(json.dumps(lint_stage, sort_keys=True))
        sys.exit(2)

    def _fail() -> bool:
        print("[CHECK] Next:")
        print("  mesh preset lint")
        print(f"  mesh doctor --world {world_path}")
        print("  mesh explain --last")
        return False

    print("[Mesh][Check] Running quality gate...")

    # 0. Pack Validation
    print("[Mesh][Check] Validating content packs...")
    index = get_content_index(refresh=True)
    index.build()

    if full:
        print("[Mesh][Check] Running smoke tests...")
        res = subprocess.run([sys.executable, "mesh_cli.py", "cli-smoke"], capture_output=True, text=True)
        if res.returncode != 0:
            print("[Mesh][Check] Smoke tests failed!")
            print(res.stdout)
            print(res.stderr)
            return _fail()
        print("[Mesh][Check] Smoke tests passed.")

    dep_errors = validate_pack_dependencies(index.packs)
    if dep_errors:
        print("[Mesh][Check] Pack dependency errors:")
        for err in dep_errors:
            print(f"  [ERR] {err}")
        return _fail()

    if frozen:
        print("[Mesh][Check] Verifying content lock (frozen mode)...")
        existing_lock = read_lock(Path("content.lock.json"))
        if not existing_lock:
            print("[Mesh][Check] ERROR: --frozen specified but no content.lock.json found.")
            return _fail()

        current_lock = build_lock()

        # Compare locks
        mismatch = False

        # 1. Compare pack list (order and versions)
        if len(existing_lock["packs"]) != len(current_lock["packs"]):
            print(f"[Mesh][Check] Lock mismatch: Pack count differs (Lock: {len(existing_lock['packs'])}, Current: {len(current_lock['packs'])})")
            mismatch = True
        else:
            for i, (p_lock, p_curr) in enumerate(zip(existing_lock["packs"], current_lock["packs"])):
                if p_lock != p_curr:
                    print(f"[Mesh][Check] Lock mismatch at index {i}:")
                    print(f"  Lock:    {p_lock}")
                    print(f"  Current: {p_curr}")
                    mismatch = True

        # 2. Compare overrides
        # We only care if the lock has overrides that current doesn't, or vice versa, or if they point to different things.
        # The lock stores overrides as a dict.
        if existing_lock.get("overrides") != current_lock.get("overrides"):
             print("[Mesh][Check] Lock mismatch: Overrides differ.")
             mismatch = True

        if mismatch:
            print("[Mesh][Check] Frozen check FAILED. The content environment does not match content.lock.json.")
            print("  Run 'mesh lock-packs' to update the lockfile if these changes are intentional.")
            return _fail()
        else:
            print("[Mesh][Check] Content lock verified.")

    # 1. Wiring checks (bindings + persistent UI contract)
    print("[Mesh][Check] Wiring checks...")
    cfg = load_config("config.json")
    bindings = getattr(cfg, "input_bindings", None) or {}
    unknown_actions, missing_actions = validate_bound_actions(bindings)
    missing_ui, has_ui_duplicates = missing_persistent_ui_attrs(PERSISTENT_UI_ATTRS)
    if unknown_actions or missing_actions or missing_ui or has_ui_duplicates:
        print("[Mesh][Check] Wiring FAILED")
        if unknown_actions:
            print(f"[Mesh][Check] ERROR: Unknown bound action(s): {', '.join(unknown_actions)}")
        if missing_actions:
            print(f"[Mesh][Check] ERROR: Unbound required action(s): {', '.join(missing_actions)}")
        if missing_ui:
            print(f"[Mesh][Check] ERROR: Missing persistent UI key(s): {', '.join(missing_ui)}")
        if has_ui_duplicates:
            print("[Mesh][Check] ERROR: Persistent UI keys contain duplicates")
        print("  Fix: update config.json input_bindings and/or engine/ui.py PERSISTENT_UI_ATTRS.")
        return _fail()
    print("[Mesh][Check] Wiring ok.")

    # 1. Validation
    print(f"[Mesh][Check] Validating world: {world_path}")
    path = Path(world_path)
    if not path.exists():
        print(f"[Mesh][Check] ERROR: World file not found: {world_path}")
        return _fail()

    validator = UnifiedValidator(
        Path("."),
        strict_compact=True,
        check_reachability=True,
        check_orphans=True,
        check_refs=check_refs
    )

    # We need to load the world data first
    try:
        with path.open("r", encoding="utf-8") as f:
            world_data = json.load(f)
    except Exception as e:
        print(f"[Mesh][Check] ERROR: Failed to parse world file: {e}")
        return _fail()

    if not validator.validate_world(path, world_data):
        print("[Mesh][Check] Validation FAILED")
        validator.print_report()
        return _fail()

    # Also check orphans explicitly if validate_world didn't cover all files on disk
    # validate_world calls check_orphans if configured, so we are good.

    if validator.print_report() != 0:
        return _fail()

    # 2. Trace Replay (Optional)
    if replay_trace:
        print(f"[Mesh][Check] Replaying trace: {replay_trace}")
        # We invoke the trace command logic directly or via subprocess
        # Using subprocess to ensure clean state
        cmd = [sys.executable, "mesh_cli.py", "trace", "--replay", replay_trace, "--headless"]
        # If there is an assertions file next to the trace, use it?
        # Convention: trace.jsonl -> trace.assertions.json
        trace_path = Path(replay_trace)
        assertions_path = trace_path.with_suffix(".assertions.json")
        if assertions_path.exists():
            print(f"[Mesh][Check] Found assertions: {assertions_path}")
            cmd.extend(["--assert-file", str(assertions_path)])

        try:
            result = subprocess.run(cmd, capture_output=False)
            if result.returncode != 0:
                print("[Mesh][Check] Trace replay FAILED")
                return _fail()
        except Exception as e:
            print(f"[Mesh][Check] ERROR running trace replay: {e}")
            return _fail()

    # 3. Smoke Tests
    print("[Mesh][Check] Running smoke tests...")
    test_files = ["tests/test_vertical_slice_smoke.py"]
    if Path("tests/test_world_vertical_slice.py").exists():
        test_files.append("tests/test_world_vertical_slice.py")

    if full:
        # Verify docs
        print("[Mesh][Check] Verifying documentation...")
        docs_cmd = [sys.executable, "mesh_cli.py", "docs", "--verify"]
        try:
            res = subprocess.run(docs_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print("[Mesh][Check] Docs verification FAILED:")
                print(res.stdout)
                print(res.stderr)
                return _fail()
            else:
                print("[Mesh][Check] Docs verified.")
        except Exception as e:
            print(f"[Mesh][Check] ERROR running docs verification: {e}")
            return _fail()

        # Run all tests
        cmd = [sys.executable, "-m", "pytest", "tests"]
    else:
        cmd = [sys.executable, "-m", "pytest"] + test_files

    try:
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            print("[Mesh][Check] Smoke tests FAILED")
            return _fail()
    except Exception as e:
        print(f"[Mesh][Check] ERROR running tests: {e}")
        return _fail()

    print("[Mesh][Check] PASSED")

    if full:
        print("[Mesh][Check] Running full gate checks...")

        # Linting
        print("[Mesh][Check] Running ruff...")
        if subprocess.run(["ruff", "check", "."], capture_output=False).returncode != 0:
            print("[Mesh][Check] Linting failed.")
            return _fail()

        print("[Mesh][Check] Running mypy...")
        if subprocess.run(["mypy", "."], capture_output=False).returncode != 0:
            print("[Mesh][Check] Type checking failed.")
            return _fail()

        # Docs verification
        print("[Mesh][Check] Verifying docs...")
        if subprocess.run([sys.executable, "mesh_cli.py", "docs", "--verify"], capture_output=False).returncode != 0:
            print("[Mesh][Check] Docs verification failed.")
            return _fail()

        # Snapshot verification
        print("[Mesh][Check] Verifying CLI snapshot...")
        if subprocess.run(
            [
                sys.executable,
                "mesh_cli.py",
                "cli-snapshot",
                "--out",
                "docs/generated/cli_snapshot.json",
                "--verify",
            ],
            capture_output=False,
        ).returncode != 0:
            print("[Mesh][Check] CLI snapshot verification failed.")
            return _fail()

        print("[Mesh][Check] Verifying Plan schema...")
        if subprocess.run(
            [
                sys.executable,
                "mesh_cli.py",
                "plan",
                "schema",
                "--out",
                "docs/generated/plan_schema.json",
                "--verify",
            ],
            capture_output=False,
        ).returncode != 0:
            print("[Mesh][Check] Plan schema verification failed.")
            return _fail()

    return True

def add_check_arguments(parser: "argparse.ArgumentParser") -> None:
    parser.add_argument("--world", default="worlds/main_world.json", help="World file to validate")
    parser.add_argument("--full", action="store_true", help="Run full test suite")
    parser.add_argument("--replay-trace", help="Optional trace file to replay")
    parser.add_argument("--frozen", action="store_true", help="Fail if content packs do not match content.lock.json")

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mesh Quality Gate")
    add_check_arguments(parser)
    args = parser.parse_args(argv)

    return 0 if run_check(args.world, args.full, args.replay_trace, frozen=args.frozen) else 1

if __name__ == "__main__":
    sys.exit(main())
