"""Tests for the accessibility text-scaling feature."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


# ===========================================================================
# text_draw module-level scale
# ===========================================================================


class TestTextScale:
    def test_default_scale(self):
        # Reset to default first
        from engine.text_draw import get_text_scale, set_text_scale
        set_text_scale(1.0)
        assert get_text_scale() == 1.0

    def test_set_scale(self):
        from engine.text_draw import get_text_scale, set_text_scale
        set_text_scale(1.5)
        assert get_text_scale() == 1.5
        set_text_scale(1.0)  # restore

    def test_clamp_low(self):
        from engine.text_draw import get_text_scale, set_text_scale
        set_text_scale(0.1)
        assert get_text_scale() == 0.5
        set_text_scale(1.0)

    def test_clamp_high(self):
        from engine.text_draw import get_text_scale, set_text_scale
        set_text_scale(5.0)
        assert get_text_scale() == 3.0
        set_text_scale(1.0)


# ===========================================================================
# RuntimeSettings text_scale field
# ===========================================================================


class TestRuntimeSettingsTextScale:
    def test_default_value(self):
        from engine.runtime_settings import RuntimeSettings
        s = RuntimeSettings()
        assert s.text_scale == 1.0

    def test_to_payload(self):
        from engine.runtime_settings import RuntimeSettings
        s = RuntimeSettings(text_scale=1.5)
        p = s.to_payload()
        assert p["text_scale"] == 1.5

    def test_from_payload_present(self):
        from engine.runtime_settings import RuntimeSettings
        s = RuntimeSettings.from_payload({"text_scale": 2.0})
        assert s.text_scale == 2.0

    def test_from_payload_missing(self):
        from engine.runtime_settings import RuntimeSettings
        s = RuntimeSettings.from_payload({})
        assert s.text_scale == 1.0

    def test_from_payload_clamped(self):
        from engine.runtime_settings import RuntimeSettings
        s = RuntimeSettings.from_payload({"text_scale": 10.0})
        assert s.text_scale == 3.0

    def test_from_config(self):
        from unittest.mock import MagicMock

        from engine.runtime_settings import RuntimeSettings
        cfg = MagicMock()
        cfg.text_scale = 1.8
        cfg.music_volume = 0.5
        cfg.sfx_volume = 0.5
        cfg.fog_enabled = False
        cfg.soft_shadows_enabled = False
        s = RuntimeSettings.from_config(cfg)
        assert s.text_scale == 1.8

    def test_from_config_missing_attr(self):
        from engine.runtime_settings import RuntimeSettings

        class BareConfig:
            music_volume = 1.0
            sfx_volume = 1.0
            fog_enabled = False
            soft_shadows_enabled = False

        s = RuntimeSettings.from_config(BareConfig())
        assert s.text_scale == 1.0

    def test_apply_pushes_text_scale(self):
        from unittest.mock import MagicMock

        from engine.runtime_settings import RuntimeSettings
        from engine.text_draw import get_text_scale, set_text_scale

        set_text_scale(1.0)  # reset
        s = RuntimeSettings(text_scale=1.75)
        window = MagicMock()
        window.audio = None
        window.engine_config = None
        s.apply(window)
        assert get_text_scale() == 1.75
        set_text_scale(1.0)  # restore

    def test_roundtrip(self):
        from engine.runtime_settings import RuntimeSettings
        s = RuntimeSettings(text_scale=1.3, music_volume=0.8, sfx_volume=0.6)
        payload = s.to_payload()
        s2 = RuntimeSettings.from_payload(payload)
        assert s2.text_scale == pytest.approx(1.3)
        assert s2.music_volume == pytest.approx(0.8)


# ===========================================================================
# draw_text_cached scale application
# ===========================================================================


class TestDrawTextCachedScale:
    """Verify that draw_text_cached applies the global text scale."""

    def test_scaled_font_size_in_fallback_path(self, monkeypatch):
        """When no cache is provided, draw_text falls back to arcade.draw_text.
        Verify the font_size argument is scaled."""
        from unittest.mock import MagicMock

        import engine.optional_arcade as oa
        import engine.text_draw as td

        monkeypatch.setattr(td, "_text_scale", 2.0)

        mock_arcade = MagicMock()
        # Delete Text attr so hasattr returns False → forces fallback path
        del mock_arcade.Text
        monkeypatch.setattr(oa, "arcade", mock_arcade)

        td.draw_text_cached("hello", 10, 20, font_size=12.0)

        mock_arcade.draw_text.assert_called_once()
        _, args, kwargs = mock_arcade.draw_text.mock_calls[0]
        actual_size = args[4] if len(args) > 4 else kwargs.get("font_size")
        assert actual_size == pytest.approx(24.0)

    def test_scale_1x_no_change(self, monkeypatch):
        """At 1.0x scale, font_size should be unchanged."""
        from unittest.mock import MagicMock

        import engine.optional_arcade as oa
        import engine.text_draw as td

        monkeypatch.setattr(td, "_text_scale", 1.0)

        mock_arcade = MagicMock()
        del mock_arcade.Text
        monkeypatch.setattr(oa, "arcade", mock_arcade)

        td.draw_text_cached("hi", 0, 0, font_size=14.0)

        _, args, kwargs = mock_arcade.draw_text.mock_calls[0]
        actual_size = args[4] if len(args) > 4 else kwargs.get("font_size")
        assert actual_size == pytest.approx(14.0)
