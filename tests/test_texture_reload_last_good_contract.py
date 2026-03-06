from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.assets_reload import reload_render_assets

pytestmark = [pytest.mark.fast]


class _StubAssets:
    def __init__(self) -> None:
        self._textures: dict[str, object] = {}
        self.clear_calls = 0
        self.load_calls: list[str] = []
        self._load_result: object | None = object()

    def _resolve_path(self, path: str) -> str:
        return str(path).replace("\\", "/")

    def _load_texture_internal(self, path: str) -> object | None:
        self.load_calls.append(str(path))
        return self._load_result

    def get_cache_size(self) -> int:
        return len(self._textures)

    def clear(self) -> None:
        self.clear_calls += 1
        self._textures.clear()


def test_image_change_triggers_safe_texture_reload_path() -> None:
    assets = _StubAssets()
    old_texture = object()
    cache_key = assets._resolve_path("assets/sprite.png")
    assets._textures[cache_key] = old_texture
    new_texture = object()
    assets._load_result = new_texture
    window = SimpleNamespace(assets=assets)

    counts = reload_render_assets(window, changed_paths=("assets/sprite.png",))

    assert counts["asset_textures_reloaded"] == 1
    assert counts["asset_textures_failed"] == 0
    assert counts["asset_textures_cleared"] == 0
    assert assets.clear_calls == 0
    assert assets._textures[cache_key] is new_texture
    assert getattr(window, "_last_hot_reload_stats") == {
        "shader_reloaded": 0,
        "shader_failed": 0,
        "textures_reloaded": 1,
        "textures_failed": 0,
        "audio_reloaded": 0,
        "audio_failed": 0,
    }


def test_non_image_change_does_not_trigger_texture_reload() -> None:
    assets = _StubAssets()
    assets._textures["assets/old.png"] = object()
    window = SimpleNamespace(assets=assets)

    counts = reload_render_assets(window, changed_paths=("assets/config.json",))

    assert counts["asset_textures_reloaded"] == 0
    assert counts["asset_textures_failed"] == 0
    assert counts["asset_textures_cleared"] == 1
    assert assets.clear_calls == 1
    assert assets.load_calls == []


def test_texture_reload_failure_keeps_last_good_cached_texture() -> None:
    assets = _StubAssets()
    old_texture = object()
    cache_key = assets._resolve_path("packs/core/assets/broken.webp")
    assets._textures[cache_key] = old_texture
    assets._load_result = None
    window = SimpleNamespace(assets=assets)

    counts = reload_render_assets(window, changed_paths=("packs/core/assets/broken.webp",))

    assert counts["asset_textures_reloaded"] == 0
    assert counts["asset_textures_failed"] == 1
    assert counts["asset_textures_cleared"] == 0
    assert assets.clear_calls == 0
    assert assets._textures[cache_key] is old_texture
    assert getattr(window, "_last_hot_reload_stats") == {
        "shader_reloaded": 0,
        "shader_failed": 0,
        "textures_reloaded": 0,
        "textures_failed": 1,
        "audio_reloaded": 0,
        "audio_failed": 0,
    }
