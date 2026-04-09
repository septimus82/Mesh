from __future__ import annotations

import os
import stat as stat_lib
from pathlib import Path
from time import monotonic
from typing import Any, Callable

from engine.logging_tools import get_logger
from engine.repo_root import get_repo_root

logger = get_logger(__name__)

ListDirFn = Callable[[Path], list[str | Path] | tuple[str | Path, ...]]
StatFn = Callable[[Path], Any]

_DEFAULT_WATCH_DIRS: tuple[str, ...] = ("assets", "packs")
_DEFAULT_EXTENSIONS: tuple[str, ...] = (
    ".frag",
    ".glsl",
    ".json",
    ".jpg",
    ".jpeg",
    ".mp3",
    ".ogg",
    ".png",
    ".tmx",
    ".vert",
    ".wav",
)


def _reload_render_assets(
    window: Any,
    *,
    changed_paths: tuple[str, ...] | None = None,
) -> dict[str, int]:
    from engine.assets_reload import reload_render_assets  # noqa: PLC0415

    return reload_render_assets(window, changed_paths=changed_paths)


def is_hot_reload_enabled(*, env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    value = str(source.get("MESH_HOT_RELOAD", "") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except Exception:
        rel = path
    return rel.as_posix()


class HotReloadWatcher:
    """Poll-based, debounced asset hot-reload watcher for dev mode."""

    def __init__(
        self,
        window: Any,
        *,
        repo_root: Path | None = None,
        watch_dirs: tuple[str, ...] = _DEFAULT_WATCH_DIRS,
        extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS,
        debounce_seconds: float = 0.35,
        dispatch_cooldown_seconds: float = 0.5,
        scan_interval_seconds: float = 0.5,
        now_fn: Callable[[], float] = monotonic,
    ) -> None:
        self.window = window
        self.repo_root = Path(repo_root or get_repo_root()).resolve()
        self.watch_dirs = tuple(sorted({str(d).strip().replace("\\", "/").strip("/") for d in watch_dirs if str(d).strip()}))
        self.extensions = tuple(sorted({str(ext).strip().lower() for ext in extensions if str(ext).strip().startswith(".")}))
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self.dispatch_cooldown_seconds = max(0.0, float(dispatch_cooldown_seconds))
        self.scan_interval_seconds = max(0.0, float(scan_interval_seconds))
        self._now_fn = now_fn
        self._running = False
        self._known_mtimes_ns: dict[str, int] = {}
        self._pending_paths: set[str] = set()
        self._next_scan_ts: float = 0.0
        self._next_dispatch_ts: float = 0.0
        self._dispatch_cooldown_until_ts: float = 0.0
        self._last_dispatched_paths: tuple[str, ...] = ()
        self._poll_interval_seconds = self.scan_interval_seconds
        self._poll_listdir_fn: ListDirFn = self._default_listdir
        self._poll_stat_fn: StatFn = self._default_stat
        self._polling_uses_custom_fs = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def last_dispatched_paths(self) -> tuple[str, ...]:
        return self._last_dispatched_paths

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._known_mtimes_ns = self._scan_current_mtimes()
        now = float(self._now_fn())
        self._next_scan_ts = now + self._poll_interval_seconds
        self._next_dispatch_ts = 0.0
        self._dispatch_cooldown_until_ts = 0.0
        self._pending_paths.clear()
        self._last_dispatched_paths = ()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._pending_paths.clear()
        self._next_scan_ts = 0.0
        self._next_dispatch_ts = 0.0
        self._dispatch_cooldown_until_ts = 0.0

    def notify_path_changed(self, path: str | Path) -> bool:
        rel = self._normalize_candidate(path)
        if rel is None:
            return False
        if not self._accept_rel_path(rel):
            return False
        self._pending_paths.add(rel)
        now = float(self._now_fn())
        if self._next_dispatch_ts <= now:
            self._next_dispatch_ts = now + self.debounce_seconds
        return True

    def configure_polling(
        self,
        watch_dirs: tuple[str, ...] | list[str],
        *,
        poll_interval_s: float = 0.5,
        dispatch_cooldown_s: float = 0.5,
        listdir_fn: ListDirFn | None = None,
        stat_fn: StatFn | None = None,
    ) -> None:
        self.watch_dirs = tuple(
            sorted(
                {
                    str(d).strip().replace("\\", "/").strip("/")
                    for d in watch_dirs
                    if str(d).strip()
                }
            )
        )
        self._poll_interval_seconds = max(0.0, float(poll_interval_s))
        self.scan_interval_seconds = self._poll_interval_seconds
        self.dispatch_cooldown_seconds = max(0.0, float(dispatch_cooldown_s))
        self._poll_listdir_fn = listdir_fn or self._default_listdir
        self._poll_stat_fn = stat_fn or self._default_stat
        self._polling_uses_custom_fs = listdir_fn is not None or stat_fn is not None
        if self._running:
            self._known_mtimes_ns = self._scan_current_mtimes()
            now = float(self._now_fn())
            self._next_scan_ts = now + self._poll_interval_seconds

    def update(self, _dt: float = 0.0) -> bool:
        if not self._running:
            return False
        now = float(self._now_fn())
        if now >= self._next_scan_ts:
            self._next_scan_ts = now + self._poll_interval_seconds
            for rel in self._scan_changed_paths():
                self.notify_path_changed(rel)
        if now < self._dispatch_cooldown_until_ts:
            return False
        if self._pending_paths and now >= self._next_dispatch_ts:
            changed_paths = tuple(sorted(self._pending_paths))
            self._pending_paths.clear()
            self._next_dispatch_ts = 0.0
            self._dispatch_reload(changed_paths)
            self._last_dispatched_paths = changed_paths
            self._dispatch_cooldown_until_ts = now + self.dispatch_cooldown_seconds
            return True
        return False

    def _watch_roots(self) -> tuple[Path, ...]:
        roots: list[Path] = []
        for rel in self.watch_dirs:
            p = (self.repo_root / rel).resolve()
            if self._polling_uses_custom_fs:
                roots.append(p)
            elif p.exists() and p.is_dir():
                roots.append(p)
        roots.sort(key=lambda p: p.as_posix())
        return tuple(roots)

    def _accept_rel_path(self, rel_path: str) -> bool:
        normalized = str(rel_path).replace("\\", "/").lstrip("/")
        if not normalized:
            return False
        suffix = Path(normalized).suffix.lower()
        if suffix not in self.extensions:
            return False
        if not self.watch_dirs:
            return True
        for watch_dir in self.watch_dirs:
            wd = str(watch_dir).replace("\\", "/").strip("/")
            if normalized == wd or normalized.startswith(f"{wd}/"):
                return True
        return False

    def _normalize_candidate(self, path: str | Path) -> str | None:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self.repo_root / candidate).resolve()
        return _to_repo_relative(candidate, self.repo_root)

    def _default_listdir(self, directory: Path) -> tuple[Path, ...]:
        try:
            entries = list(directory.iterdir())
        except OSError:
            return ()
        return tuple(sorted(entries, key=lambda p: p.as_posix()))

    def _default_stat(self, path: Path) -> Any:
        return path.stat()

    @staticmethod
    def _mtime_ns_from_stat(stat_result: Any) -> int | None:
        raw_ns = getattr(stat_result, "st_mtime_ns", None)
        if raw_ns is not None:
            try:
                return int(raw_ns)
            except (TypeError, ValueError):
                return None
        raw = getattr(stat_result, "st_mtime", None)
        if raw is None:
            return None
        try:
            return int(float(raw) * 1_000_000_000.0)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_dir_from_stat(stat_result: Any) -> bool:
        mode = getattr(stat_result, "st_mode", None)
        if mode is None:
            return False
        try:
            return bool(stat_lib.S_ISDIR(int(mode)))
        except (TypeError, ValueError):
            return False

    def _iter_directory_entries(self, directory: Path) -> tuple[Path, ...]:
        try:
            raw_entries = self._poll_listdir_fn(directory)
        except Exception:
            return ()
        entries: list[Path] = []
        for raw in raw_entries:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = directory / candidate
            entries.append(candidate)
        entries.sort(key=lambda p: p.as_posix())
        return tuple(entries)

    def _stat_path(self, path: Path) -> Any | None:
        try:
            return self._poll_stat_fn(path)
        except OSError:
            return None
        except Exception:
            return None

    def _scan_current_mtimes(self) -> dict[str, int]:
        mtimes: dict[str, int] = {}
        for root in self._watch_roots():
            stack: list[Path] = [root]
            while stack:
                directory = stack.pop()
                for path in self._iter_directory_entries(directory):
                    stat_result = self._stat_path(path)
                    if stat_result is None:
                        continue
                    if self._is_dir_from_stat(stat_result):
                        stack.append(path)
                        continue
                    rel = _to_repo_relative(path, self.repo_root)
                    if not self._accept_rel_path(rel):
                        continue
                    mtime_ns = self._mtime_ns_from_stat(stat_result)
                    if mtime_ns is None:
                        continue
                    mtimes[rel] = mtime_ns
        return mtimes

    def _scan_changed_paths(self) -> tuple[str, ...]:
        current = self._scan_current_mtimes()
        changed: set[str] = set()
        previous = self._known_mtimes_ns
        for rel, mtime in current.items():
            if previous.get(rel) != mtime:
                changed.add(rel)
        for rel in previous:
            if rel not in current:
                changed.add(rel)
        self._known_mtimes_ns = current
        return tuple(sorted(changed))

    def _dispatch_reload(self, changed_paths: tuple[str, ...]) -> None:
        if not changed_paths:
            return
        try:
            counts = _reload_render_assets(self.window, changed_paths=changed_paths)
        except Exception as exc:  # noqa: BLE001  # REASON: hot-reload refresh failures must not break watcher loop
            logger.warning("[Mesh][HotReload] asset reload failed: %s", exc)
            return

        textures = int(
            counts.get("asset_textures_cleared", 0)
            + counts.get("render_queue_textures_cleared", 0)
            + counts.get("particle_textures_cleared", 0)
            + counts.get("tilemap_textures_cleared", 0)
        )
        message = f"[Assets][HotReload] files={len(changed_paths)} textures={textures}"
        logger.info("%s", message)
        console_log = getattr(self.window, "console_log", None)
        if callable(console_log):
            console_log(message)


def maybe_start_hot_reload_watcher(
    window: Any,
    *,
    env: dict[str, str] | None = None,
) -> HotReloadWatcher | None:
    if not is_hot_reload_enabled(env=env):
        return None
    existing = getattr(window, "asset_hot_reload_watcher", None)
    if isinstance(existing, HotReloadWatcher):
        existing.start()
        return existing
    watcher = HotReloadWatcher(window)
    watcher.start()
    setattr(window, "asset_hot_reload_watcher", watcher)
    logger.info("[Mesh][HotReload] asset watcher enabled (MESH_HOT_RELOAD=1)")
    return watcher


def stop_hot_reload_watcher(window: Any) -> None:
    watcher = getattr(window, "asset_hot_reload_watcher", None)
    stopper = getattr(watcher, "stop", None)
    if callable(stopper):
        stopper()
