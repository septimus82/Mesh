"""The obsolete "Soft Shadows" player setting was removed after Milestone 15 (nothing has read it since the per-light
shadows of Milestone 12). Settings and configs saved before still load: the key is ignored, the rest is kept, and the
next save drops it. Room and project shadow softness is a separate, working setting and is untouched."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engine.config import load_config
from engine.runtime_settings import RuntimeSettings
from engine.runtime_settings_storage import load_runtime_settings, save_runtime_settings
from engine.ui_overlays._settings_data import SETTINGS_ROWS

pytestmark = pytest.mark.fast

LEGACY_USER_SETTINGS = {"version": 1, "music_volume": 0.3, "sfx_volume": 0.7, "fog_enabled": True,
                        "soft_shadows_enabled": True, "text_scale": 1.25, "reduced_flicker": True}


def test_older_saved_settings_with_soft_shadows_still_load_and_keep_everything_else(tmp_path) -> None:
    path = tmp_path / "user_settings.json"
    path.write_text(json.dumps(LEGACY_USER_SETTINGS), encoding="utf-8")
    loaded = load_runtime_settings(path)
    assert (loaded.music_volume, loaded.sfx_volume, loaded.fog_enabled) == (pytest.approx(0.3), pytest.approx(0.7), True)
    assert (loaded.text_scale, loaded.reduced_flicker) == (pytest.approx(1.25), True)
    assert not hasattr(loaded, "soft_shadows_enabled")

    save_runtime_settings(path, loaded)
    resaved = json.loads(path.read_text(encoding="utf-8"))
    assert "soft_shadows_enabled" not in resaved, "the next save drops the old key"
    assert resaved["music_volume"] == pytest.approx(0.3) and resaved["reduced_flicker"] is True


def test_an_older_config_with_soft_shadow_keys_still_loads(tmp_path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"soft_shadows_enabled": True, "soft_shadows_expand_px": 9.0,
                                    "soft_shadows_alpha_scale": 0.5, "fog_enabled": True}), encoding="utf-8")
    cfg = load_config(str(cfg_path))
    assert cfg.fog_enabled is True, "the rest of the config is read"
    settings = RuntimeSettings.from_config(cfg)
    assert settings.fog_enabled is True
    settings.apply(SimpleNamespace(engine_config=cfg))  # applying to a legacy config doesn't fail


def test_neither_menu_offers_soft_shadows_any_more() -> None:
    assert all(key != "soft_shadows_enabled" and label != "Soft Shadows" for key, label, _kind in SETTINGS_ROWS)
    from engine.ui_overlays.pause_menu import PauseMenu

    menu = PauseMenu(SimpleNamespace(width=800, height=600, paused=True, engine_config=SimpleNamespace()))
    assert "soft_shadows_enabled" not in menu._settings_widgets
