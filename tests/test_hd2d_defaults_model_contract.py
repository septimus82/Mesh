"""Contract tests for HD-2D defaults model.

Tests the pure model functions for:
- Default preset validation
- Auto-apply conditions
- Safe merge behavior
- Upgrade action behavior
"""

from __future__ import annotations

import pytest
from tests._typing import as_any


# =============================================================================
# Test Constants
# =============================================================================


class TestHd2dSettingKeys:
    """Tests for HD2D_SETTING_KEYS constant."""

    def test_hd2d_setting_keys_is_frozenset(self) -> None:
        """HD2D_SETTING_KEYS should be a frozenset."""
        from engine.editor.hd2d_defaults_model import HD2D_SETTING_KEYS

        assert isinstance(HD2D_SETTING_KEYS, frozenset)

    def test_hd2d_setting_keys_contains_expected_keys(self) -> None:
        """HD2D_SETTING_KEYS should contain all HD2D setting keys."""
        from engine.editor.hd2d_defaults_model import HD2D_SETTING_KEYS

        expected = {
            "depth_tint_enabled",
            "depth_tint_strength",
            "depth_tint_near_color",
            "depth_tint_far_color",
            "shadows_enabled",
            "shadows_contact_enabled",
            "shadows_ao_enabled",
            "outline_enabled",
            "outline_strength",
            "outline_radius_px",
            "outline_color_rgba",
        }
        assert expected == HD2D_SETTING_KEYS


# =============================================================================
# Test is_valid_default_preset_id
# =============================================================================


class TestIsValidDefaultPresetId:
    """Tests for is_valid_default_preset_id function."""

    def test_valid_preset_ids(self) -> None:
        """Valid preset IDs return True."""
        from engine.editor.hd2d_defaults_model import is_valid_default_preset_id

        assert is_valid_default_preset_id("soft") is True
        assert is_valid_default_preset_id("crisp") is True
        assert is_valid_default_preset_id("noir") is True
        assert is_valid_default_preset_id("dreamy") is True

    def test_none_returns_false(self) -> None:
        """None returns False."""
        from engine.editor.hd2d_defaults_model import is_valid_default_preset_id

        assert is_valid_default_preset_id(None) is False

    def test_empty_string_returns_false(self) -> None:
        """Empty string returns False."""
        from engine.editor.hd2d_defaults_model import is_valid_default_preset_id

        assert is_valid_default_preset_id("") is False

    def test_unknown_preset_returns_false(self) -> None:
        """Unknown preset ID returns False."""
        from engine.editor.hd2d_defaults_model import is_valid_default_preset_id

        assert is_valid_default_preset_id("unknown") is False
        assert is_valid_default_preset_id("custom") is False

    def test_non_string_returns_false(self) -> None:
        """Non-string values return False."""
        from engine.editor.hd2d_defaults_model import is_valid_default_preset_id

        assert is_valid_default_preset_id(as_any(123)) is False
        assert is_valid_default_preset_id(as_any([])) is False


# =============================================================================
# Test scene_has_hd2d_keys
# =============================================================================


class TestSceneHasHd2dKeys:
    """Tests for scene_has_hd2d_keys function."""

    def test_empty_scene_returns_false(self) -> None:
        """Empty scene returns False."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        assert scene_has_hd2d_keys({}) is False

    def test_scene_without_settings_returns_false(self) -> None:
        """Scene without settings returns False."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        assert scene_has_hd2d_keys({"entities": []}) is False

    def test_scene_with_empty_settings_returns_false(self) -> None:
        """Scene with empty settings returns False."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        assert scene_has_hd2d_keys({"settings": {}}) is False

    def test_scene_with_non_hd2d_settings_returns_false(self) -> None:
        """Scene with only non-HD2D settings returns False."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        scene = {"settings": {"world_width": 1920, "world_height": 1080}}
        assert scene_has_hd2d_keys(scene) is False

    def test_scene_with_hd2d_key_returns_true(self) -> None:
        """Scene with at least one HD2D key returns True."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        scene = {"settings": {"depth_tint_enabled": True}}
        assert scene_has_hd2d_keys(scene) is True

    def test_scene_with_multiple_hd2d_keys_returns_true(self) -> None:
        """Scene with multiple HD2D keys returns True."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        scene = {"settings": {"shadows_enabled": True, "outline_enabled": False}}
        assert scene_has_hd2d_keys(scene) is True

    def test_non_dict_returns_false(self) -> None:
        """Non-dict scene returns False."""
        from engine.editor.hd2d_defaults_model import scene_has_hd2d_keys

        assert scene_has_hd2d_keys(as_any(None)) is False
        assert scene_has_hd2d_keys(as_any("string")) is False


# =============================================================================
# Test should_auto_apply_default
# =============================================================================


class TestShouldAutoApplyDefault:
    """Tests for should_auto_apply_default function."""

    def test_returns_false_when_no_default_preset(self) -> None:
        """Returns False when default preset is None."""
        from engine.editor.hd2d_defaults_model import should_auto_apply_default

        scene = {"settings": {}}
        assert should_auto_apply_default(scene, None) is False

    def test_returns_false_when_invalid_default_preset(self) -> None:
        """Returns False when default preset is invalid."""
        from engine.editor.hd2d_defaults_model import should_auto_apply_default

        scene = {"settings": {}}
        assert should_auto_apply_default(scene, "unknown") is False

    def test_returns_false_when_scene_has_hd2d_keys(self) -> None:
        """Returns False when scene already has HD2D keys."""
        from engine.editor.hd2d_defaults_model import should_auto_apply_default

        scene = {"settings": {"depth_tint_enabled": True}}
        assert should_auto_apply_default(scene, "soft") is False

    def test_returns_true_when_conditions_met(self) -> None:
        """Returns True when default set and scene lacks HD2D keys."""
        from engine.editor.hd2d_defaults_model import should_auto_apply_default

        scene = {"settings": {"world_width": 1920}}
        assert should_auto_apply_default(scene, "soft") is True

    def test_returns_true_for_empty_scene(self) -> None:
        """Returns True for empty scene with valid default."""
        from engine.editor.hd2d_defaults_model import should_auto_apply_default

        assert should_auto_apply_default({}, "crisp") is True


# =============================================================================
# Test compute_safe_merge_patch
# =============================================================================


class TestComputeSafeMergePatch:
    """Tests for compute_safe_merge_patch function."""

    def test_returns_empty_for_invalid_preset(self) -> None:
        """Returns empty dict for invalid preset."""
        from engine.editor.hd2d_defaults_model import compute_safe_merge_patch

        scene = {"settings": {}}
        assert compute_safe_merge_patch(scene, "unknown") == {}

    def test_returns_full_patch_for_empty_settings(self) -> None:
        """Returns full patch when scene has no settings."""
        from engine.editor.hd2d_defaults_model import compute_safe_merge_patch
        from engine.editor.hd2d_look_presets_model import get_hd2d_preset_patch

        scene = {"settings": {}}
        patch = compute_safe_merge_patch(scene, "soft")
        expected = get_hd2d_preset_patch("soft")
        assert patch == expected

    def test_excludes_existing_keys(self) -> None:
        """Does not include keys that already exist in scene."""
        from engine.editor.hd2d_defaults_model import compute_safe_merge_patch

        scene = {"settings": {"depth_tint_enabled": False}}
        patch = compute_safe_merge_patch(scene, "soft")
        assert "depth_tint_enabled" not in patch

    def test_includes_only_missing_keys(self) -> None:
        """Only includes keys that are missing from scene settings."""
        from engine.editor.hd2d_defaults_model import compute_safe_merge_patch

        scene = {
            "settings": {
                "depth_tint_enabled": False,
                "shadows_enabled": False,
            }
        }
        patch = compute_safe_merge_patch(scene, "soft")
        # These should NOT be in patch (already in scene)
        assert "depth_tint_enabled" not in patch
        assert "shadows_enabled" not in patch
        # These should be in patch (missing from scene)
        assert "depth_tint_strength" in patch
        assert "outline_enabled" in patch


# =============================================================================
# Test apply_safe_merge
# =============================================================================


class TestApplySafeMerge:
    """Tests for apply_safe_merge function."""

    def test_does_not_mutate_input(self) -> None:
        """Does not mutate the input scene."""
        from engine.editor.hd2d_defaults_model import apply_safe_merge
        import copy

        scene = {"settings": {"world_width": 1920}}
        original = copy.deepcopy(scene)
        apply_safe_merge(scene, "soft")
        assert scene == original

    def test_returns_new_scene_with_merged_settings(self) -> None:
        """Returns a new scene with merged settings."""
        from engine.editor.hd2d_defaults_model import apply_safe_merge

        scene = {"settings": {"world_width": 1920}}
        result = apply_safe_merge(scene, "soft")
        assert "depth_tint_enabled" in result["settings"]
        assert result["settings"]["world_width"] == 1920

    def test_preserves_existing_values(self) -> None:
        """Preserves existing HD2D values."""
        from engine.editor.hd2d_defaults_model import apply_safe_merge

        scene = {"settings": {"depth_tint_enabled": False}}
        result = apply_safe_merge(scene, "soft")
        assert result["settings"]["depth_tint_enabled"] is False

    def test_returns_copy_for_invalid_preset(self) -> None:
        """Returns a deep copy when preset is invalid."""
        from engine.editor.hd2d_defaults_model import apply_safe_merge

        scene = {"settings": {"x": 1}}
        result = apply_safe_merge(scene, "unknown")
        assert result == scene
        assert result is not scene


# =============================================================================
# Test format_upgrade_undo_label
# =============================================================================


class TestFormatUpgradeUndoLabel:
    """Tests for format_upgrade_undo_label function."""

    def test_formats_known_preset(self) -> None:
        """Formats label with known preset name."""
        from engine.editor.hd2d_defaults_model import format_upgrade_undo_label

        assert format_upgrade_undo_label("soft") == "Upgrade Scene · HD2D Defaults (Soft)"
        assert format_upgrade_undo_label("crisp") == "Upgrade Scene · HD2D Defaults (Crisp)"
        assert format_upgrade_undo_label("noir") == "Upgrade Scene · HD2D Defaults (Noir)"
        assert format_upgrade_undo_label("dreamy") == "Upgrade Scene · HD2D Defaults (Dreamy)"

    def test_formats_unknown_preset_with_capitalized_id(self) -> None:
        """Formats unknown preset with capitalized ID."""
        from engine.editor.hd2d_defaults_model import format_upgrade_undo_label

        assert format_upgrade_undo_label("custom") == "Upgrade Scene · HD2D Defaults (Custom)"


# =============================================================================
# Test Workspace Settings Integration
# =============================================================================


class TestWorkspaceSettingsHd2dDefault:
    """Tests for hd2d_default_preset_id in WorkspaceSettings."""

    def test_default_value_is_none(self) -> None:
        """Default value for hd2d_default_preset_id is None."""
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings()
        assert settings.hd2d_default_preset_id is None

    def test_from_dict_with_valid_preset(self) -> None:
        """from_dict correctly loads valid preset ID."""
        from engine.workspace_settings import WorkspaceSettings

        data = {"hd2d_default_preset_id": "soft"}
        settings = WorkspaceSettings.from_dict(data)
        assert settings.hd2d_default_preset_id == "soft"

    def test_from_dict_with_none(self) -> None:
        """from_dict correctly handles None."""
        from engine.workspace_settings import WorkspaceSettings

        data = {"hd2d_default_preset_id": None}
        settings = WorkspaceSettings.from_dict(data)
        assert settings.hd2d_default_preset_id is None

    def test_from_dict_with_invalid_preset_returns_none(self) -> None:
        """from_dict returns None for invalid preset."""
        from engine.workspace_settings import WorkspaceSettings

        data = {"hd2d_default_preset_id": "unknown"}
        settings = WorkspaceSettings.from_dict(data)
        assert settings.hd2d_default_preset_id is None

    def test_from_dict_with_empty_string_returns_none(self) -> None:
        """from_dict returns None for empty string."""
        from engine.workspace_settings import WorkspaceSettings

        data = {"hd2d_default_preset_id": ""}
        settings = WorkspaceSettings.from_dict(data)
        assert settings.hd2d_default_preset_id is None

    def test_round_trip(self) -> None:
        """Settings can be serialized and deserialized."""
        from dataclasses import asdict
        from engine.workspace_settings import WorkspaceSettings

        original = WorkspaceSettings(hd2d_default_preset_id="crisp")
        data = asdict(original)
        loaded = WorkspaceSettings.from_dict(data)
        assert loaded.hd2d_default_preset_id == "crisp"


# =============================================================================
# Test Auto-Apply Does NOT Push Undo
# =============================================================================


class TestAutoApplyDoesNotPushUndo:
    """Tests ensuring auto-apply doesn't push undo or mark dirty."""

    def test_should_auto_apply_is_pure(self) -> None:
        """should_auto_apply_default is a pure function."""
        from engine.editor.hd2d_defaults_model import should_auto_apply_default

        scene = {"settings": {}}
        # Call multiple times - should always return same result
        r1 = should_auto_apply_default(scene, "soft")
        r2 = should_auto_apply_default(scene, "soft")
        r3 = should_auto_apply_default(scene, "soft")
        assert r1 == r2 == r3 == True  # noqa: E712

    def test_apply_safe_merge_does_not_modify_input(self) -> None:
        """apply_safe_merge does not modify the input scene."""
        from engine.editor.hd2d_defaults_model import apply_safe_merge
        import copy

        scene = {"settings": {"x": 1}}
        original = copy.deepcopy(scene)
        apply_safe_merge(scene, "soft")
        assert scene == original


# =============================================================================
# Test Upgrade Action Pushes ONE Undo Entry
# =============================================================================


class TestUpgradeActionPushesOneUndoEntry:
    """Tests for upgrade action undo behavior."""

    def test_upgrade_undo_label_contains_preset_name(self) -> None:
        """Upgrade undo label contains the preset name."""
        from engine.editor.hd2d_defaults_model import format_upgrade_undo_label

        label = format_upgrade_undo_label("soft")
        assert "Soft" in label
        assert "Upgrade Scene" in label
        assert "HD2D Defaults" in label


# =============================================================================
# Test Deterministic Output
# =============================================================================


class TestDeterministicOutput:
    """Tests for deterministic behavior."""

    def test_compute_safe_merge_patch_is_deterministic(self) -> None:
        """compute_safe_merge_patch produces consistent output."""
        from engine.editor.hd2d_defaults_model import compute_safe_merge_patch

        scene = {"settings": {"x": 1}}
        p1 = compute_safe_merge_patch(scene, "soft")
        p2 = compute_safe_merge_patch(scene, "soft")
        p3 = compute_safe_merge_patch(scene, "soft")
        assert p1 == p2 == p3

    def test_apply_safe_merge_is_deterministic(self) -> None:
        """apply_safe_merge produces consistent output."""
        from engine.editor.hd2d_defaults_model import apply_safe_merge

        scene = {"settings": {"x": 1}}
        r1 = apply_safe_merge(scene, "soft")
        r2 = apply_safe_merge(scene, "soft")
        r3 = apply_safe_merge(scene, "soft")
        assert r1 == r2 == r3


# =============================================================================
# Test Editor Action Exists
# =============================================================================


class TestUpgradeSceneActionExists:
    """Tests for upgrade scene action registration."""

    def test_action_is_registered(self) -> None:
        """Action is in the actions list."""
        from engine.editor.editor_actions import get_editor_actions

        actions = get_editor_actions(None, None)
        action_ids = [a.id for a in actions]
        assert "editor.hd2d.defaults.upgrade_scene" in action_ids

    def test_action_has_correct_properties(self) -> None:
        """Action has expected properties."""
        from engine.editor.editor_actions import get_editor_actions

        actions = get_editor_actions(None, None)
        action = next(a for a in actions if a.id == "editor.hd2d.defaults.upgrade_scene")
        assert action.title == "Upgrade Scene to HD2D Defaults"
        assert "hd2d" in action.keywords
        assert "upgrade" in action.keywords
        assert action.in_palette is True
