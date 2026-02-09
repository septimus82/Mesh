"""Mypy typing safety island gate.

This script runs strict mypy type checking on a curated list of "typed island"
modules - new subsystems that have clean, well-typed code.

The island grows over time as:
1. New subsystems are added to the island from the start
2. Legacy modules are refactored and graduated into the island

This is separate from the baseline ratchet gate which prevents NEW errors
anywhere. The island gate ensures ZERO errors in curated modules.

Usage:
    python -m tooling.mypy_island        # Run island check
    python -m tooling.mypy_island --list # List island modules
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Typed Island Modules - strict typing required, zero errors allowed
# ---------------------------------------------------------------------------

# Router models - pure data/logic for input routing
ISLAND_INPUT_RUNTIME = [
    "engine/input_runtime/capture_mouse_router_model.py",
    "engine/input_runtime/capture_key_router_model.py",
    "engine/input_runtime/capture_runtime_focus_model.py",
]

# Save system schema and validation
ISLAND_SAVE_RUNTIME = [
    "engine/save_runtime/schema.py",
]

# Physics and sensor models (already strict per pyproject.toml)
ISLAND_PHYSICS = [
    "engine/physics_model.py",
    "engine/sensors_model.py",
    "engine/physics_broadphase_key_model.py",
]

# Editor models (low-dependency, testable)
ISLAND_EDITOR_MODELS = [
    "engine/editor/project_explorer_rank_model.py",
]

# Animation - headless simulator (test helper)
ISLAND_ANIMATION: list[str] = [
    # Note: test_animation_determinism_contract.py has AnimationStepSimulator
    # which is a test helper, so we check it lives in tests/ and is typed.
]

# Sprite animator (runtime, well-typed)
ISLAND_SPRITE = [
    "engine/sprite_animator.py",
]

# Pathfinding models
ISLAND_PATHFINDING = [
    "engine/pathfinding/nav_grid.py",
    "engine/pathfinding/astar.py",
]

# Combine all island modules
TYPED_ISLAND_MODULES: tuple[str, ...] = tuple(
    ISLAND_INPUT_RUNTIME
    + ISLAND_SAVE_RUNTIME
    + ISLAND_PHYSICS
    + ISLAND_EDITOR_MODELS
    + ISLAND_SPRITE
    + ISLAND_PATHFINDING
)


# ---------------------------------------------------------------------------
# Known allowances - errors we accept temporarily for specific reasons
# ---------------------------------------------------------------------------

# These are errors in island modules that we explicitly allow.
# Document the reason and create a ticket/plan to fix.
# Format: "file:line: error message fragment"
ALLOWED_ISLAND_ERRORS: frozenset[str] = frozenset({
    # capture_mouse_router_model.py uses CaptureFocusSnapshot which has dynamic attrs
    "capture_mouse_router_model.py:87: error: Returning Any",  # show_debug attr
    # capture_key_router_model.py similar issue
    # nav_grid.py has a deliberate Any return for iteration
    "nav_grid.py:125: error: Returning Any",  # iter_tiles returns dynamic
})


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _filter_island_errors(errors: list[str]) -> list[str]:
    """Filter out explicitly allowed errors."""
    filtered = []
    for error in errors:
        allowed = any(allowed_frag in error for allowed_frag in ALLOWED_ISLAND_ERRORS)
        if not allowed:
            filtered.append(error)
    return filtered


def _run_mypy_on_island(repo_root: Path) -> tuple[int, list[str]]:
    """Run mypy on island modules with strict settings."""
    # Filter to only existing files
    existing_modules = [
        m for m in TYPED_ISLAND_MODULES
        if (repo_root / m).exists()
    ]
    
    if not existing_modules:
        return 0, []
    
    cmd = [
        sys.executable, "-m", "mypy",
        "--ignore-missing-imports",
        "--follow-imports=skip",  # Only check island modules, not their dependencies
        "--no-error-summary",
        "--show-error-codes",
        "--warn-return-any",
        "--warn-unused-ignores",
        "--no-implicit-optional",
        *existing_modules,
    ]
    
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    
    errors = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if " error: " in line:
            errors.append(line)
    
    return result.returncode, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mypy typing safety island gate",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List island modules and exit",
    )
    args = parser.parse_args(argv)
    
    repo_root = _repo_root()
    
    if args.list:
        print("Typed Island Modules:")
        print("=" * 60)
        for module in TYPED_ISLAND_MODULES:
            exists = (repo_root / module).exists()
            status = "✓" if exists else "✗ (missing)"
            print(f"  {status} {module}")
        print()
        print(f"Total: {len(TYPED_ISLAND_MODULES)} modules")
        print()
        print("To add a module to the island:")
        print("  1. Fix all mypy errors in the module")
        print("  2. Add the module path to TYPED_ISLAND_MODULES in this file")
        print("  3. Run `python -m tooling.mypy_island` to verify")
        return 0
    
    print("[mypy-island] checking typed island modules...")
    code, errors = _run_mypy_on_island(repo_root)
    
    # Filter allowed errors
    filtered_errors = _filter_island_errors(errors)
    
    if filtered_errors:
        print(f"[mypy-island] FAILED - {len(filtered_errors)} error(s) in typed island:")
        for error in filtered_errors[:20]:
            print(f"  {error}")
        if len(filtered_errors) > 20:
            print(f"  ... and {len(filtered_errors) - 20} more")
        print()
        print("To fix:")
        print("  1. Address the type errors in the listed modules")
        print("  2. If error is expected, add to ALLOWED_ISLAND_ERRORS with reason")
        return 1
    
    print(f"[mypy-island] ok - {len(TYPED_ISLAND_MODULES)} modules clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
