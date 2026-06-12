from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.assets_reload as assets_reload

pytestmark = [pytest.mark.fast]


class _ResolverFailAssets:
    def __init__(self) -> None:
        self._textures: dict[str, object] = {}
        self.load_calls: list[str] = []
        self.clear_calls = 0

    def _resolve_path(self, _path: str) -> str:
        raise RuntimeError("resolve failed")

    def _load_texture_internal(self, path: str) -> object:
        self.load_calls.append(str(path))
        return object()

    def get_cache_size(self) -> int:
        return len(self._textures)

    def clear(self) -> None:
        self.clear_calls += 1
        self._textures.clear()


def test_texture_cache_key_resolve_failures_are_sampled_not_permanently_silent(monkeypatch) -> None:
    assets = _ResolverFailAssets()
    window = SimpleNamespace(assets=assets)
    calls = iter([True, False, True])
    logged: list[str] = []

    def _capture(message: str, *args, **kwargs) -> None:
        logged.append(message % args)

    monkeypatch.setattr(assets_reload, "should_log", lambda _site: next(calls))
    monkeypatch.setattr(assets_reload.logger, "warning", _capture)

    first = assets_reload.reload_render_assets(window, changed_paths=("assets/sprite.png",))
    second = assets_reload.reload_render_assets(window, changed_paths=("assets/sprite.png",))
    third = assets_reload.reload_render_assets(window, changed_paths=("assets/sprite.png",))

    assert first["asset_textures_reloaded"] == 1
    assert first["asset_textures_failed"] == 0
    assert second["asset_textures_reloaded"] == 1
    assert second["asset_textures_failed"] == 0
    assert third["asset_textures_reloaded"] == 1
    assert third["asset_textures_failed"] == 0
    assert assets.clear_calls == 0
    assert assets.load_calls == ["assets/sprite.png", "assets/sprite.png", "assets/sprite.png"]
    assert len(logged) == 2
    assert all("[Mesh][HotReload] texture cache key resolve fallback for 'assets/sprite.png': resolve failed" in msg for msg in logged)


def test_fx_preset_rebuild_failures_are_sampled_not_permanently_silent(monkeypatch) -> None:
    calls = iter([True, False, True])
    logged: list[str] = []

    def _capture(message: str, *args, **kwargs) -> None:
        logged.append(message % args)

    def _boom() -> object:
        raise RuntimeError("fx rebuild failed")

    monkeypatch.setattr(assets_reload, "should_log", lambda _site: next(calls))
    monkeypatch.setattr(assets_reload.logger, "warning", _capture)
    monkeypatch.setattr("engine.fx_presets.build_fx_preset_registry", _boom)

    window = SimpleNamespace(fx_presets=object())

    first = assets_reload.reload_render_assets(window)
    second = assets_reload.reload_render_assets(window)
    third = assets_reload.reload_render_assets(window)

    assert first["fx_presets_reloaded"] == 0
    assert second["fx_presets_reloaded"] == 0
    assert third["fx_presets_reloaded"] == 0
    assert len(logged) == 2
    assert all("[Mesh][HotReload] fx presets rebuild fallback: fx rebuild failed" in msg for msg in logged)
