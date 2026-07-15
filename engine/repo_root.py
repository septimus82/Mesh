from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, cast

from engine.swallowed_exceptions import _log_swallow

from .logging_tools import get_logger

_MARKERS: tuple[str, ...] = ("pyproject.toml", "config.json")
_LOG = get_logger("engine.repo_root")

_LAUNCHED_PROJECT_ROOT: Path | None = None


def engine_source_root() -> Path:
    """Return the Mesh engine source tree root (the directory containing ``engine/``)."""
    return Path(__file__).resolve().parent.parent


def pin_launched_project_root(root: Path, *, config: object | None = None) -> Path:
    """Pin the launched game project root for standalone runs."""
    global _LAUNCHED_PROJECT_ROOT

    resolved = Path(root).expanduser().resolve()
    _LAUNCHED_PROJECT_ROOT = resolved
    os.environ["MESH_REPO_ROOT"] = str(resolved)

    from engine.paths import pin_config, reset_path_caches  # noqa: PLC0415

    reset_path_caches()
    if config is not None:
        from engine.config import EngineConfig  # noqa: PLC0415

        pin_config(cast(EngineConfig, config))

    return resolved


def get_launched_project_root() -> Path | None:
    """Return the pinned standalone launch root, if any."""
    return _LAUNCHED_PROJECT_ROOT


def clear_launched_project_root() -> None:
    """Clear the pinned launch root (tests/tooling)."""
    global _LAUNCHED_PROJECT_ROOT
    _LAUNCHED_PROJECT_ROOT = None
    os.environ.pop("MESH_REPO_ROOT", None)


def launched_project_root_blocks_switch(target: str) -> bool:
    """Return True when ``target`` would switch away from a pinned launch root."""
    if _LAUNCHED_PROJECT_ROOT is None:
        return False
    text = str(target or "").strip()
    if not text:
        return False
    try:
        candidate = Path(text).expanduser().resolve()
    except Exception:
        _log_swallow("REPO-002", "engine/repo_root.py pass-only blanket swallow")
        return True
    return candidate != _LAUNCHED_PROJECT_ROOT.resolve()


def is_standalone_project_root(root: Path) -> bool:
    """Return True when ``root`` is not the engine source checkout."""
    try:
        return Path(root).expanduser().resolve() != engine_source_root().resolve()
    except Exception:
        _log_swallow("REPO-003", "engine/repo_root.py pass-only blanket swallow")
        return True


def _has_any_marker(path: Path, markers: Iterable[str]) -> bool:
    for name in markers:
        if (path / name).exists():
            return True
    return False


def _walk_up_for_markers(start: Path) -> Optional[Path]:
    current = start.resolve()
    while True:
        if _has_any_marker(current, _MARKERS):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def get_repo_root(
    start: Optional[Path] = None,
    *,
    override: Optional[Path] = None,
    strict: bool = False,
) -> Path:
    """Resolve the repo root with strict precedence.

    Priority:
      1) `override` if provided (must be a directory)
      2) `MESH_REPO_ROOT` env var (must be a directory; strict mode raises on invalid)
      3) upward-walk from `start` or this module's `__file__` for repo markers
      4) fallback to `Path.cwd()`
    """
    if override is not None:
        candidate = Path(override).expanduser()
        if not candidate.exists() or not candidate.is_dir():
            raise ValueError(f"override repo root is not a directory: {candidate.as_posix()}")
        return candidate.resolve()

    env_root = (os.environ.get("MESH_REPO_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser()
        if not candidate.exists() or not candidate.is_dir():
            msg = f"MESH_REPO_ROOT is set but is not a directory: {candidate.as_posix()}"
            if strict:
                raise ValueError(msg)
            _LOG.warning("%s", msg)
        else:
            return candidate.resolve()

    probe = start or Path(__file__).resolve()
    found = _walk_up_for_markers(probe if probe.is_dir() else probe.parent)
    if found is not None:
        return found

    return Path.cwd().resolve()


def find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """Return the nearest ancestor containing repo markers, else None.

    This is a discovery helper (may return None); use `get_repo_root()` if you
    need a non-optional root with precedence and fallbacks.
    """
    env_root = (os.environ.get("MESH_REPO_ROOT") or "").strip()
    if env_root:
        try:
            candidate = Path(env_root).expanduser().resolve()
            if not candidate.exists() or not candidate.is_dir():
                _LOG.warning("MESH_REPO_ROOT is set but is not a directory: %s", candidate.as_posix())
            elif _has_any_marker(candidate, _MARKERS):
                return candidate
        except Exception:
            _log_swallow("REPO-001", "engine/repo_root.py pass-only blanket swallow")
            pass

    probe = start or Path.cwd()
    return _walk_up_for_markers(probe if probe.is_dir() else probe.parent)
