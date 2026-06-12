

def test_text_draw_cached_no_arcade_noop(monkeypatch):
    import engine.optional_arcade
    # Patch the arcade reference inside text_draw module, in case it was already imported
    monkeypatch.setattr(engine.optional_arcade, "arcade", None)

    from engine.text_draw import TextCache, draw_text_cached

    cache = TextCache()
    # Should not raise
    draw_text_cached("test", 0, 0, cache=cache)
