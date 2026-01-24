from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


_FORBIDDEN_PREFIXES: tuple[str, ...] = (
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
)

_FORBIDDEN_ROOT_FILES: tuple[str, ...] = ("final.patch", "final.files.txt", "context.json")


_FORBIDDEN_DIR_NAMES: frozenset[str] = frozenset(
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
    }
)

_FORBIDDEN_FILE_SUFFIXES: tuple[str, ...] = (
    ".pyc",
    ".pyo",
    ".pyd",
)


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
    for candidate in _iter_git_candidates():
        if candidate == "git":
            return candidate
        if Path(candidate).exists():
            return candidate
    return None


def _run_git(args: List[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
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


def _is_forbidden_tracked_path(posix_path: str) -> bool:
    if posix_path in _FORBIDDEN_ROOT_FILES:
        return True

    # Forbid tracked Python bytecode anywhere.
    if posix_path.endswith(_FORBIDDEN_FILE_SUFFIXES):
        return True

    for prefix in _FORBIDDEN_PREFIXES:
        if posix_path.startswith(prefix):
            return True

    # Forbid tracked files inside these directories anywhere in the tree.
    # (e.g. engine/__pycache__/x.pyc shouldn't slip through).
    parts = [p for p in posix_path.split("/") if p]
    for part in parts[:-1]:
        if part in _FORBIDDEN_DIR_NAMES:
            return True

    # Forbid any tracked file inside an *.egg-info directory.
    if ".egg-info/" in posix_path or posix_path.endswith(".egg-info"):
        return True
    return False


def main() -> int:
    cwd = Path.cwd()

    try:
        repo_root = _git_repo_root(cwd)
    except FileNotFoundError:
        # Best-effort fallback: we cannot know what's tracked, but we can at least
        # surface obviously-forbidden paths that exist on disk.
        offenders: list[str] = []
        root = cwd.resolve()

        for name in _FORBIDDEN_ROOT_FILES:
            p = root / name
            if p.exists():
                offenders.append(name)

        for prefix in _FORBIDDEN_PREFIXES:
            dir_name = prefix.rstrip("/")
            p = root / dir_name
            if p.exists():
                offenders.append(prefix)

        offenders = sorted({o.replace("\\", "/") for o in offenders})
        if offenders:
            print("[RepoHygiene] WARN (git not found; cannot check tracked files). Forbidden paths exist on disk:")
            for o in offenders:
                print(o)
            return 0

        print("[RepoHygiene] OK (git not found; skipping tracked-file hygiene check)")
        return 0

    if repo_root is None:
        print("[RepoHygiene] OK (not a git repo; skipping tracked-file hygiene check)")
        return 0

    res = _run_git(["-C", str(repo_root), "ls-files", "-z"], cwd=repo_root)
    if res.returncode != 0:
        stderr = res.stderr.decode("utf-8", errors="replace").strip()
        print("[RepoHygiene] OK (git ls-files unavailable; skipping tracked-file hygiene check)")
        if stderr:
            print(f"[RepoHygiene] git error: {stderr}")
        return 0

    raw = res.stdout
    if not raw:
        print("[RepoHygiene] OK")
        return 0

    paths = [p.decode("utf-8", errors="surrogateescape") for p in raw.split(b"\x00") if p]
    offenders = sorted({p for p in paths if _is_forbidden_tracked_path(p)})

    if offenders:
        print("[RepoHygiene] ERROR: Forbidden paths are tracked by git:")
        for offender in offenders:
            print(offender)
        return 2

    print("[RepoHygiene] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
