import sys
from pathlib import Path
from typing import List, Optional

from engine.swallowed_exceptions import _log_swallow

from .config import EngineConfig, load_config
from .content_index import ContentIndex
from .repo_root import find_repo_root

_CACHED_CONFIG: Optional[EngineConfig] = None
_CONFIG_PINNED: bool = False
_CONTENT_ROOTS: Optional[List[Path]] = None
_CONTENT_ROOTS_SIG: Optional[tuple[str, str]] = None
_CONTENT_INDEX: Optional[ContentIndex] = None
_CONTENT_INDEX_ROOTS: Optional[tuple[Path, ...]] = None

# Paths that may fall back to the engine install (wheel / source tree), not project content.
_ENGINE_BUNDLED_PREFIXES: tuple[str, ...] = (
    "assets/data/monster_",
)


def _engine_install_roots() -> list[Path]:
    installed_roots: list[Path] = []
    try:
        installed_roots.append(Path(sys.prefix))
    except Exception:
        _log_swallow("PATH-002", "engine/paths.py pass-only blanket swallow")
    try:
        installed_roots.append(Path(__file__).resolve().parent.parent)
    except Exception:
        _log_swallow("PATH-003", "engine/paths.py pass-only blanket swallow")

    seen: set[str] = set()
    unique: list[Path] = []
    for root in installed_roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _is_engine_bundled_path(path_str: str) -> bool:
    normalized = str(path_str).replace("\\", "/").lstrip("/")
    return any(normalized.startswith(prefix) for prefix in _ENGINE_BUNDLED_PREFIXES)

def get_config() -> EngineConfig:
    global _CACHED_CONFIG
    if _CONFIG_PINNED and _CACHED_CONFIG is not None:
        return _CACHED_CONFIG

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


def pin_config(config: EngineConfig) -> None:
    """Pin the active project config for content-root resolution."""
    global _CACHED_CONFIG, _CONFIG_PINNED, _CONTENT_ROOTS, _CONTENT_ROOTS_SIG, _CONTENT_INDEX, _CONTENT_INDEX_ROOTS
    _CACHED_CONFIG = config
    _CONFIG_PINNED = True
    _CONTENT_ROOTS = None
    _CONTENT_ROOTS_SIG = None
    _CONTENT_INDEX = None
    _CONTENT_INDEX_ROOTS = None


def _config_signature(config: EngineConfig) -> tuple[str, str]:
    base_dir = getattr(config, "_config_base_dir", None)
    cfg_path = getattr(config, "_config_path", None)
    base_key = str(Path(str(base_dir)).resolve()) if base_dir else ""
    path_key = str(Path(str(cfg_path)).resolve()) if cfg_path else ""
    return base_key, path_key


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
    config = get_config()
    if _CONFIG_PINNED:
        sig = _config_signature(config)
        cwd_base_dir = Path(getattr(config, "_config_base_dir", cwd)).resolve()
    else:
        cwd_base_dir = find_repo_root() or cwd
        desired_root = cwd_base_dir
        desired_cfg_path = ((desired_root / "config.json") if desired_root else Path("config.json")).resolve()
        sig = (str(desired_root.resolve()), str(desired_cfg_path))

    if _CONTENT_ROOTS is not None and _CONTENT_ROOTS_SIG == sig:
        return _CONTENT_ROOTS

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
        resolved = [cwd_base_dir.resolve()]
    else:
        # Explicit roots are resolved relative to the config file directory (when available),
        # else relative to the discovered repo root for the current cwd.
        base_dir = config_base_dir or cwd_base_dir
        resolved = []
        for r in cfg_roots:
            rp = Path(str(r))
            if not rp.is_absolute():
                rp = base_dir / rp
            resolved.append(rp.resolve())

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
    global _CACHED_CONFIG, _CONFIG_PINNED, _CONTENT_ROOTS, _CONTENT_ROOTS_SIG, _CONTENT_INDEX, _CONTENT_INDEX_ROOTS
    _CACHED_CONFIG = None
    _CONFIG_PINNED = False
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

    # Project content only: return the first-root candidate (missing) for writes / loud failures.
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
def resolve_engine_bundled_path(path_str: str) -> Path:
    """Resolve an engine-shipped asset path (never project scenes/worlds)."""
    path_str = str(path_str).replace("\\", "/")
    p = Path(path_str)
    if p.is_absolute():
        return p
    if not _is_engine_bundled_path(path_str):
        raise ValueError(f"Path is not engine-bundled content: {path_str}")

    for root in _engine_install_roots():
        candidate = root / p
        if candidate.exists():
            return candidate

    return _engine_install_roots()[0] / p if _engine_install_roots() else p


def resolve_monster_data_dir() -> Path:
    """Resolve the directory containing monster catalog JSON files."""
    rel = "assets/data/monster_species.json"
    for root in get_content_roots():
        candidate = (root / rel).resolve()
        if candidate.exists():
            return candidate.parent
    bundled = resolve_engine_bundled_path(rel)
    return bundled.parent
