from __future__ import annotations

import json

import pytest

from engine.runtime_settings import RuntimeSettings
from engine.runtime_settings_storage import (
    load_runtime_settings,
    save_runtime_settings,
)


@pytest.mark.fast
def test_runtime_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "user_settings.json"
    settings = RuntimeSettings(
        music_volume=0.8,
        sfx_volume=0.2,
        fog_enabled=True,
        soft_shadows_enabled=True,
    )
    save_runtime_settings(path, settings)
    loaded = load_runtime_settings(path)
    assert loaded.music_volume == pytest.approx(0.8)
    assert loaded.sfx_volume == pytest.approx(0.2)
    assert loaded.fog_enabled is True
    assert loaded.soft_shadows_enabled is True


@pytest.mark.fast
def test_runtime_settings_invalid_payload_falls_back(tmp_path) -> None:
    path = tmp_path / "user_settings.json"
    path.write_text("{\"version\": 99}", encoding="utf-8")
    base = RuntimeSettings(music_volume=0.4, sfx_volume=0.6, fog_enabled=True)
    loaded = load_runtime_settings(path, base=base)
    assert loaded.music_volume == pytest.approx(0.4)
    assert loaded.sfx_volume == pytest.approx(0.6)
    assert loaded.fog_enabled is True


@pytest.mark.fast
def test_runtime_settings_clamps_on_load(tmp_path) -> None:
    path = tmp_path / "user_settings.json"
    payload = {
        "version": 1,
        "music_volume": 2.5,
        "sfx_volume": -1.0,
        "fog_enabled": True,
        "soft_shadows_enabled": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_runtime_settings(path)
    assert loaded.music_volume == pytest.approx(1.0)
    assert loaded.sfx_volume == pytest.approx(0.0)
