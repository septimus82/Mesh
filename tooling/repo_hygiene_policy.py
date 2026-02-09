"""Repo hygiene policy helpers (pure, deterministic)."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable
import os


DEFAULT_ALLOWLIST_GLOBS: tuple[str, ...] = (
    ".git/**",
    "tests/fixtures/**",
)

DEFAULT_FORBIDDEN_GLOBS: tuple[str, ...] = (
    ".venv",
    ".venv/**",
    "venv",
    "venv/**",
    "__pycache__",
    "**/__pycache__/**",
    ".pytest_cache",
    ".pytest_cache/**",
    ".mypy_cache",
    ".mypy_cache/**",
    ".ruff_cache",
    ".ruff_cache/**",
    "dist",
    "dist/**",
    "build",
    "build/**",
    "Mesh-Engine-v1",
    "Mesh-Engine-v1/**",
    "seb",
    "seb/**",
    "seb1",
    "seb1/**",
    "seb2",
    "seb2/**",
    ".mesh",
    ".mesh/**",
    ".codex_tmp",
    ".codex_tmp/**",
    "artifacts",
    "artifacts/**",
    "traces",
    "traces/**",
    "saves",
    "saves/**",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.egg-info",
    "*.egg-info/**",
    "final.patch",
    "final.files.txt",
    "context.json",
)


@dataclass(frozen=True, slots=True)
class HygieneScanResult:
    offenders: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return len(self.offenders) == 0


def scan_repo_hygiene(
    root: Path | str,
    *,
    allowlist_globs: Iterable[str] = DEFAULT_ALLOWLIST_GLOBS,
    forbidden_globs: Iterable[str] = DEFAULT_FORBIDDEN_GLOBS,
) -> HygieneScanResult:
    root_path = Path(root).resolve()
    allowlist = tuple(_normalize_glob(g) for g in allowlist_globs)
    forbidden = tuple(_normalize_glob(g) for g in forbidden_globs)

    offenders: set[str] = set()

    for current_dir, dirnames, filenames in _walk_repo(root_path):
        rel_dir = Path(current_dir).relative_to(root_path)
        rel_dir_posix = "" if str(rel_dir) == "." else rel_dir.as_posix()

        if rel_dir_posix and _matches_any(rel_dir_posix, allowlist):
            dirnames[:] = []
            continue

        if rel_dir_posix and _matches_any(rel_dir_posix, forbidden):
            offenders.add(rel_dir_posix)
            dirnames[:] = []
            continue

        for name in list(dirnames):
            rel_path = _join_rel(rel_dir_posix, name)
            if _matches_any(rel_path, allowlist):
                continue
            if _matches_any(rel_path, forbidden):
                offenders.add(rel_path)
                if name in dirnames:
                    dirnames.remove(name)

        for name in filenames:
            rel_path = _join_rel(rel_dir_posix, name)
            if _matches_any(rel_path, allowlist):
                continue
            if _matches_any(rel_path, forbidden):
                offenders.add(rel_path)

    return HygieneScanResult(offenders=tuple(sorted(offenders)))


def format_hygiene_failure(offenders: Iterable[str]) -> str:
    items = sorted({str(p) for p in offenders if str(p)})
    if not items:
        return "Repo hygiene policy OK."
    hint = "Remove the offending paths or add a justified allowlist entry."
    lines = ["Repo hygiene policy violation:", *items, f"Hint: {hint}"]
    return "\n".join(lines)


def _walk_repo(root: Path):
    for current_dir, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        yield current_dir, dirnames, filenames


def _normalize_glob(pattern: str) -> str:
    text = str(pattern or "").replace("\\", "/")
    return text.strip("/")


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    rel = path.replace("\\", "/").strip("/")
    for pattern in patterns:
        if _match_pattern(rel, pattern):
            return True
    return False


def _match_pattern(rel: str, pattern: str) -> bool:
    if fnmatch(rel, pattern):
        return True
    if pattern.endswith("/**"):
        head = pattern[:-3]
        if head and fnmatch(rel, head):
            return True
    return False


def _join_rel(prefix: str, name: str) -> str:
    if not prefix:
        return name
    return f"{prefix}/{name}"
