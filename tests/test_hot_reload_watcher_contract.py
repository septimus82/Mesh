from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

import engine.asset_hot_reload_watcher as watcher_mod

pytestmark = [pytest.mark.fast]


def test_disabled_flag_does_not_start_watcher(tmp_path: Path) -> None:
    window = SimpleNamespace(asset_hot_reload_watcher=None)
    watcher = watcher_mod.maybe_start_hot_reload_watcher(
        window,
        env={"MESH_HOT_RELOAD": "0"},
    )
    assert watcher is None
    assert getattr(window, "asset_hot_reload_watcher", None) is None


def test_event_dispatch_is_debounced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    now = [10.0]
    reload_calls: list[dict[str, int]] = []
    logs: list[str] = []

    monkeypatch.setattr(
        watcher_mod,
        "_reload_render_assets",
        lambda _window, **_kwargs: reload_calls.append({"ok": 1}) or {"asset_textures_cleared": 1},
    )

    window = SimpleNamespace(console_log=lambda message: logs.append(str(message)))
    watcher = watcher_mod.HotReloadWatcher(
        window,
        repo_root=tmp_path,
        watch_dirs=("assets",),
        debounce_seconds=0.2,
        scan_interval_seconds=30.0,
        now_fn=lambda: float(now[0]),
    )
    watcher.start()
    assert watcher.notify_path_changed("assets/a.png") is True
    assert watcher.update(0.0) is False
    assert reload_calls == []

    now[0] += 0.15
    assert watcher.update(0.0) is False
    assert reload_calls == []

    now[0] += 0.10
    assert watcher.update(0.0) is True
    assert len(reload_calls) == 1
    assert watcher.last_dispatched_paths == ("assets/a.png",)
    assert logs and logs[-1].startswith("[Assets][HotReload] files=1")


def test_multiple_rapid_events_batch_to_single_reload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [100.0]
    reload_count = {"n": 0}

    def _fake_reload(_window: object, **_kwargs: object) -> dict[str, int]:
        reload_count["n"] += 1
        return {"asset_textures_cleared": 0}

    monkeypatch.setattr(watcher_mod, "_reload_render_assets", _fake_reload)

    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        watch_dirs=("assets", "packs"),
        debounce_seconds=0.25,
        scan_interval_seconds=30.0,
        now_fn=lambda: float(now[0]),
    )
    watcher.start()
    watcher.notify_path_changed("assets/b.png")
    watcher.notify_path_changed("assets/b.png")
    watcher.notify_path_changed("assets/a.txt")  # filtered out
    watcher.notify_path_changed("packs/core/assets/c.OGG")
    assert watcher.update(0.0) is False
    now[0] += 0.3
    assert watcher.update(0.0) is True
    assert reload_count["n"] == 1
    assert watcher.last_dispatched_paths == (
        "assets/b.png",
        "packs/core/assets/c.OGG",
    )


def test_extension_filtering_is_deterministic(tmp_path: Path) -> None:
    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(),
        repo_root=tmp_path,
        watch_dirs=("assets",),
        extensions=(".json", ".png"),
    )
    assert watcher.notify_path_changed("assets/a.png") is True
    assert watcher.notify_path_changed("assets/a.PNG") is True
    assert watcher.notify_path_changed("assets/a.json") is True
    assert watcher.notify_path_changed("assets/a.wav") is False
    assert watcher.notify_path_changed("other/a.png") is False


def test_default_extension_filter_includes_shader_files(tmp_path: Path) -> None:
    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(),
        repo_root=tmp_path,
        watch_dirs=("assets",),
    )
    assert watcher.notify_path_changed("assets/a.glsl") is True
    assert watcher.notify_path_changed("assets/a.frag") is True
    assert watcher.notify_path_changed("assets/a.vert") is True


def test_enabled_start_and_stop_helpers(tmp_path: Path) -> None:
    window = SimpleNamespace(asset_hot_reload_watcher=None)
    watcher = watcher_mod.maybe_start_hot_reload_watcher(
        window,
        env={"MESH_HOT_RELOAD": "1"},
    )
    assert isinstance(watcher, watcher_mod.HotReloadWatcher)
    assert watcher.running is True
    watcher_mod.stop_hot_reload_watcher(window)
    assert watcher.running is False


def test_shader_change_event_passes_changed_paths_to_reload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = [50.0]
    captured: list[tuple[str, ...] | None] = []

    def _fake_reload(_window: object, **kwargs: object) -> dict[str, int]:
        changed_paths = kwargs.get("changed_paths")
        if isinstance(changed_paths, tuple):
            captured.append(changed_paths)
        else:
            captured.append(None)
        return {"asset_textures_cleared": 0}

    monkeypatch.setattr(watcher_mod, "_reload_render_assets", _fake_reload)

    watcher = watcher_mod.HotReloadWatcher(
        SimpleNamespace(console_log=lambda _m: None),
        repo_root=tmp_path,
        watch_dirs=("assets",),
        debounce_seconds=0.1,
        scan_interval_seconds=30.0,
        now_fn=lambda: float(now[0]),
    )
    watcher.start()
    assert watcher.notify_path_changed("assets/effect.glsl") is True
    now[0] += 0.2
    assert watcher.update(0.0) is True
    assert captured == [("assets/effect.glsl",)]
