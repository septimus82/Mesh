"""Contract tests for HD-2D look presets model.

These tests verify:
- Preset list order is stable and deterministic
- Preset patches are deterministic
- apply_hd2d_preset produces expected patched settings
- Editor actions push labeled undo entries
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from engine.editor.hd2d_look_presets_model import (
    Hd2dLookPreset,
    apply_hd2d_preset,
    get_hd2d_preset_name,
    get_hd2d_preset_patch,
    list_hd2d_presets,
)
from engine.editor.editor_actions import get_editor_actions, run_editor_action


class TestPresetListStability:
    """Tests for list_hd2d_presets stability."""

    def test_list_returns_four_presets(self) -> None:
        presets = list_hd2d_presets()
        assert len(presets) == 4

    def test_list_order_is_deterministic(self) -> None:
        """Preset order must be stable across calls."""
        presets1 = list_hd2d_presets()
        presets2 = list_hd2d_presets()
        assert [p.id for p in presets1] == [p.id for p in presets2]

    def test_list_order_is_soft_crisp_noir_dreamy(self) -> None:
        """Preset order must be Soft, Crisp, Noir, Dreamy."""
        presets = list_hd2d_presets()
        expected_ids = ["soft", "crisp", "noir", "dreamy"]
        expected_names = ["Soft", "Crisp", "Noir", "Dreamy"]
        assert [p.id for p in presets] == expected_ids
        assert [p.name for p in presets] == expected_names

    def test_presets_are_frozen_dataclasses(self) -> None:
        """Presets must be frozen to prevent accidental mutation."""
        presets = list_hd2d_presets()
        for preset in presets:
            assert isinstance(preset, Hd2dLookPreset)


class TestPresetPatchDeterminism:
    """Tests for get_hd2d_preset_patch determinism."""

    def test_patch_for_unknown_id_returns_none(self) -> None:
        assert get_hd2d_preset_patch("unknown") is None
        assert get_hd2d_preset_patch("") is None

    def test_patch_is_deterministic(self) -> None:
        """Same preset ID must return identical patch."""
        for preset_id in ["soft", "crisp", "noir", "dreamy"]:
            patch1 = get_hd2d_preset_patch(preset_id)
            patch2 = get_hd2d_preset_patch(preset_id)
            assert patch1 == patch2

    def test_patch_returns_copy_not_original(self) -> None:
        """Patch must be a copy to prevent mutation of source data."""
        patch1 = get_hd2d_preset_patch("soft")
        patch2 = get_hd2d_preset_patch("soft")
        assert patch1 is not patch2
        # Mutating one should not affect the other
        assert patch1 is not None
        patch1["depth_tint_enabled"] = False
        patch3 = get_hd2d_preset_patch("soft")
        assert patch3 is not None
        assert patch3["depth_tint_enabled"] is True

    def test_soft_patch_contains_expected_keys(self) -> None:
        patch = get_hd2d_preset_patch("soft")
        assert patch is not None
        expected_keys = {
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
        assert set(patch.keys()) == expected_keys

    def test_all_presets_have_consistent_keys(self) -> None:
        """All presets must have the same keys."""
        patches = [get_hd2d_preset_patch(pid) for pid in ["soft", "crisp", "noir", "dreamy"]]
        assert all(p is not None for p in patches)
        key_sets = [set(p.keys()) for p in patches if p is not None]
        assert all(ks == key_sets[0] for ks in key_sets)


class TestPresetNameLookup:
    """Tests for get_hd2d_preset_name."""

    def test_name_lookup_returns_correct_names(self) -> None:
        assert get_hd2d_preset_name("soft") == "Soft"
        assert get_hd2d_preset_name("crisp") == "Crisp"
        assert get_hd2d_preset_name("noir") == "Noir"
        assert get_hd2d_preset_name("dreamy") == "Dreamy"

    def test_name_lookup_returns_none_for_unknown(self) -> None:
        assert get_hd2d_preset_name("unknown") is None
        assert get_hd2d_preset_name("") is None


class TestApplyPreset:
    """Tests for apply_hd2d_preset function."""

    def test_apply_unknown_preset_returns_copy(self) -> None:
        scene = {"settings": {"foo": "bar"}}
        result = apply_hd2d_preset(scene, "unknown")
        assert result == scene
        assert result is not scene

    def test_apply_creates_settings_if_missing(self) -> None:
        scene: dict[str, Any] = {}
        result = apply_hd2d_preset(scene, "soft")
        assert "settings" in result
        assert isinstance(result["settings"], dict)
        assert result["settings"]["depth_tint_enabled"] is True

    def test_apply_merges_with_existing_settings(self) -> None:
        scene = {"settings": {"custom_key": "preserved", "depth_tint_enabled": False}}
        result = apply_hd2d_preset(scene, "soft")
        assert result["settings"]["custom_key"] == "preserved"
        assert result["settings"]["depth_tint_enabled"] is True

    def test_apply_does_not_mutate_original(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        original = copy.deepcopy(scene)
        _ = apply_hd2d_preset(scene, "soft")
        assert scene == original

    def test_apply_returns_deterministic_result(self) -> None:
        scene = {"settings": {"foo": "bar"}}
        result1 = apply_hd2d_preset(scene, "crisp")
        result2 = apply_hd2d_preset(scene, "crisp")
        assert result1 == result2

    def test_apply_does_not_touch_entities(self) -> None:
        scene = {
            "settings": {},
            "entities": [{"id": "e1", "overrides": {"special": True}}],
        }
        result = apply_hd2d_preset(scene, "noir")
        assert result["entities"] == scene["entities"]


class _StubSceneController:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._loaded_scene_data = payload


class _StubEditor:
    def __init__(self) -> None:
        self.dirty_calls = 0
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []

    def _mark_dirty(self) -> None:
        self.dirty_calls += 1

    def _push_command(self, cmd: dict[str, Any]) -> None:
        self.undo_stack.append(cmd)
        self.redo_stack.clear()


class _StubWindow:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.scene_controller = _StubSceneController(payload)
        self.editor_controller = _StubEditor()


class TestEditorActionsRegistration:
    """Tests for HD-2D preset editor actions."""

    def _find_action_ids(self, prefix: str) -> list[str]:
        return [action.id for action in get_editor_actions(None, None) if action.id.startswith(prefix)]

    def test_hd2d_preset_actions_registered_in_stable_order(self) -> None:
        expected = [
            "editor.hd2d.preset.soft.apply",
            "editor.hd2d.preset.crisp.apply",
            "editor.hd2d.preset.noir.apply",
            "editor.hd2d.preset.dreamy.apply",
        ]
        assert self._find_action_ids("editor.hd2d.preset.") == expected

    def test_hd2d_preset_actions_have_correct_group(self) -> None:
        actions = get_editor_actions(None, None)
        by_id = {action.id: action for action in actions}
        for action_id in [
            "editor.hd2d.preset.soft.apply",
            "editor.hd2d.preset.crisp.apply",
            "editor.hd2d.preset.noir.apply",
            "editor.hd2d.preset.dreamy.apply",
        ]:
            assert by_id[action_id].group == "View"

    def test_hd2d_preset_actions_in_palette_and_menu(self) -> None:
        actions = get_editor_actions(None, None)
        by_id = {action.id: action for action in actions}
        for action_id in [
            "editor.hd2d.preset.soft.apply",
            "editor.hd2d.preset.crisp.apply",
            "editor.hd2d.preset.noir.apply",
            "editor.hd2d.preset.dreamy.apply",
        ]:
            assert by_id[action_id].in_palette is True
            assert by_id[action_id].in_menu is True

    def test_hd2d_preset_actions_have_searchable_keywords(self) -> None:
        actions = get_editor_actions(None, None)
        by_id = {action.id: action for action in actions}
        for action_id in [
            "editor.hd2d.preset.soft.apply",
            "editor.hd2d.preset.crisp.apply",
            "editor.hd2d.preset.noir.apply",
            "editor.hd2d.preset.dreamy.apply",
        ]:
            keywords = by_id[action_id].keywords
            assert "hd2d" in keywords
            assert "preset" in keywords


class TestEditorActionsEnabled:
    """Tests for HD-2D preset actions enabled state."""

    def test_actions_disabled_without_scene(self) -> None:
        window = SimpleNamespace(scene_controller=None, editor_controller=None)
        actions = get_editor_actions(None, window)
        by_id = {action.id: action for action in actions}
        for action_id in [
            "editor.hd2d.preset.soft.apply",
            "editor.hd2d.preset.crisp.apply",
            "editor.hd2d.preset.noir.apply",
            "editor.hd2d.preset.dreamy.apply",
        ]:
            assert by_id[action_id].enabled(None, window) is False

    def test_actions_enabled_with_scene_loaded(self) -> None:
        window = _StubWindow({"settings": {}})
        actions = get_editor_actions(window.editor_controller, window)
        by_id = {action.id: action for action in actions}
        for action_id in [
            "editor.hd2d.preset.soft.apply",
            "editor.hd2d.preset.crisp.apply",
            "editor.hd2d.preset.noir.apply",
            "editor.hd2d.preset.dreamy.apply",
        ]:
            assert by_id[action_id].enabled(window.editor_controller, window) is True


class TestEditorActionsUndoHistory:
    """Tests for HD-2D preset actions undo history integration."""

    def test_applying_preset_pushes_undo_entry(self) -> None:
        window = _StubWindow({"settings": {"depth_tint_enabled": False}})
        assert len(window.editor_controller.undo_stack) == 0

        run_editor_action("editor.hd2d.preset.soft.apply", window.editor_controller, window)

        assert len(window.editor_controller.undo_stack) == 1
        cmd = window.editor_controller.undo_stack[0]
        assert cmd["type"] == "ApplyHd2dPreset"
        assert cmd["preset_id"] == "soft"

    def test_undo_entry_has_labeled_format(self) -> None:
        window = _StubWindow({"settings": {}})
        run_editor_action("editor.hd2d.preset.crisp.apply", window.editor_controller, window)

        cmd = window.editor_controller.undo_stack[0]
        # Label format: "Apply HD2D Preset · <Name>"
        assert cmd["label"] == "Apply HD2D Preset · Crisp"

    def test_each_preset_has_correct_label(self) -> None:
        for preset_id, name in [("soft", "Soft"), ("crisp", "Crisp"), ("noir", "Noir"), ("dreamy", "Dreamy")]:
            window = _StubWindow({"settings": {}})
            run_editor_action(f"editor.hd2d.preset.{preset_id}.apply", window.editor_controller, window)
            cmd = window.editor_controller.undo_stack[0]
            assert cmd["label"] == f"Apply HD2D Preset · {name}"

    def test_undo_entry_contains_before_and_after(self) -> None:
        window = _StubWindow({"settings": {"custom": "value", "depth_tint_enabled": False}})
        run_editor_action("editor.hd2d.preset.noir.apply", window.editor_controller, window)

        cmd = window.editor_controller.undo_stack[0]
        assert "before" in cmd
        assert "after" in cmd
        assert cmd["before"]["custom"] == "value"
        assert cmd["before"]["depth_tint_enabled"] is False
        assert cmd["after"]["depth_tint_enabled"] is True

    def test_no_op_does_not_push_undo_entry(self) -> None:
        """If preset application doesn't change anything, no undo entry."""
        # First apply the preset
        window = _StubWindow({"settings": {}})
        run_editor_action("editor.hd2d.preset.soft.apply", window.editor_controller, window)
        assert len(window.editor_controller.undo_stack) == 1

        # Apply same preset again - should not push another entry
        run_editor_action("editor.hd2d.preset.soft.apply", window.editor_controller, window)
        assert len(window.editor_controller.undo_stack) == 1

    def test_applying_preset_marks_dirty(self) -> None:
        window = _StubWindow({"settings": {}})
        run_editor_action("editor.hd2d.preset.dreamy.apply", window.editor_controller, window)
        assert window.editor_controller.dirty_calls == 1


class TestMenuIntegration:
    """Tests for menu integration."""

    def test_presets_in_view_menu_action_order(self) -> None:
        from engine.editor.menu_bar_model import MENU_ACTION_ORDER

        view_actions = MENU_ACTION_ORDER.get("View", ())
        assert "editor.hd2d.preset.soft.apply" in view_actions
        assert "editor.hd2d.preset.crisp.apply" in view_actions
        assert "editor.hd2d.preset.noir.apply" in view_actions
        assert "editor.hd2d.preset.dreamy.apply" in view_actions

    def test_presets_in_deterministic_order_in_menu(self) -> None:
        from engine.editor.menu_bar_model import MENU_ACTION_ORDER

        view_actions = list(MENU_ACTION_ORDER.get("View", ()))
        soft_idx = view_actions.index("editor.hd2d.preset.soft.apply")
        crisp_idx = view_actions.index("editor.hd2d.preset.crisp.apply")
        noir_idx = view_actions.index("editor.hd2d.preset.noir.apply")
        dreamy_idx = view_actions.index("editor.hd2d.preset.dreamy.apply")
        # Order must be: soft < crisp < noir < dreamy
        assert soft_idx < crisp_idx < noir_idx < dreamy_idx
