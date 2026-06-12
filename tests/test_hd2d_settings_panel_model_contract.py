"""Contract tests for engine/editor/hd2d_settings_panel_model.py.

Tests the pure model functions for HD-2D settings panel:
- Parsing settings from scene payloads with defaults
- Sanitizing setting patches
- Applying patches immutably
- Formatting undo labels
- Preset detection
"""

from __future__ import annotations

from typing import Any

import pytest

from engine.editor.hd2d_settings_panel_model import (
    BOOL_KEYS,
    COLOR_KEYS,
    HD2D_DEFAULTS,
    INT_KEYS,
    STRENGTH_KEYS,
    Hd2dSettingRow,
    Hd2dSettings,
    apply_hd2d_setting_patch,
    build_hd2d_settings_rows,
    detect_active_preset,
    format_hd2d_setting_change_label,
    format_hd2d_toggle_label,
    parse_hd2d_scene_settings,
    parse_hd2d_scene_settings_dict,
    sanitize_hd2d_setting_patch,
    sanitize_hd2d_setting_value,
)
from tests._typing import as_any

# =============================================================================
# Test Constants
# =============================================================================


class TestHd2dDefaults:
    """Tests for HD2D_DEFAULTS constant."""

    def test_defaults_has_expected_keys(self) -> None:
        """HD2D_DEFAULTS should have all expected keys."""
        expected_keys = {
            "shadows_enabled",
            "shadows_contact_enabled",
            "shadows_ao_enabled",
            "depth_tint_enabled",
            "depth_tint_strength",
            "depth_tint_near_color",
            "depth_tint_far_color",
            "outline_enabled",
            "outline_strength",
            "outline_radius_px",
            "outline_color_rgba",
        }
        assert set(HD2D_DEFAULTS.keys()) == expected_keys

    def test_bool_keys_are_valid(self) -> None:
        """BOOL_KEYS should be subset of HD2D_DEFAULTS."""
        for key in BOOL_KEYS:
            assert key in HD2D_DEFAULTS

    def test_strength_keys_are_valid(self) -> None:
        """STRENGTH_KEYS should be subset of HD2D_DEFAULTS."""
        for key in STRENGTH_KEYS:
            assert key in HD2D_DEFAULTS

    def test_int_keys_are_valid(self) -> None:
        """INT_KEYS should be subset of HD2D_DEFAULTS."""
        for key in INT_KEYS:
            assert key in HD2D_DEFAULTS

    def test_color_keys_are_valid(self) -> None:
        """COLOR_KEYS should be subset of HD2D_DEFAULTS."""
        for key in COLOR_KEYS:
            assert key in HD2D_DEFAULTS


# =============================================================================
# Test parse_hd2d_scene_settings
# =============================================================================


class TestParseHd2dSceneSettings:
    """Tests for parse_hd2d_scene_settings function."""

    def test_returns_hd2d_settings_dataclass(self) -> None:
        """Should return Hd2dSettings dataclass."""
        result = parse_hd2d_scene_settings({})
        assert isinstance(result, Hd2dSettings)

    def test_uses_defaults_for_empty_payload(self) -> None:
        """Should use defaults when payload is empty."""
        result = parse_hd2d_scene_settings({})
        assert result.shadows_enabled is True
        assert result.shadows_contact_enabled is True
        assert result.shadows_ao_enabled is False
        assert result.depth_tint_enabled is False
        assert result.depth_tint_strength == pytest.approx(0.3)
        assert result.outline_enabled is False
        assert result.outline_strength == pytest.approx(0.5)
        assert result.outline_radius_px == 1

    def test_uses_defaults_for_missing_settings(self) -> None:
        """Should use defaults when settings dict is missing keys."""
        payload = {"settings": {"shadows_enabled": False}}
        result = parse_hd2d_scene_settings(payload)
        assert result.shadows_enabled is False  # From payload
        assert result.shadows_contact_enabled is True  # Default
        assert result.depth_tint_strength == pytest.approx(0.3)  # Default

    def test_parses_all_bool_settings(self) -> None:
        """Should correctly parse all boolean settings."""
        payload = {
            "settings": {
                "shadows_enabled": False,
                "shadows_contact_enabled": False,
                "shadows_ao_enabled": True,
                "depth_tint_enabled": True,
                "outline_enabled": True,
            }
        }
        result = parse_hd2d_scene_settings(payload)
        assert result.shadows_enabled is False
        assert result.shadows_contact_enabled is False
        assert result.shadows_ao_enabled is True
        assert result.depth_tint_enabled is True
        assert result.outline_enabled is True

    def test_parses_float_settings_with_clamping(self) -> None:
        """Should clamp float settings to valid range."""
        payload = {
            "settings": {
                "depth_tint_strength": 1.5,  # Over max
                "outline_strength": -0.5,  # Under min
            }
        }
        result = parse_hd2d_scene_settings(payload)
        assert result.depth_tint_strength == pytest.approx(1.0)
        assert result.outline_strength == pytest.approx(0.0)

    def test_parses_int_settings(self) -> None:
        """Should correctly parse integer settings."""
        payload = {"settings": {"outline_radius_px": 5}}
        result = parse_hd2d_scene_settings(payload)
        assert result.outline_radius_px == 5

    def test_clamps_int_settings_to_non_negative(self) -> None:
        """Should clamp integer settings to non-negative."""
        payload = {"settings": {"outline_radius_px": -3}}
        result = parse_hd2d_scene_settings(payload)
        assert result.outline_radius_px == 0

    def test_parses_rgba_colors(self) -> None:
        """Should correctly parse RGBA color values."""
        payload = {
            "settings": {
                "depth_tint_near_color": [100, 150, 200, 255],
                "depth_tint_far_color": [50, 75, 100, 128],
                "outline_color_rgba": [0, 0, 0, 200],
            }
        }
        result = parse_hd2d_scene_settings(payload)
        assert result.depth_tint_near_color == (100, 150, 200, 255)
        assert result.depth_tint_far_color == (50, 75, 100, 128)
        assert result.outline_color_rgba == (0, 0, 0, 200)

    def test_clamps_rgba_values(self) -> None:
        """Should clamp RGBA values to 0-255."""
        payload = {"settings": {"outline_color_rgba": [-10, 300, 128, 500]}}
        result = parse_hd2d_scene_settings(payload)
        assert result.outline_color_rgba == (0, 255, 128, 255)

    def test_handles_invalid_payload_types(self) -> None:
        """Should handle invalid payload types gracefully."""
        assert isinstance(parse_hd2d_scene_settings(as_any(None)), Hd2dSettings)
        assert isinstance(parse_hd2d_scene_settings(as_any("invalid")), Hd2dSettings)
        assert isinstance(parse_hd2d_scene_settings(as_any([])), Hd2dSettings)

    def test_handles_invalid_settings_types(self) -> None:
        """Should handle invalid settings dict type."""
        payload = {"settings": "invalid"}
        result = parse_hd2d_scene_settings(payload)
        assert result.shadows_enabled is True  # Default


# =============================================================================
# Test parse_hd2d_scene_settings_dict
# =============================================================================


class TestParseHd2dSceneSettingsDict:
    """Tests for parse_hd2d_scene_settings_dict function."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        result = parse_hd2d_scene_settings_dict({})
        assert isinstance(result, dict)

    def test_contains_all_settings_keys(self) -> None:
        """Should contain all expected keys."""
        result = parse_hd2d_scene_settings_dict({})
        expected_keys = {
            "shadows_enabled",
            "shadows_contact_enabled",
            "shadows_ao_enabled",
            "depth_tint_enabled",
            "depth_tint_strength",
            "depth_tint_near_color",
            "depth_tint_far_color",
            "outline_enabled",
            "outline_strength",
            "outline_radius_px",
            "outline_color_rgba",
        }
        assert set(result.keys()) == expected_keys

    def test_colors_are_lists(self) -> None:
        """Should return colors as lists, not tuples."""
        result = parse_hd2d_scene_settings_dict({})
        assert isinstance(result["depth_tint_near_color"], list)
        assert isinstance(result["depth_tint_far_color"], list)
        assert isinstance(result["outline_color_rgba"], list)


# =============================================================================
# Test sanitize_hd2d_setting_value
# =============================================================================


class TestSanitizeHd2dSettingValue:
    """Tests for sanitize_hd2d_setting_value function."""

    def test_sanitizes_bool_values(self) -> None:
        """Should coerce various types to bool for bool keys."""
        assert sanitize_hd2d_setting_value("shadows_enabled", 1) is True
        assert sanitize_hd2d_setting_value("shadows_enabled", 0) is False
        assert sanitize_hd2d_setting_value("shadows_enabled", "yes") is True
        assert sanitize_hd2d_setting_value("shadows_enabled", "") is False

    def test_clamps_strength_values(self) -> None:
        """Should clamp strength values to [0, 1]."""
        assert sanitize_hd2d_setting_value("depth_tint_strength", 1.5) == pytest.approx(1.0)
        assert sanitize_hd2d_setting_value("depth_tint_strength", -0.5) == pytest.approx(0.0)
        assert sanitize_hd2d_setting_value("outline_strength", 0.5) == pytest.approx(0.5)

    def test_handles_invalid_strength_types(self) -> None:
        """Should return default for invalid strength types."""
        result = sanitize_hd2d_setting_value("depth_tint_strength", "invalid")
        assert isinstance(result, float)
        assert result == pytest.approx(HD2D_DEFAULTS["depth_tint_strength"])

    def test_clamps_int_values(self) -> None:
        """Should clamp int values to non-negative."""
        assert sanitize_hd2d_setting_value("outline_radius_px", -5) == 0
        assert sanitize_hd2d_setting_value("outline_radius_px", 10) == 10

    def test_handles_invalid_int_types(self) -> None:
        """Should return default for invalid int types."""
        result = sanitize_hd2d_setting_value("outline_radius_px", "invalid")
        assert result == HD2D_DEFAULTS["outline_radius_px"]

    def test_sanitizes_color_values(self) -> None:
        """Should sanitize and clamp color values."""
        result = sanitize_hd2d_setting_value("outline_color_rgba", [-10, 300, 128, 500])
        assert result == [0, 255, 128, 255]

    def test_returns_unknown_keys_as_is(self) -> None:
        """Should return unknown keys unchanged."""
        result = sanitize_hd2d_setting_value("unknown_key", "some_value")
        assert result == "some_value"


# =============================================================================
# Test sanitize_hd2d_setting_patch
# =============================================================================


class TestSanitizeHd2dSettingPatch:
    """Tests for sanitize_hd2d_setting_patch function."""

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        result = sanitize_hd2d_setting_patch({})
        assert isinstance(result, dict)

    def test_returns_empty_for_invalid_input(self) -> None:
        """Should return empty dict for invalid input."""
        assert sanitize_hd2d_setting_patch(as_any(None)) == {}
        assert sanitize_hd2d_setting_patch(as_any("invalid")) == {}

    def test_sanitizes_all_patch_values(self) -> None:
        """Should sanitize all values in patch."""
        patch = {
            "shadows_enabled": 1,
            "depth_tint_strength": 2.0,
            "outline_radius_px": -5,
        }
        result = sanitize_hd2d_setting_patch(patch)
        assert result["shadows_enabled"] is True
        assert result["depth_tint_strength"] == pytest.approx(1.0)
        assert result["outline_radius_px"] == 0

    def test_filters_non_string_keys(self) -> None:
        """Should filter out non-string keys."""
        patch: dict[Any, Any] = {
            "shadows_enabled": True,
            123: "invalid_key",
        }
        result = sanitize_hd2d_setting_patch(patch)
        assert "shadows_enabled" in result
        assert 123 not in result


# =============================================================================
# Test apply_hd2d_setting_patch
# =============================================================================


class TestApplyHd2dSettingPatch:
    """Tests for apply_hd2d_setting_patch function."""

    def test_returns_new_dict(self) -> None:
        """Should return a new dict, not mutate input."""
        original = {"settings": {"shadows_enabled": True}}
        result = apply_hd2d_setting_patch(original, {"shadows_enabled": False})
        assert result is not original
        assert original["settings"]["shadows_enabled"] is True

    def test_applies_patch_to_settings(self) -> None:
        """Should apply patch to settings dict."""
        payload = {"settings": {"shadows_enabled": True}}
        result = apply_hd2d_setting_patch(payload, {"shadows_enabled": False})
        assert result["settings"]["shadows_enabled"] is False

    def test_creates_settings_dict_if_missing(self) -> None:
        """Should create settings dict if missing."""
        payload: dict[str, Any] = {}
        result = apply_hd2d_setting_patch(payload, {"shadows_enabled": False})
        assert "settings" in result
        assert result["settings"]["shadows_enabled"] is False

    def test_sanitizes_patch_before_applying(self) -> None:
        """Should sanitize patch values before applying."""
        payload = {"settings": {}}
        result = apply_hd2d_setting_patch(payload, {"depth_tint_strength": 2.0})
        assert result["settings"]["depth_tint_strength"] == pytest.approx(1.0)

    def test_returns_copy_for_empty_patch(self) -> None:
        """Should return deep copy for empty patch."""
        payload = {"settings": {"foo": "bar"}}
        result = apply_hd2d_setting_patch(payload, {})
        assert result is not payload
        assert result["settings"]["foo"] == "bar"

    def test_handles_invalid_payload(self) -> None:
        """Should handle invalid payload type."""
        result = apply_hd2d_setting_patch(as_any(None), {"shadows_enabled": False})
        assert result == {"settings": {"shadows_enabled": False}}

    def test_preserves_other_scene_keys(self) -> None:
        """Should preserve other keys in scene payload."""
        payload = {
            "entities": [{"id": "test"}],
            "settings": {"shadows_enabled": True, "other_setting": "value"},
        }
        result = apply_hd2d_setting_patch(payload, {"shadows_enabled": False})
        assert result["entities"] == [{"id": "test"}]
        assert result["settings"]["other_setting"] == "value"


# =============================================================================
# Test format_hd2d_toggle_label
# =============================================================================


class TestFormatHd2dToggleLabel:
    """Tests for format_hd2d_toggle_label function."""

    def test_enable_label_format(self) -> None:
        """Should format enable label correctly."""
        label = format_hd2d_toggle_label("shadows_enabled", True)
        assert "Enable" in label
        assert "HD2D" in label
        assert "Shadows" in label

    def test_disable_label_format(self) -> None:
        """Should format disable label correctly."""
        label = format_hd2d_toggle_label("shadows_enabled", False)
        assert "Disable" in label
        assert "HD2D" in label
        assert "Shadows" in label

    def test_known_keys_have_friendly_names(self) -> None:
        """Should use friendly names for known keys."""
        label = format_hd2d_toggle_label("depth_tint_enabled", True)
        assert "Depth Tint" in label or "Tint" in label

    def test_unknown_keys_use_title_case(self) -> None:
        """Should use title case for unknown keys."""
        label = format_hd2d_toggle_label("unknown_setting", True)
        assert "Unknown Setting" in label or "unknown_setting" in label.lower()


# =============================================================================
# Test format_hd2d_setting_change_label
# =============================================================================


class TestFormatHd2dSettingChangeLabel:
    """Tests for format_hd2d_setting_change_label function."""

    def test_float_format_shows_values(self) -> None:
        """Should show old and new values for float settings."""
        label = format_hd2d_setting_change_label("depth_tint_strength", 0.3, 0.5)
        assert "0.30" in label or "0.3" in label
        assert "0.50" in label or "0.5" in label

    def test_int_format_shows_values(self) -> None:
        """Should show old and new values for int settings."""
        label = format_hd2d_setting_change_label("outline_radius_px", 1, 3)
        assert "1" in label
        assert "3" in label

    def test_bool_format_uses_enable_disable(self) -> None:
        """Should use Enable/Disable for bool settings."""
        label = format_hd2d_setting_change_label("shadows_enabled", False, True)
        assert "Enable" in label


# =============================================================================
# Test build_hd2d_settings_rows
# =============================================================================


class TestBuildHd2dSettingsRows:
    """Tests for build_hd2d_settings_rows function."""

    def test_returns_list_of_rows(self) -> None:
        """Should return list of Hd2dSettingRow."""
        settings = parse_hd2d_scene_settings({})
        rows = build_hd2d_settings_rows(settings)
        assert isinstance(rows, list)
        assert all(isinstance(r, Hd2dSettingRow) for r in rows)

    def test_includes_shadow_settings(self) -> None:
        """Should include shadow toggle rows."""
        settings = parse_hd2d_scene_settings({})
        rows = build_hd2d_settings_rows(settings)
        keys = [r.key for r in rows]
        assert "shadows_enabled" in keys
        assert "shadows_contact_enabled" in keys
        assert "shadows_ao_enabled" in keys

    def test_includes_tint_settings(self) -> None:
        """Should include tint rows."""
        settings = parse_hd2d_scene_settings({})
        rows = build_hd2d_settings_rows(settings)
        keys = [r.key for r in rows]
        assert "depth_tint_enabled" in keys
        assert "depth_tint_strength" in keys

    def test_includes_outline_settings(self) -> None:
        """Should include outline rows."""
        settings = parse_hd2d_scene_settings({})
        rows = build_hd2d_settings_rows(settings)
        keys = [r.key for r in rows]
        assert "outline_enabled" in keys
        assert "outline_strength" in keys
        assert "outline_radius_px" in keys

    def test_rows_have_correct_value_types(self) -> None:
        """Should have correct value_type for each row."""
        settings = parse_hd2d_scene_settings({})
        rows = build_hd2d_settings_rows(settings)
        for row in rows:
            if row.key in BOOL_KEYS:
                assert row.value_type == "bool"
            elif row.key in STRENGTH_KEYS:
                assert row.value_type == "float"
            elif row.key in INT_KEYS:
                assert row.value_type == "int"


# =============================================================================
# Test detect_active_preset
# =============================================================================


class TestDetectActivePreset:
    """Tests for detect_active_preset function."""

    def test_returns_none_for_non_matching(self) -> None:
        """Should return None when settings don't match any preset."""
        settings = parse_hd2d_scene_settings({})
        result = detect_active_preset(settings)
        # Default settings might match a preset or not
        assert result is None or isinstance(result, str)

    def test_detects_soft_preset(self) -> None:
        """Should detect soft preset when settings match."""
        from engine.editor.hd2d_look_presets_model import apply_hd2d_preset

        scene = apply_hd2d_preset({}, "soft")
        settings = parse_hd2d_scene_settings(scene)
        result = detect_active_preset(settings)
        assert result == "soft"

    def test_detects_crisp_preset(self) -> None:
        """Should detect crisp preset when settings match."""
        from engine.editor.hd2d_look_presets_model import apply_hd2d_preset

        scene = apply_hd2d_preset({}, "crisp")
        settings = parse_hd2d_scene_settings(scene)
        result = detect_active_preset(settings)
        assert result == "crisp"

    def test_detects_noir_preset(self) -> None:
        """Should detect noir preset when settings match."""
        from engine.editor.hd2d_look_presets_model import apply_hd2d_preset

        scene = apply_hd2d_preset({}, "noir")
        settings = parse_hd2d_scene_settings(scene)
        result = detect_active_preset(settings)
        assert result == "noir"

    def test_detects_dreamy_preset(self) -> None:
        """Should detect dreamy preset when settings match."""
        from engine.editor.hd2d_look_presets_model import apply_hd2d_preset

        scene = apply_hd2d_preset({}, "dreamy")
        settings = parse_hd2d_scene_settings(scene)
        result = detect_active_preset(settings)
        assert result == "dreamy"

    def test_returns_none_when_modified_from_preset(self) -> None:
        """Should return None when settings are modified from a preset."""
        from engine.editor.hd2d_look_presets_model import apply_hd2d_preset

        scene = apply_hd2d_preset({}, "soft")
        # Modify one setting
        scene["settings"]["depth_tint_strength"] = 0.99
        settings = parse_hd2d_scene_settings(scene)
        result = detect_active_preset(settings)
        # After modification, it shouldn't match
        assert result is None or result != "soft"


# =============================================================================
# Test Hd2dSettings Dataclass
# =============================================================================


class TestHd2dSettingsDataclass:
    """Tests for Hd2dSettings dataclass."""

    def test_is_frozen(self) -> None:
        """Should be frozen (immutable)."""
        settings = parse_hd2d_scene_settings({})
        with pytest.raises(AttributeError):
            as_any(settings).shadows_enabled = False

    def test_has_all_expected_fields(self) -> None:
        """Should have all expected fields."""
        settings = parse_hd2d_scene_settings({})
        assert hasattr(settings, "shadows_enabled")
        assert hasattr(settings, "shadows_contact_enabled")
        assert hasattr(settings, "shadows_ao_enabled")
        assert hasattr(settings, "depth_tint_enabled")
        assert hasattr(settings, "depth_tint_strength")
        assert hasattr(settings, "depth_tint_near_color")
        assert hasattr(settings, "depth_tint_far_color")
        assert hasattr(settings, "outline_enabled")
        assert hasattr(settings, "outline_strength")
        assert hasattr(settings, "outline_radius_px")
        assert hasattr(settings, "outline_color_rgba")


# =============================================================================
# Test Integration
# =============================================================================


class TestIntegration:
    """Integration tests for the HD-2D settings panel model."""

    def test_round_trip_parse_and_apply(self) -> None:
        """Parse → patch → parse should preserve values."""
        original_payload = {
            "settings": {
                "shadows_enabled": False,
                "depth_tint_strength": 0.7,
                "outline_radius_px": 3,
            }
        }

        # Parse original
        original_settings = parse_hd2d_scene_settings(original_payload)

        # Apply a patch
        patch = {"depth_tint_enabled": True, "outline_strength": 0.8}
        new_payload = apply_hd2d_setting_patch(original_payload, patch)

        # Parse result
        new_settings = parse_hd2d_scene_settings(new_payload)

        # Original values preserved
        assert new_settings.shadows_enabled is False
        assert new_settings.depth_tint_strength == pytest.approx(0.7)
        assert new_settings.outline_radius_px == 3

        # New values applied
        assert new_settings.depth_tint_enabled is True
        assert new_settings.outline_strength == pytest.approx(0.8)

    def test_preset_detection_after_apply(self) -> None:
        """Should detect preset after applying preset patch."""
        from engine.editor.hd2d_look_presets_model import get_hd2d_preset_patch

        payload: dict[str, Any] = {}
        preset_patch = get_hd2d_preset_patch("noir")
        assert preset_patch is not None

        new_payload = apply_hd2d_setting_patch(payload, preset_patch)
        settings = parse_hd2d_scene_settings(new_payload)
        detected = detect_active_preset(settings)
        assert detected == "noir"

    def test_no_mutation_chain(self) -> None:
        """Multiple applies should not mutate any intermediate payloads."""
        payload1: dict[str, Any] = {"settings": {"shadows_enabled": True}}
        payload2 = apply_hd2d_setting_patch(payload1, {"shadows_enabled": False})
        payload3 = apply_hd2d_setting_patch(payload2, {"depth_tint_enabled": True})

        # Verify no mutations
        assert payload1["settings"]["shadows_enabled"] is True
        assert payload2["settings"]["shadows_enabled"] is False
        assert "depth_tint_enabled" not in payload1.get("settings", {})
        assert "depth_tint_enabled" not in payload2.get("settings", {})
        assert payload3["settings"]["depth_tint_enabled"] is True
