from __future__ import annotations

from engine.text_draw import TextCache
from engine.ui_text_cache import UiTextCache, draw_text


def test_ui_text_cache_wraps_text_cache() -> None:
    cache = TextCache()
    ui_cache = UiTextCache(cache)
    assert ui_cache.cache is cache


def test_draw_text_passes_cache_keyword(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_draw_text_cached(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("engine.ui_text_cache.draw_text_cached", _fake_draw_text_cached)

    ui_cache = UiTextCache(TextCache())
    draw_text(ui_cache, text="Hello", x=10.0, y=20.0, color=(1, 2, 3))

    assert calls, "draw_text_cached was not called"
    assert calls[0]["args"][:3] == ("Hello", 10.0, 20.0)
    assert calls[0]["kwargs"].get("cache") is ui_cache.cache
