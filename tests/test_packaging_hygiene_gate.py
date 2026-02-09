"""Fast CI gate: fail if forbidden paths exist in workspace (even if untracked).

This test catches accidental packaging of caches, venv, or build artifacts.

By default these tests are skipped unless:
- Running with pytest -m packaging_hygiene
- CI environment variable is set (CI=true, GITHUB_ACTIONS=true, etc.)
- --packaging-strict flag is passed

This allows local dev machines to have caches while still catching issues in CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# Skip unless in CI or explicitly requested
_IN_CI = any(
    os.environ.get(var) in ("true", "1", "yes")
    for var in ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "CIRCLECI", "TRAVIS")
)

_skip_unless_ci = pytest.mark.skipif(
    not _IN_CI,
    reason="Packaging hygiene checks skipped locally (run with CI=true or -m packaging_hygiene)",
)


# Forbidden directories that should never exist in a clean workspace tree
# during CI packaging. These may exist locally but should never be committed
# or packaged.
FORBIDDEN_WORKSPACE_DIRS: tuple[str, ...] = (
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".codex_tmp",
)

# Files that indicate packaging contamination
FORBIDDEN_ROOT_FILES: tuple[str, ...] = (
    "final.patch",
    "final.files.txt",
    "context.json",
)

# Suffixes that should never appear in tracked files
FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".dll",
    ".dylib",
    ".so",
)


def _get_repo_root() -> Path:
    """Return repo root (parent of tests/)."""
    return Path(__file__).resolve().parent.parent


@pytest.mark.fast
@pytest.mark.packaging_hygiene
@_skip_unless_ci
def test_no_forbidden_directories_in_workspace() -> None:
    """Fail if forbidden cache/build directories exist in workspace.

    This prevents accidental packaging of .venv, __pycache__, dist, etc.
    """
    repo_root = _get_repo_root()
    found: list[str] = []

    for dirname in FORBIDDEN_WORKSPACE_DIRS:
        path = repo_root / dirname
        if path.exists():
            found.append(dirname)

    if found:
        msg = (
            "Forbidden directories exist in workspace (remove before packaging):\n"
            + "\n".join(f"  - {d}/" for d in sorted(found))
        )
        pytest.fail(msg)


@pytest.mark.fast
def test_no_forbidden_root_files_tracked() -> None:
    """Fail if packaging contamination files exist at repo root."""
    repo_root = _get_repo_root()
    found: list[str] = []

    for filename in FORBIDDEN_ROOT_FILES:
        path = repo_root / filename
        if path.exists():
            found.append(filename)

    if found:
        msg = (
            "Forbidden files exist at repo root (remove before packaging):\n"
            + "\n".join(f"  - {f}" for f in sorted(found))
        )
        pytest.fail(msg)


@pytest.mark.fast
@pytest.mark.packaging_hygiene
@_skip_unless_ci
def test_no_pycache_dirs_in_source_tree() -> None:
    """Fail if any __pycache__ directories exist in engine/ or mesh_cli/.

    These should be in .gitignore but this gate catches leaks.
    """
    repo_root = _get_repo_root()
    found: list[str] = []

    for search_dir in ("engine", "mesh_cli", "tooling"):
        base = repo_root / search_dir
        if not base.exists():
            continue
        for root, dirs, _files in os.walk(base):
            if "__pycache__" in dirs:
                rel_path = Path(root).relative_to(repo_root) / "__pycache__"
                found.append(rel_path.as_posix())
                # Don't recurse into __pycache__
                dirs.remove("__pycache__")

    # Limit output to first 10 to avoid huge failure messages
    if found:
        sample = found[:10]
        msg = (
            f"Found {len(found)} __pycache__ directories in source tree "
            "(should be in .gitignore):\n"
            + "\n".join(f"  - {p}/" for p in sample)
        )
        if len(found) > 10:
            msg += f"\n  ... and {len(found) - 10} more"
        pytest.fail(msg)


@pytest.mark.fast
@pytest.mark.packaging_hygiene
@_skip_unless_ci
def test_no_egg_info_directories() -> None:
    """Fail if *.egg-info directories exist at repo root."""
    repo_root = _get_repo_root()
    found: list[str] = []

    for item in repo_root.iterdir():
        if item.is_dir() and item.name.endswith(".egg-info"):
            found.append(item.name)

    if found:
        msg = (
            "Found .egg-info directories (remove before packaging):\n"
            + "\n".join(f"  - {d}/" for d in sorted(found))
        )
        pytest.fail(msg)
