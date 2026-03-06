from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.audio as audio_mod
from engine.assets_reload import reload_render_assets

pytestmark = [pytest.mark.fast]


class _StubAudioManager:
    def __init__(self, *, reloaded: int = 0, failed: int = 0) -> None:
        self.reloaded = int(reloaded)
        self.failed = int(failed)
        self.calls: list[tuple[str, ...]] = []
        self.invalidated: list[str] = []

    def reload_cached_sounds(self, changed_paths: tuple[str, ...] | None) -> tuple[int, int]:
        self.calls.append(tuple(changed_paths or ()))
        return (self.reloaded, self.failed)

    def invalidate_muffled_variant_cache_for_path(self, changed_path: str) -> None:
        self.invalidated.append(str(changed_path))


def test_audio_change_triggers_reload_path_and_counters() -> None:
    audio = _StubAudioManager(reloaded=2, failed=1)
    window = SimpleNamespace(audio=audio)

    counts = reload_render_assets(
        window,
        changed_paths=("assets/sfx/hit.wav", "assets/music/theme.ogg", "assets/config.json"),
    )

    assert audio.invalidated == ["assets/music/theme.ogg", "assets/sfx/hit.wav"]
    assert audio.calls == [("assets/music/theme.ogg", "assets/sfx/hit.wav")]
    assert counts["audio_reloaded"] == 2
    assert counts["audio_failed"] == 1
    assert getattr(window, "_last_hot_reload_stats") == {
        "shader_reloaded": 0,
        "shader_failed": 0,
        "textures_reloaded": 0,
        "textures_failed": 0,
        "audio_reloaded": 2,
        "audio_failed": 1,
    }


def test_non_audio_change_does_not_trigger_audio_reload() -> None:
    audio = _StubAudioManager(reloaded=9, failed=9)
    window = SimpleNamespace(audio=audio)

    counts = reload_render_assets(window, changed_paths=("assets/config.json", "assets/sprite.png"))

    assert audio.invalidated == []
    assert audio.calls == []
    assert counts["audio_reloaded"] == 0
    assert counts["audio_failed"] == 0


def test_audio_reload_failure_keeps_last_good_cached_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    cached_key = "assets/sfx/fail.wav"
    last_good = object()
    manager._sounds[cached_key] = last_good

    monkeypatch.setattr(audio_mod, "resolve_path", lambda path: str(path))

    def _raise_sound(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("decode failed")

    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", _raise_sound)

    window = SimpleNamespace(audio=manager)
    counts = reload_render_assets(window, changed_paths=(cached_key,))

    assert counts["audio_reloaded"] == 0
    assert counts["audio_failed"] == 1
    assert manager._sounds[cached_key] is last_good
    assert getattr(window, "_last_hot_reload_stats") == {
        "shader_reloaded": 0,
        "shader_failed": 0,
        "textures_reloaded": 0,
        "textures_failed": 0,
        "audio_reloaded": 0,
        "audio_failed": 1,
    }
