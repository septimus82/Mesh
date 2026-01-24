from __future__ import annotations

from pathlib import Path


def test_settings_v1_roundtrip(tmp_path: Path) -> None:
    from engine.settings import SettingsV1, load_settings, save_settings

    path = tmp_path / "settings.json"
    settings = SettingsV1(
        keybinds={"move_up": 87, "interact": 69},
        sfx_volume=0.25,
        music_volume=0.75,
    )
    save_settings(path, settings)
    loaded = load_settings(path)

    assert loaded.keybinds == settings.keybinds
    assert abs(loaded.sfx_volume - settings.sfx_volume) < 1e-9
    assert abs(loaded.music_volume - settings.music_volume) < 1e-9

