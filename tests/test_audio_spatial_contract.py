from __future__ import annotations

from typing import Any

import pytest

import engine.audio as audio_mod
import engine.optional_arcade as optional_arcade

pytestmark = [pytest.mark.fast]


def _stub_get_sound(monkeypatch: pytest.MonkeyPatch, manager: audio_mod.AudioManager) -> None:
    monkeypatch.setattr(manager, "get_sound", lambda _path: object())


def test_attenuate_endpoints_and_monotonic_linear() -> None:
    max_dist = 100.0
    g0 = audio_mod._attenuate(0.0, max_dist=max_dist, rolloff="linear")
    g1 = audio_mod._attenuate(25.0, max_dist=max_dist, rolloff="linear")
    g2 = audio_mod._attenuate(50.0, max_dist=max_dist, rolloff="linear")
    g3 = audio_mod._attenuate(75.0, max_dist=max_dist, rolloff="linear")
    g4 = audio_mod._attenuate(100.0, max_dist=max_dist, rolloff="linear")

    assert g0 == pytest.approx(1.0)
    assert g4 == pytest.approx(0.0)
    assert g0 > g1 > g2 > g3 > g4


def test_pan_is_clamped_and_deterministic() -> None:
    assert audio_mod._pan(-2.0) == pytest.approx(-1.0)
    assert audio_mod._pan(2.0) == pytest.approx(1.0)
    assert audio_mod._pan(-0.25) == pytest.approx(-0.25)
    assert audio_mod._pan(0.25) == pytest.approx(0.25)


def test_play_sound_at_applies_distance_and_pan(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = audio_mod.AudioManager()
    manager.master_volume = 1.0
    manager.sfx_volume = 1.0

    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        base_volume=1.0,
        max_dist=200.0,
        rolloff="linear",
        pan=True,
    )
    assert len(calls) == 1
    call = calls[0]
    assert float(call["volume"]) == pytest.approx(0.5)
    assert float(call["pan"]) == pytest.approx(0.5)


def test_play_sound_at_far_distance_skips_play(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(500.0, 0.0),
        listener_pos=(0.0, 0.0),
        base_volume=1.0,
        max_dist=100.0,
    )
    assert calls == []


def test_play_sound_at_resolves_listener_from_window_camera_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)
    window = type("W", (), {"camera": type("C", (), {"position": (0.0, 0.0)})()})()

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        window=window,
        listener_pos=None,
        base_volume=1.0,
        max_dist=200.0,
        rolloff="linear",
        pan=True,
    )
    assert len(calls) == 1
    call = calls[0]
    assert float(call["volume"]) == pytest.approx(0.5)
    assert float(call["pan"]) == pytest.approx(0.5)


def test_play_sound_at_listener_resolution_failure_keeps_non_spatial_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    class _BrokenWindow:
        camera = object()

        @staticmethod
        def get_camera_center() -> str:
            return "invalid"

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        window=_BrokenWindow(),
        listener_pos=None,
        base_volume=0.75,
        max_dist=200.0,
        pan=True,
    )
    assert len(calls) == 1
    call = calls[0]
    assert float(call["volume"]) == pytest.approx(0.75)
    assert "pan" not in call


def test_play_sound_at_occluded_applies_volume_multiplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    query_calls = {"n": 0}

    class _Scene:
        @staticmethod
        def is_sound_occluded(listener: tuple[float, float], source: tuple[float, float]) -> bool:
            assert listener == (0.0, 0.0)
            assert source == (100.0, 0.0)
            query_calls["n"] += 1
            return True

    window = type("W", (), {"scene_controller": _Scene()})()
    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=True,
    )
    assert query_calls["n"] == 1
    assert len(calls) == 1
    assert float(calls[0]["volume"]) == pytest.approx(0.5 * audio_mod.WORLD_SFX_OCCLUDED_VOLUME_MUL)
    assert float(calls[0]["pan"]) == pytest.approx(0.5 * audio_mod.WORLD_SFX_OCCLUDED_PAN_MUL)


def test_play_sound_at_unoccluded_keeps_volume_and_pan_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    class _Scene:
        @staticmethod
        def is_sound_occluded(_listener: tuple[float, float], _source: tuple[float, float]) -> bool:
            return False

    window = type("W", (), {"scene_controller": _Scene()})()
    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=True,
    )
    assert len(calls) == 1
    assert float(calls[0]["volume"]) == pytest.approx(0.5)
    assert float(calls[0]["pan"]) == pytest.approx(0.5)


def test_play_sound_at_occluded_prefers_muffled_variant_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    get_sound_calls: list[str] = []
    play_calls: list[dict[str, Any]] = []

    def _get_sound(path: str) -> object:
        get_sound_calls.append(str(path))
        return object()

    monkeypatch.setattr(manager, "get_sound", _get_sound)
    monkeypatch.setattr(manager, "_muffled_variant_exists", lambda _path: True)
    monkeypatch.setattr(optional_arcade.arcade, "play_sound", lambda _sound, **kwargs: play_calls.append(dict(kwargs)))

    class _Scene:
        @staticmethod
        def is_sound_occluded(_listener: tuple[float, float], _source: tuple[float, float]) -> bool:
            return True

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=type("W", (), {"scene_controller": _Scene()})(),
        base_volume=1.0,
        max_dist=200.0,
        pan=True,
    )

    assert get_sound_calls == ["assets/sounds/hit_muffled.wav"]
    assert len(play_calls) == 1


def test_play_sound_at_occluded_missing_muffled_falls_back_and_caches_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    get_sound_calls: list[str] = []
    play_calls: list[dict[str, Any]] = []
    exists_calls = {"n": 0}

    def _get_sound(path: str) -> object:
        get_sound_calls.append(str(path))
        return object()

    def _variant_exists(_path: str) -> bool:
        exists_calls["n"] += 1
        return False

    monkeypatch.setattr(manager, "get_sound", _get_sound)
    monkeypatch.setattr(manager, "_muffled_variant_exists", _variant_exists)
    monkeypatch.setattr(optional_arcade.arcade, "play_sound", lambda _sound, **kwargs: play_calls.append(dict(kwargs)))

    class _Scene:
        @staticmethod
        def is_sound_occluded(_listener: tuple[float, float], _source: tuple[float, float]) -> bool:
            return True

    window = type("W", (), {"scene_controller": _Scene()})()
    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=False,
    )
    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=False,
    )

    assert exists_calls["n"] == 1
    assert get_sound_calls == ["assets/sounds/hit.wav", "assets/sounds/hit.wav"]
    assert len(play_calls) == 2


def test_muffled_miss_cache_invalidation_picks_up_new_variant_after_hot_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    original = "assets/sounds/hit.wav"
    muffled = "assets/sounds/hit_muffled.wav"
    original_sound = object()
    muffled_sound = object()
    manager._sounds[original] = original_sound

    play_calls: list[object] = []
    exists_calls = {"n": 0}

    def _variant_exists(_path: str) -> bool:
        exists_calls["n"] += 1
        return False

    monkeypatch.setattr(manager, "_muffled_variant_exists", _variant_exists)
    monkeypatch.setattr(optional_arcade.arcade, "play_sound", lambda sound, **_kwargs: play_calls.append(sound))

    class _Scene:
        @staticmethod
        def is_sound_occluded(_listener: tuple[float, float], _source: tuple[float, float]) -> bool:
            return True

    window = type("W", (), {"scene_controller": _Scene()})()
    manager.play_sound_at(
        original,
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=False,
    )

    assert manager._muffled_variant_cache.get(original) is None
    assert play_calls == [original_sound]
    assert exists_calls["n"] == 1

    manager.invalidate_muffled_variant_cache_for_path(muffled)
    manager._sounds[muffled] = muffled_sound
    manager.play_sound_at(
        original,
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=False,
    )

    assert play_calls == [original_sound, muffled_sound]
    # Second call should not need filesystem existence probing because variant is cached as a loaded sound.
    assert exists_calls["n"] == 1


def test_play_sound_at_unoccluded_uses_original_without_muffled_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    get_sound_calls: list[str] = []
    play_calls: list[dict[str, Any]] = []
    exists_calls = {"n": 0}

    def _get_sound(path: str) -> object:
        get_sound_calls.append(str(path))
        return object()

    def _variant_exists(_path: str) -> bool:
        exists_calls["n"] += 1
        return True

    monkeypatch.setattr(manager, "get_sound", _get_sound)
    monkeypatch.setattr(manager, "_muffled_variant_exists", _variant_exists)
    monkeypatch.setattr(optional_arcade.arcade, "play_sound", lambda _sound, **kwargs: play_calls.append(dict(kwargs)))

    class _Scene:
        @staticmethod
        def is_sound_occluded(_listener: tuple[float, float], _source: tuple[float, float]) -> bool:
            return False

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=type("W", (), {"scene_controller": _Scene()})(),
        base_volume=1.0,
        max_dist=200.0,
        pan=True,
    )

    assert exists_calls["n"] == 0
    assert get_sound_calls == ["assets/sounds/hit.wav"]
    assert len(play_calls) == 1


def test_play_sound_at_missing_occlusion_query_keeps_volume_and_pan_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    window = type("W", (), {"scene_controller": object()})()
    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=(0.0, 0.0),
        window=window,
        base_volume=1.0,
        max_dist=200.0,
        pan=True,
    )
    assert len(calls) == 1
    assert float(calls[0]["volume"]) == pytest.approx(0.5)
    assert float(calls[0]["pan"]) == pytest.approx(0.5)


def test_play_sound_at_does_not_query_occlusion_without_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    query_calls = {"n": 0}

    class _Scene:
        @staticmethod
        def is_sound_occluded(_listener: tuple[float, float], _source: tuple[float, float]) -> bool:
            query_calls["n"] += 1
            return True

    class _BrokenWindow:
        scene_controller = _Scene()
        camera = object()

        @staticmethod
        def get_camera_center() -> str:
            return "invalid"

    manager.play_sound_at(
        "assets/sounds/hit.wav",
        world_pos=(100.0, 0.0),
        listener_pos=None,
        window=_BrokenWindow(),
        base_volume=0.75,
        max_dist=200.0,
        pan=False,
    )
    assert len(calls) == 1
    assert query_calls["n"] == 0
    assert float(calls[0]["volume"]) == pytest.approx(0.75)


def test_play_world_sfx_forwards_to_spatial_with_standard_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    window = object()

    def _capture(*args: Any, **kwargs: Any) -> None:
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(manager, "play_sound_at", _capture)

    manager.play_world_sfx(
        "assets/sounds/hit.wav",
        world_pos=(4.0, -2.0),
        window=window,
        base_volume=0.6,
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["args"] == ("assets/sounds/hit.wav",)
    assert call["kwargs"] == {
        "world_pos": (4.0, -2.0),
        "window": window,
        "listener_pos": None,
        "base_volume": 0.6,
        "max_dist": 800.0,
        "rolloff": "linear",
        "pan": True,
    }


def test_play_world_sfx_profile_overrides_and_explicit_kwargs_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    window = object()

    def _capture(*args: Any, **kwargs: Any) -> None:
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(manager, "play_sound_at", _capture)

    manager.play_world_sfx(
        "assets/sounds/hit.wav",
        world_pos=(10.0, 5.0),
        window=window,
        base_volume=0.4,
        profile="projectile",
        max_dist=750.0,
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["args"] == ("assets/sounds/hit.wav",)
    assert call["kwargs"] == {
        "world_pos": (10.0, 5.0),
        "window": window,
        "listener_pos": None,
        "base_volume": 0.4,
        "max_dist": 750.0,
        "rolloff": "linear",
        "pan": True,
    }


def test_play_world_sfx_unknown_profile_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = audio_mod.AudioManager()
    calls: list[dict[str, Any]] = []
    window = object()

    def _capture(*args: Any, **kwargs: Any) -> None:
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(manager, "play_sound_at", _capture)

    manager.play_world_sfx(
        "assets/sounds/hit.wav",
        world_pos=(1.0, 2.0),
        window=window,
        profile="unknown-profile",
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["kwargs"]["max_dist"] == pytest.approx(800.0)
    assert call["kwargs"]["rolloff"] == "linear"
    assert call["kwargs"]["pan"] is True


def test_existing_play_sound_behavior_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = audio_mod.AudioManager()
    manager.master_volume = 0.5
    manager.sfx_volume = 0.5

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        optional_arcade.arcade,
        "play_sound",
        lambda _sound, **kwargs: calls.append(dict(kwargs)),
    )
    _stub_get_sound(monkeypatch, manager)

    manager.play_sound("assets/sounds/hit.wav", volume=0.8)
    assert len(calls) == 1
    assert float(calls[0]["volume"]) == pytest.approx(0.2)
    assert "pan" not in calls[0]


def test_play_sound_ui_path_is_unaffected_by_muffled_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = audio_mod.AudioManager()
    manager.master_volume = 1.0
    manager.sfx_volume = 1.0
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(manager, "get_sound", lambda _path: object())
    monkeypatch.setattr(
        manager,
        "_select_occluded_sound_path",
        lambda _path: (_ for _ in ()).throw(AssertionError("play_sound should not query occluded selector")),
    )
    monkeypatch.setattr(optional_arcade.arcade, "play_sound", lambda _sound, **kwargs: calls.append(dict(kwargs)))

    manager.play_sound("assets/sounds/ui_click.wav", volume=0.5)
    assert len(calls) == 1
    assert float(calls[0]["volume"]) == pytest.approx(0.5)


def test_invalidate_muffled_variant_cache_for_base_path_removes_cached_miss() -> None:
    manager = audio_mod.AudioManager()
    manager._muffled_variant_cache["assets/sounds/hit.wav"] = None
    manager.invalidate_muffled_variant_cache_for_path("assets/sounds/hit.wav")
    assert "assets/sounds/hit.wav" not in manager._muffled_variant_cache
