"""Clean source export: produce a ZIP containing only tracked source/assets.

Usage:
    python -m tooling.export_clean [--out OUTPUT.zip] [--dry-run]

Excludes all development artifacts, caches, and build outputs.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

# ------------------------------------------------------------------------------
# Exclusion patterns
# ------------------------------------------------------------------------------

EXCLUDED_PREFIXES: tuple[str, ...] = (
    ".venv/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "dist/",
    "build/",
    ".mesh/",
    ".codex_tmp/",
    "artifacts/",
    "traces/",
    "saves/",
    ".git/",
    "egg-info/",
)

EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".mesh",
        ".codex_tmp",
        "artifacts",
        "traces",
        "saves",
        ".git",
    }
)

EXCLUDED_SUFFIXES: tuple[str, ...] = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".dll",
    ".dylib",
    ".so",
)

EXCLUDED_PATTERNS: tuple[str, ...] = (
    ".egg-info/",
    ".mesh/_diff_",
)


# ------------------------------------------------------------------------------
# Git helpers
# ------------------------------------------------------------------------------


def _iter_git_candidates() -> Iterable[str]:
    yield "git"
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        yield str(Path(program_files) / "Git" / "cmd" / "git.exe")
        yield str(Path(program_files) / "Git" / "bin" / "git.exe")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        yield str(Path(program_files_x86) / "Git" / "cmd" / "git.exe")
        yield str(Path(program_files_x86) / "Git" / "bin" / "git.exe")
    local_app_data = os.environ.get("LocalAppData")
    if local_app_data:
        yield str(Path(local_app_data) / "Programs" / "Git" / "cmd" / "git.exe")
        yield str(Path(local_app_data) / "Programs" / "Git" / "bin" / "git.exe")


def _find_git_exe() -> Optional[str]:
    import shutil

    # First try shutil.which for PATH-based lookup
    git_path = shutil.which("git")
    if git_path:
        return git_path

    # Fall back to common Windows locations
    for candidate in _iter_git_candidates():
        if candidate == "git":
            continue  # Already checked via shutil.which
        if Path(candidate).exists():
            return candidate
    return None


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    exe = _find_git_exe()
    if not exe:
        raise FileNotFoundError("git executable not found")
    return subprocess.run(
        [exe, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git_repo_root(cwd: Path) -> Optional[Path]:
    res = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if res.returncode != 0:
        return None
    try:
        return Path(res.stdout.decode("utf-8", errors="replace").strip()).resolve()
    except Exception:
        return None


def _git_tracked_files(repo_root: Path) -> list[str]:
    """Return list of git-tracked files as POSIX relative paths."""
    res = _run_git(["-C", str(repo_root), "ls-files", "-z"], cwd=repo_root)
    if res.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {res.stderr.decode('utf-8', errors='replace')}")
    raw = res.stdout
    if not raw:
        return []
    return [p.decode("utf-8", errors="surrogateescape") for p in raw.split(b"\x00") if p]


# ------------------------------------------------------------------------------
# Filtering
# ------------------------------------------------------------------------------


def _should_exclude(posix_path: str) -> bool:
    """Return True if path should be excluded from clean export."""
    # Check prefixes
    for prefix in EXCLUDED_PREFIXES:
        if posix_path.startswith(prefix):
            return True

    # Check patterns anywhere in path
    for pattern in EXCLUDED_PATTERNS:
        if pattern in posix_path:
            return True

    # Check suffixes
    if posix_path.endswith(EXCLUDED_SUFFIXES):
        return True

    # Check directory names anywhere in path
    parts = [p for p in posix_path.split("/") if p]
    for part in parts[:-1]:  # Exclude the filename itself
        if part in EXCLUDED_DIR_NAMES:
            return True

    return False


def get_clean_file_list(repo_root: Path) -> list[str]:
    """Return list of tracked files that pass clean export filter."""
    all_files = _git_tracked_files(repo_root)
    return sorted(p for p in all_files if not _should_exclude(p))


# ------------------------------------------------------------------------------
# Export
# ------------------------------------------------------------------------------


def export_clean_zip(repo_root: Path, output_path: Path, *, dry_run: bool = False) -> dict:
    """Create a clean source ZIP from tracked files.

    Returns a summary dict with counts.
    """
    try:
        clean_files = get_clean_file_list(repo_root)
    except (FileNotFoundError, RuntimeError) as e:
        # Git not available - fall back to walking directory
        return {
            "ok": False,
            "error": f"Git required for clean export: {e}",
            "hint": "Install git and ensure the workspace is a git repository.",
        }

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "output": None,
            "file_count": len(clean_files),
            "files": clean_files[:50],  # Sample
            "truncated": len(clean_files) > 50,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in clean_files:
            abs_path = repo_root / rel_path
            if abs_path.exists():
                zf.write(abs_path, rel_path)

    return {
        "ok": True,
        "dry_run": False,
        "output": str(output_path),
        "file_count": len(clean_files),
    }


# ------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a clean source ZIP containing only tracked source/assets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Excludes:
  .venv/, __pycache__/, .pytest_cache/, .mypy_cache/, dist/, build/,
  .mesh/, artifacts/, traces/, saves/, *.pyc, *.pyd, *.exe, *.dylib,
  *.egg-info/, .mesh/_diff_*

Examples:
  python -m tooling.export_clean
  python -m tooling.export_clean --out release.zip
  python -m tooling.export_clean --dry-run
""",
    )
    parser.add_argument(
        "--out",
        "-o",
        help="Output ZIP path (default: mesh_clean_YYYYMMDD_HHMMSS.zip)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be included without creating ZIP",
    )

    args = parser.parse_args(argv)

    cwd = Path.cwd()

    # Try to find repo root via git, with fallback for no-git case
    try:
        repo_root = _git_repo_root(cwd)
    except FileNotFoundError:
        print("[export_clean] ERROR: git not found. Install git to use clean export.", file=sys.stderr)
        return 1

    if repo_root is None:
        print("[export_clean] ERROR: Not in a git repository", file=sys.stderr)
        return 1

    if args.out:
        output_path = Path(args.out)
        if not output_path.is_absolute():
            output_path = cwd / output_path
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = cwd / f"mesh_clean_{timestamp}.zip"

    try:
        result = export_clean_zip(repo_root, output_path, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"[export_clean] ERROR: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"[export_clean] ERROR: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[export_clean] DRY-RUN: {result['file_count']} files would be included")
        if result.get("files"):
            print("Sample files:")
            for f in result["files"]:
                print(f"  {f}")
            if result.get("truncated"):
                print("  ...")
    else:
        print(f"[export_clean] Created: {result['output']}")
        print(f"[export_clean] Files: {result['file_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
