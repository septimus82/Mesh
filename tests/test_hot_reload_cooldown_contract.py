from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.asset_hot_reload_watcher as watcher_mod

pytestmark = [pytest.mark.fast]


def test_dispatch_cooldown_coalesces_bursts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [0.0]
    captured: list[tuple[str, ...]] = []

    def _fake_reload(_window: object, **kwargs: object) -> dict[str, int]:
        changed_paths = kwargs.get("changed_paths")
        assert isinstance(changed_paths, tuple)
        captured.append(changed_paths)
        return {"asset_textures_cleared": 0}

    monkeypatch.setattr(watcher_mod, "_reload_render_assets", _fake_reload)

    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        watch_dirs=("assets",),
        debounce_seconds=0.1,
        dispatch_cooldown_seconds=0.5,
        scan_interval_seconds=30.0,
        now_fn=lambda: float(now[0]),
    )
    watcher.start()

    assert watcher.notify_path_changed("assets/a.png") is True
    now[0] += 0.11
    assert watcher.update(0.0) is True
    assert captured == [("assets/a.png",)]

    assert watcher.notify_path_changed("assets/c.png") is True
    assert watcher.notify_path_changed("assets/b.png") is True
    now[0] += 0.1
    assert watcher.update(0.0) is False
    assert captured == [("assets/a.png",)]

    now[0] += 0.31
    assert watcher.update(0.0) is False
    assert captured == [("assets/a.png",)]

    now[0] += 0.10
    assert watcher.update(0.0) is True
    assert captured == [
        ("assets/a.png",),
        ("assets/b.png", "assets/c.png"),
    ]


def test_pending_changes_during_cooldown_are_not_lost(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [10.0]
    captured: list[tuple[str, ...]] = []

    def _fake_reload(_window: object, **kwargs: object) -> dict[str, int]:
        changed_paths = kwargs.get("changed_paths")
        assert isinstance(changed_paths, tuple)
        captured.append(changed_paths)
        return {"asset_textures_cleared": 0}

    monkeypatch.setattr(watcher_mod, "_reload_render_assets", _fake_reload)

    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        watch_dirs=("assets",),
        debounce_seconds=0.05,
        dispatch_cooldown_seconds=0.4,
        scan_interval_seconds=30.0,
        now_fn=lambda: float(now[0]),
    )
    watcher.start()

    assert watcher.notify_path_changed("assets/z.png") is True
    now[0] += 0.06
    assert watcher.update(0.0) is True
    assert captured == [("assets/z.png",)]

    assert watcher.notify_path_changed("assets/m.png") is True
    assert watcher.notify_path_changed("assets/a.png") is True
    assert watcher.notify_path_changed("assets/m.png") is True
    assert watcher.notify_path_changed("assets/ignore.txt") is False

    now[0] += 0.20
    assert watcher.update(0.0) is False
    assert captured == [("assets/z.png",)]

    now[0] += 0.21
    assert watcher.update(0.0) is True
    assert captured == [
        ("assets/z.png",),
        ("assets/a.png", "assets/m.png"),
    ]


def test_configure_polling_accepts_dispatch_cooldown_value(tmp_path: Path) -> None:
    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
    )
    watcher.configure_polling(("assets",), poll_interval_s=0.25, dispatch_cooldown_s=0.75)

    assert watcher.scan_interval_seconds == pytest.approx(0.25)
    assert watcher.dispatch_cooldown_seconds == pytest.approx(0.75)
