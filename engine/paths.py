import os
import sys
from pathlib import Path
from typing import List, Optional

from engine.swallowed_exceptions import _log_swallow

from .config import EngineConfig, load_config
from .content_index import ContentIndex
from .repo_root import find_repo_root

_CACHED_CONFIG: Optional[EngineConfig] = None
_CONTENT_ROOTS: Optional[List[Path]] = None
_CONTENT_ROOTS_SIG: Optional[tuple[str, str]] = None
_CONTENT_INDEX: Optional[ContentIndex] = None
_CONTENT_INDEX_ROOTS: Optional[tuple[Path, ...]] = None

def _relativize(target: Path, base: Path) -> Path:
    try:
        rel = os.path.relpath(str(target), str(base))
        return Path(rel)
    except Exception:
        return target

def get_config() -> EngineConfig:
    global _CACHED_CONFIG
    desired_root = find_repo_root()
    desired_cfg_path = ((desired_root / "config.json") if desired_root else Path("config.json")).resolve()

    if _CACHED_CONFIG is not None:
        cached_path_str = getattr(_CACHED_CONFIG, "_config_path", None)
        if cached_path_str:
            try:
                cached_path = Path(str(cached_path_str)).resolve()
                if cached_path == desired_cfg_path:
                    return _CACHED_CONFIG
            except Exception:
                _log_swallow("PATH-001", "engine/paths.py pass-only blanket swallow")
                pass

    _CACHED_CONFIG = load_config(None)
    return _CACHED_CONFIG

def get_content_roots() -> List[Path]:
    global _CONTENT_ROOTS, _CONTENT_ROOTS_SIG

    # If roots were explicitly set via set_content_roots(), they take precedence
    # over auto-discovery and should not be invalidated by cwd changes.
    if _CONTENT_ROOTS is not None and _CONTENT_ROOTS_SIG is None:
        return _CONTENT_ROOTS

    # Cache is sensitive to the discovered repo root and config path.
    # Pytest (and some tooling) frequently changes cwd; without a keyed cache,
    # we can end up resolving paths against the wrong repo.
    cwd = Path.cwd()
    cwd_base_dir = find_repo_root() or cwd
    desired_root = cwd_base_dir
    desired_cfg_path = ((desired_root / "config.json") if desired_root else Path("config.json")).resolve()
    sig = (str(desired_root.resolve()), str(desired_cfg_path))

    if _CONTENT_ROOTS is not None and _CONTENT_ROOTS_SIG == sig:
        return _CONTENT_ROOTS

    config = get_config()
    loaded_keys: object = getattr(config, "_loaded_keys", set())
    explicit_in_config = isinstance(loaded_keys, set) and ("content_roots" in loaded_keys)

    cfg_roots = getattr(config, "content_roots", None) or []
    if not isinstance(cfg_roots, list):
        cfg_roots = [str(cfg_roots)]

    # (cwd_base_dir computed above)
    config_base_dir_str = getattr(config, "_config_base_dir", None)
    config_base_dir = Path(config_base_dir_str) if config_base_dir_str else None

    resolved: list[Path]
    if (not explicit_in_config) or (len(cfg_roots) == 0):
        # "Missing/empty" means: use the discovered repo root for the *current* cwd,
        # falling back to cwd when no repo markers are present.
        resolved_root = _relativize(cwd_base_dir.resolve(), cwd)
        resolved = [resolved_root]
    else:
        # Explicit roots are resolved relative to the config file directory (when available),
        # else relative to the discovered repo root for the current cwd.
        base_dir = config_base_dir or cwd_base_dir
        resolved = []
        for r in cfg_roots:
            rp = Path(str(r))
            was_absolute = rp.is_absolute()
            if not was_absolute:
                rp = base_dir / rp
            rp = rp.resolve() if rp.exists() else rp
            resolved.append(rp if was_absolute else _relativize(rp, cwd))

    _CONTENT_ROOTS = resolved
    _CONTENT_ROOTS_SIG = sig
    return resolved

def set_content_roots(roots: List[Path]) -> None:
    global _CONTENT_ROOTS, _CONTENT_ROOTS_SIG, _CONTENT_INDEX, _CONTENT_INDEX_ROOTS
    _CONTENT_ROOTS = list(roots)
    _CONTENT_ROOTS_SIG = None
    # Invalidate index if roots change
    _CONTENT_INDEX = None
    _CONTENT_INDEX_ROOTS = None

def reset_path_caches() -> None:
    global _CACHED_CONFIG, _CONTENT_ROOTS, _CONTENT_ROOTS_SIG, _CONTENT_INDEX, _CONTENT_INDEX_ROOTS
    _CACHED_CONFIG = None
    _CONTENT_ROOTS = None
    _CONTENT_ROOTS_SIG = None
    _CONTENT_INDEX = None
    _CONTENT_INDEX_ROOTS = None

def get_content_index(refresh: bool = False) -> ContentIndex:
    """Get or create the content index."""
    global _CONTENT_INDEX, _CONTENT_INDEX_ROOTS

    current_roots = tuple(get_content_roots())
    if _CONTENT_INDEX is None or _CONTENT_INDEX_ROOTS != current_roots:
        _CONTENT_INDEX = ContentIndex(list(current_roots))
        _CONTENT_INDEX_ROOTS = current_roots

    if refresh:
        _CONTENT_INDEX.build(refresh=True)

    return _CONTENT_INDEX

def resolve_path(path_str: str) -> Path:
    """Resolve a content path against configured content roots."""
    path_str = str(path_str).replace("\\", "/")
    # If absolute, return as is
    p = Path(path_str)
    if p.is_absolute():
        return p

    # If index is built and matches current roots, use it for fast lookup
    current_roots = tuple(get_content_roots())
    if _CONTENT_INDEX and _CONTENT_INDEX._built and _CONTENT_INDEX_ROOTS == current_roots:
        # Normalize path separators for index lookup
        key = str(p).replace("\\", "/")
        entry = _CONTENT_INDEX.get_entry(key)
        if entry:
            return entry.resolved_path

    roots = list(current_roots)

    # Try to find existing file in roots
    for root in roots:
        candidate = root / p
        if candidate.exists():
            return candidate

    # Fallback: packaged/installed data roots (wheel installs)
    # - `data-files` may land under sys.prefix/<path_str>
    # - Or adjacent to the engine package (site-packages/<path_str>)
    installed_roots: list[Path] = []
    try:
        installed_roots.append(Path(sys.prefix))
    except Exception:
        _log_swallow("PATH-002", "engine/paths.py pass-only blanket swallow")
        pass
    try:
        installed_roots.append(Path(__file__).resolve().parent.parent)
    except Exception:
        _log_swallow("PATH-003", "engine/paths.py pass-only blanket swallow")
        pass

    seen: set[str] = set()
    for root in installed_roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        candidate = root / p
        if candidate.exists():
            return candidate

    # Fallback to first root (usually for writing or if not found)
    if roots:
        return roots[0] / p

    return p


def is_path_under_content_roots(path: Path) -> bool:
    """Return True when ``path`` resolves inside a configured project content root."""
    try:
        resolved = path.resolve()
    except Exception:
        _log_swallow("PATH-004", "engine/paths.py pass-only blanket swallow")
        resolved = path
    for root in get_content_roots():
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def resolve_monster_data_dir() -> Path:
    """Resolve the directory containing monster catalog JSON files."""

    return resolve_path("assets/data/monster_species.json").parent
