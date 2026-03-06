from __future__ import annotations

from collections import deque
import hashlib
import os
from pathlib import Path
from typing import Optional

from .logging_tools import get_logger
from .paths import resolve_path
from .repo_root import get_repo_root


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

_LOG = get_logger("engine.editor_palette.thumbs")

DEFAULT_THUMB_SIZE = 64


# ---------------------------------------------------------------------------
# Budgeted thumbnail generation
#
# Generating thumbs can be expensive (PIL decode/resize + disk IO). The editor
# palette draws every frame, so we expose a small work queue processed in
# tick_thumb_generation().

_THUMB_QUEUE: deque[str] = deque()
_THUMB_PENDING: set[str] = set()
_THUMB_META: dict[str, tuple[Path, int]] = {}


def _normalize_repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        _log_swallow("EDPT-003", f"path={path}")
        return path.as_posix()


def _build_cache_key(resolved: Path, *, repo_root: Path, thumb_size: int) -> str | None:
    try:
        stat = resolved.stat()
    except Exception:
        _log_swallow("EDPT-004", f"resolved={resolved}")
        return None
    rel = _normalize_repo_relative(resolved, repo_root=repo_root)
    return f"{rel}|{stat.st_mtime_ns}|{stat.st_size}|{thumb_size}"


def _thumb_path_for_key(key: str, *, repo_root: Path) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return repo_root / ".mesh" / "cache" / "thumbs" / f"{digest}.png"


def _compute_thumb_path(
    sprite_path: str,
    *,
    repo_root: Path | None = None,
    thumb_size: int = DEFAULT_THUMB_SIZE,
) -> tuple[Path, Path] | None:
    """Return (resolved_source_path, thumb_path) or None if not resolvable."""
    if not isinstance(sprite_path, str) or not sprite_path.strip():
        return None
    try:
        resolved = resolve_path(sprite_path)
    except Exception:
        _log_swallow("EDPT-005", f"sprite_path={sprite_path}")
        return None
    if not resolved.exists() or not resolved.is_file():
        return None

    root = repo_root or get_repo_root(start=Path.cwd(), strict=False)
    key = _build_cache_key(resolved, repo_root=root, thumb_size=int(thumb_size))
    if not key:
        return None
    return resolved, _thumb_path_for_key(key, repo_root=root)


def request_thumb(
    sprite_path: str,
    *,
    repo_root: Path | None = None,
    thumb_size: int = DEFAULT_THUMB_SIZE,
) -> Optional[Path]:
    """Return cached thumb path, or enqueue thumb generation and return None."""
    computed = _compute_thumb_path(sprite_path, repo_root=repo_root, thumb_size=thumb_size)
    if computed is None:
        return None
    resolved, thumb_path = computed
    if thumb_path.exists():
        return thumb_path

    canonical = str(resolved)
    _THUMB_META[canonical] = (repo_root or get_repo_root(start=Path.cwd(), strict=False), int(thumb_size))
    if canonical not in _THUMB_PENDING:
        _THUMB_PENDING.add(canonical)
        _THUMB_QUEUE.append(canonical)
    return None


def _create_thumb_sync(
    resolved: Path,
    *,
    repo_root: Path,
    thumb_size: int,
) -> Optional[Path]:
    key = _build_cache_key(resolved, repo_root=repo_root, thumb_size=int(thumb_size))
    if not key:
        return None
    thumb_path = _thumb_path_for_key(key, repo_root=repo_root)
    if thumb_path.exists():
        return thumb_path

    try:
        from PIL import Image
    except Exception:
        _log_swallow("EDPT-006", "PIL import failed")
        return None

    try:
        with Image.open(resolved) as img:
            thumb = img.convert("RGBA")
            thumb.thumbnail((thumb_size, thumb_size))
            canvas = Image.new("RGBA", (thumb_size, thumb_size), (0, 0, 0, 0))
            offset_x = max(0, (thumb_size - thumb.width) // 2)
            offset_y = max(0, (thumb_size - thumb.height) // 2)
            canvas.paste(thumb, (offset_x, offset_y))

        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = thumb_path.with_name(f"{thumb_path.name}.tmp")
        canvas.save(tmp_path, format="PNG")
        os.replace(tmp_path, thumb_path)
        return thumb_path
    except Exception as exc:  # noqa: BLE001
        _log_swallow("EDPT-007", f"resolved={resolved.as_posix()} exc={exc}")
        _LOG.warning("[Editor][Palette] Failed to create thumbnail for %s: %s", resolved.as_posix(), exc)
        return None


def tick_thumb_generation(max_per_frame: int = 2) -> int:
    """Generate up to N thumbs from the queue. Returns the number processed."""
    budget = max(0, int(max_per_frame))
    processed = 0
    if budget > 0:
        while processed < budget and _THUMB_QUEUE:
            canonical = _THUMB_QUEUE.popleft()
            _THUMB_PENDING.discard(canonical)

            meta = _THUMB_META.get(canonical)
            if meta is None:
                continue
            repo_root, thumb_size = meta

            try:
                resolved = Path(canonical)
            except Exception:
                _log_swallow("EDPT-008", f"canonical={canonical}")
                continue
            if not resolved.exists() or not resolved.is_file():
                continue

            _create_thumb_sync(resolved, repo_root=repo_root, thumb_size=int(thumb_size))
            processed += 1

    # Optional cache cap: trim oldest thumbnails by mtime.
    cap_raw = os.environ.get("MESH_EDITOR_THUMBS_MAX")
    if cap_raw is not None and str(cap_raw).strip() != "":
        try:
            cap = int(str(cap_raw).strip())
        except Exception:
            _log_swallow("EDPT-009", f"cap_raw={cap_raw}")
            cap = 0
        if cap > 0:
            try:
                root = get_repo_root(start=Path.cwd(), strict=False)
                thumbs_dir = root / ".mesh" / "cache" / "thumbs"
                if thumbs_dir.exists():
                    files = [p for p in thumbs_dir.iterdir() if p.is_file()]
                    if len(files) > cap:
                        files.sort(key=lambda p: p.stat().st_mtime_ns)
                        to_delete = max(0, len(files) - cap)
                        for p in files[:to_delete]:
                            try:
                                p.unlink(missing_ok=True)
                            except Exception:
                                _log_swallow("EDPT-001", f"unlink p={p}")
                                pass
            except Exception:
                _log_swallow("EDPT-002", "thumb cache cap cleanup")
                pass

    return processed


def _reset_thumb_generation_state_for_tests() -> None:
    _THUMB_QUEUE.clear()
    _THUMB_PENDING.clear()
    _THUMB_META.clear()


def _peek_thumb_queue_for_tests() -> list[str]:
    return list(_THUMB_QUEUE)


def get_or_create_thumb(
    sprite_path: str,
    *,
    repo_root: Path | None = None,
    thumb_size: int = DEFAULT_THUMB_SIZE,
) -> Optional[Path]:
    computed = _compute_thumb_path(sprite_path, repo_root=repo_root, thumb_size=thumb_size)
    if computed is None:
        return None
    resolved, thumb_path = computed
    if thumb_path.exists():
        return thumb_path
    root = repo_root or get_repo_root(start=Path.cwd(), strict=False)
    return _create_thumb_sync(resolved, repo_root=root, thumb_size=int(thumb_size))
