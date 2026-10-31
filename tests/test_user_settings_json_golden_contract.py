"""Golden contract for user_settings.json persistence."""

from __future__ import annotations

import json

from engine.runtime_settings import RuntimeSettings
from engine.runtime_settings_storage import save_runtime_settings


def test_user_settings_json_golden(tmp_path, monkeypatch) -> None:
    path = tmp_path / "user_settings.json"
    monkeypatch.setenv("MESH_RUNTIME_SETTINGS_PATH", str(path))

    settings = RuntimeSettings(
        music_volume=0.25,
        sfx_volume=0.5,
        fog_enabled=True,
    )
    save_runtime_settings(None, settings)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "music_volume": 0.25,
        "sfx_volume": 0.5,
        "ambience_volume": 1.0,  # M21A: the ambience bus (older files without it load as 1.0)
        "fog_enabled": True,
        "text_scale": 1.0,
        "reduced_flicker": False,
    }
