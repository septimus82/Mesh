from __future__ import annotations

from pathlib import Path

from engine.paths import resolve_path
from engine.repo_root import get_repo_root


def get_project_root() -> Path:
    """Return the resolved repository root."""
    return Path(get_repo_root()).resolve()


def resolve_asset_path(path: str | Path, *, project_root: Path | None = None) -> Path:
    """Resolve an asset/content path to an absolute filesystem path.

    If ``project_root`` is provided, relative paths are resolved from that root.
    Otherwise this delegates to the engine's canonical path resolver.
    """
    raw = Path(path)
    if raw.is_absolute():
        return raw
    if project_root is not None:
        return (Path(project_root) / raw).resolve()
    return resolve_path(str(raw)).resolve()


__all__ = ["get_project_root", "resolve_asset_path"]

