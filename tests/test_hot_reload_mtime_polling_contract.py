from __future__ import annotations

import stat as stat_lib
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.asset_hot_reload_watcher as watcher_mod

pytestmark = [pytest.mark.fast]


class _FakeFs:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._entries: dict[str, tuple[bool, int]] = {}

    def add_dir(self, rel_path: str) -> None:
        self._entries[self._abs_key(rel_path)] = (True, 0)

    def add_file(self, rel_path: str, *, mtime_ns: int) -> None:
        path = Path(str(rel_path).replace("\\", "/").strip("/"))
        parent = path.parent
        while str(parent) not in {".", ""}:
            self.add_dir(parent.as_posix())
            parent = parent.parent
        self._entries[self._abs_key(path.as_posix())] = (False, int(mtime_ns))

    def set_mtime(self, rel_path: str, *, mtime_ns: int) -> None:
        key = self._abs_key(rel_path)
        is_dir, _ = self._entries[key]
        self._entries[key] = (is_dir, int(mtime_ns))

    def listdir(self, directory: Path) -> tuple[Path, ...]:
        dir_key = Path(directory).as_posix().rstrip("/")
        prefix = f"{dir_key}/"
        children: set[str] = set()
        for entry_key in self._entries:
            if not entry_key.startswith(prefix):
                continue
            suffix = entry_key[len(prefix):]
            if not suffix:
                continue
            child_name = suffix.split("/", 1)[0]
            children.add(f"{dir_key}/{child_name}")
        return tuple(Path(p) for p in sorted(children))

    def stat(self, path: Path) -> SimpleNamespace:
        key = Path(path).as_posix().rstrip("/")
        is_dir, mtime_ns = self._entries[key]
        mode = stat_lib.S_IFDIR if is_dir else stat_lib.S_IFREG
        return SimpleNamespace(st_mode=mode, st_mtime_ns=int(mtime_ns))

    def _abs_key(self, rel_path: str) -> str:
        rel = str(rel_path).replace("\\", "/").strip("/")
        return (self.repo_root / rel).as_posix().rstrip("/")


def _build_fake_fs(repo_root: Path) -> _FakeFs:
    fs = _FakeFs(repo_root)
    fs.add_file("assets/shaders/fx.glsl", mtime_ns=10)
    fs.add_file("assets/textures/hero.png", mtime_ns=20)
    fs.add_file("assets/audio/hit.ogg", mtime_ns=30)
    fs.add_file("assets/audio/readme.txt", mtime_ns=40)
    return fs


def test_mtime_polling_no_changes_does_not_reload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [1.0]
    calls: list[tuple[str, ...] | None] = []

    monkeypatch.setattr(
        watcher_mod,
        "_reload_render_assets",
        lambda _window, **kwargs: calls.append(kwargs.get("changed_paths")) or {"asset_textures_cleared": 0},
    )
    fs = _build_fake_fs(tmp_path)
    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        debounce_seconds=0.1,
        now_fn=lambda: float(now[0]),
    )
    watcher.configure_polling(
        ("assets/shaders", "assets/textures", "assets/audio"),
        poll_interval_s=0.5,
        listdir_fn=fs.listdir,
        stat_fn=fs.stat,
    )
    watcher.start()

    now[0] += 0.6
    assert watcher.update(0.0) is False
    assert calls == []


def test_mtime_polling_change_is_debounced_and_ordered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [10.0]
    calls: list[tuple[str, ...]] = []

    def _fake_reload(_window: object, **kwargs: object) -> dict[str, int]:
        changed_paths = kwargs.get("changed_paths")
        assert isinstance(changed_paths, tuple)
        calls.append(changed_paths)
        return {"asset_textures_cleared": 0}

    monkeypatch.setattr(watcher_mod, "_reload_render_assets", _fake_reload)
    fs = _build_fake_fs(tmp_path)
    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        debounce_seconds=0.2,
        now_fn=lambda: float(now[0]),
    )
    watcher.configure_polling(
        ("assets/shaders", "assets/textures", "assets/audio"),
        poll_interval_s=0.5,
        listdir_fn=fs.listdir,
        stat_fn=fs.stat,
    )
    watcher.start()

    fs.set_mtime("assets/textures/hero.png", mtime_ns=99)
    fs.set_mtime("assets/audio/hit.ogg", mtime_ns=101)

    now[0] += 0.6
    assert watcher.update(0.0) is False
    assert calls == []

    now[0] += 0.21
    assert watcher.update(0.0) is True
    assert calls == [("assets/audio/hit.ogg", "assets/textures/hero.png")]
    assert watcher.last_dispatched_paths == ("assets/audio/hit.ogg", "assets/textures/hero.png")


def test_mtime_polling_extension_filter_is_honored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [25.0]
    calls: list[tuple[str, ...] | None] = []

    monkeypatch.setattr(
        watcher_mod,
        "_reload_render_assets",
        lambda _window, **kwargs: calls.append(kwargs.get("changed_paths")) or {"asset_textures_cleared": 0},
    )
    fs = _build_fake_fs(tmp_path)
    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        debounce_seconds=0.1,
        now_fn=lambda: float(now[0]),
    )
    watcher.configure_polling(
        ("assets/audio",),
        poll_interval_s=0.5,
        listdir_fn=fs.listdir,
        stat_fn=fs.stat,
    )
    watcher.start()

    fs.set_mtime("assets/audio/readme.txt", mtime_ns=500)
    now[0] += 0.6
    assert watcher.update(0.0) is False
    assert calls == []
