"""Contract tests for HD-2D preset preview model.

These tests verify:
- begin/apply/end restores exact original values
- Preview is deterministic
- Snapshot only contains touched keys
- Preview does not mark dirty or push undo
- Commit pushes ONE undo entry
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from engine.editor.hd2d_look_presets_model import get_hd2d_preset_patch
from engine.editor.hd2d_preset_preview_model import (
    HD2D_PRESET_KEYS,
    PreviewSnapshot,
    begin_preset_preview,
    end_preset_preview,
    extract_preset_id_from_command,
    is_hd2d_preset_command,
    update_preset_preview,
)


class TestPreviewSnapshotKeys:
    """Tests for HD2D_PRESET_KEYS completeness."""

    def test_preset_keys_matches_actual_patch_keys(self) -> None:
        """HD2D_PRESET_KEYS must include all keys from actual presets."""
        for preset_id in ["soft", "crisp", "noir", "dreamy"]:
            patch = get_hd2d_preset_patch(preset_id)
            assert patch is not None
            for key in patch:
                assert key in HD2D_PRESET_KEYS, f"Missing key {key} for preset {preset_id}"

    def test_preset_keys_is_frozen(self) -> None:
        """Keys set should be immutable."""
        assert isinstance(HD2D_PRESET_KEYS, frozenset)


class TestBeginPresetPreview:
    """Tests for begin_preset_preview function."""

    def test_begin_returns_tuple_of_payload_and_snapshot(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        result = begin_preset_preview(scene, "soft")
        assert isinstance(result, tuple)
        assert len(result) == 2
        payload, snapshot = result
        assert isinstance(payload, dict)
        assert isinstance(snapshot, PreviewSnapshot)

    def test_begin_does_not_mutate_original(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        original = copy.deepcopy(scene)
        _ = begin_preset_preview(scene, "soft")
        assert scene == original

    def test_begin_applies_preset_to_payload(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        payload, _ = begin_preset_preview(scene, "soft")
        assert payload["settings"]["depth_tint_enabled"] is True

    def test_begin_snapshot_contains_original_values(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False, "depth_tint_strength": 0.5}}
        _, snapshot = begin_preset_preview(scene, "soft")
        assert snapshot.original_settings["depth_tint_enabled"] is False
        assert snapshot.original_settings["depth_tint_strength"] == 0.5

    def test_begin_snapshot_only_contains_touched_keys(self) -> None:
        """Snapshot should only include keys that exist in scene settings."""
        scene = {"settings": {"depth_tint_enabled": False, "unrelated_key": "preserved"}}
        _, snapshot = begin_preset_preview(scene, "soft")
        assert "depth_tint_enabled" in snapshot.original_settings
        assert "unrelated_key" not in snapshot.original_settings

    def test_begin_unknown_preset_returns_unchanged_copy(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        payload, snapshot = begin_preset_preview(scene, "unknown_preset")
        assert payload["settings"]["depth_tint_enabled"] is False
        assert snapshot.original_settings == {}

    def test_begin_creates_settings_if_missing(self) -> None:
        scene: dict[str, Any] = {}
        payload, _ = begin_preset_preview(scene, "soft")
        assert "settings" in payload
        assert payload["settings"]["depth_tint_enabled"] is True

    def test_begin_preserves_unrelated_settings(self) -> None:
        scene = {"settings": {"custom_key": "preserved", "depth_tint_enabled": False}}
        payload, _ = begin_preset_preview(scene, "soft")
        assert payload["settings"]["custom_key"] == "preserved"


class TestUpdatePresetPreview:
    """Tests for update_preset_preview function."""

    def test_update_applies_new_preset(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        _, snapshot = begin_preset_preview(scene, "soft")

        # Get soft preset values
        soft_patch = get_hd2d_preset_patch("soft")
        assert soft_patch is not None
        previewed = {"settings": dict(soft_patch)}

        # Update to crisp
        updated = update_preset_preview(previewed, "crisp", snapshot)
        crisp_patch = get_hd2d_preset_patch("crisp")
        assert crisp_patch is not None
        assert updated["settings"]["depth_tint_strength"] == crisp_patch["depth_tint_strength"]

    def test_update_does_not_mutate_original(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        payload, snapshot = begin_preset_preview(scene, "soft")
        original_payload = copy.deepcopy(payload)
        _ = update_preset_preview(payload, "crisp", snapshot)
        assert payload == original_payload


class TestEndPresetPreview:
    """Tests for end_preset_preview function."""

    def test_end_restores_original_values(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False, "depth_tint_strength": 0.5}}
        original_settings = copy.deepcopy(scene["settings"])

        payload, snapshot = begin_preset_preview(scene, "soft")
        assert payload["settings"]["depth_tint_enabled"] is True

        restored = end_preset_preview(payload, snapshot)
        assert restored["settings"]["depth_tint_enabled"] is False
        assert restored["settings"]["depth_tint_strength"] == 0.5

    def test_end_removes_keys_not_in_original(self) -> None:
        """Keys added by preset that weren't in original should be removed."""
        scene: dict[str, Any] = {"settings": {}}
        payload, snapshot = begin_preset_preview(scene, "soft")

        # Soft preset added depth_tint_enabled
        assert payload["settings"]["depth_tint_enabled"] is True

        restored = end_preset_preview(payload, snapshot)
        # Should not have depth_tint_enabled since original didn't
        assert "depth_tint_enabled" not in restored["settings"]

    def test_end_does_not_mutate_input(self) -> None:
        scene = {"settings": {"depth_tint_enabled": False}}
        payload, snapshot = begin_preset_preview(scene, "soft")
        payload_copy = copy.deepcopy(payload)
        _ = end_preset_preview(payload, snapshot)
        assert payload == payload_copy

    def test_end_preserves_unrelated_keys(self) -> None:
        scene = {"settings": {"custom": "value", "depth_tint_enabled": False}}
        payload, snapshot = begin_preset_preview(scene, "soft")
        restored = end_preset_preview(payload, snapshot)
        assert restored["settings"]["custom"] == "value"


class TestPreviewRoundTrip:
    """Tests for complete preview lifecycle."""

    def test_begin_then_end_restores_exact_original(self) -> None:
        """Full round-trip must restore exact original state."""
        scene = {
            "settings": {
                "depth_tint_enabled": False,
                "depth_tint_strength": 0.33,
                "depth_tint_near_color": [100, 100, 100, 255],
                "custom_setting": "untouched",
            },
            "entities": [{"id": "e1"}],
        }
        original = copy.deepcopy(scene)

        payload, snapshot = begin_preset_preview(scene, "noir")
        assert payload["settings"]["depth_tint_enabled"] is True

        restored = end_preset_preview(payload, snapshot)
        assert restored["settings"] == original["settings"]
        assert restored["entities"] == original["entities"]

    def test_preview_is_deterministic(self) -> None:
        """Same input produces same output."""
        scene = {"settings": {"depth_tint_enabled": False}}

        payload1, snapshot1 = begin_preset_preview(scene, "soft")
        payload2, snapshot2 = begin_preset_preview(scene, "soft")

        assert payload1 == payload2
        assert snapshot1.original_settings == snapshot2.original_settings

    def test_multiple_update_cycles_restore_correctly(self) -> None:
        """Preview can be updated multiple times and still restore correctly."""
        scene = {"settings": {"depth_tint_enabled": False, "depth_tint_strength": 0.1}}
        original_settings = copy.deepcopy(scene["settings"])

        payload, snapshot = begin_preset_preview(scene, "soft")
        payload = update_preset_preview(payload, "crisp", snapshot)
        payload = update_preset_preview(payload, "noir", snapshot)
        payload = update_preset_preview(payload, "dreamy", snapshot)

        restored = end_preset_preview(payload, snapshot)
        assert restored["settings"]["depth_tint_enabled"] == original_settings["depth_tint_enabled"]
        assert restored["settings"]["depth_tint_strength"] == original_settings["depth_tint_strength"]


class TestCommandIdHelpers:
    """Tests for HD2D command ID helpers."""

    def test_is_hd2d_preset_command_true_cases(self) -> None:
        assert is_hd2d_preset_command("editor.hd2d.preset.soft.apply") is True
        assert is_hd2d_preset_command("editor.hd2d.preset.crisp.apply") is True
        assert is_hd2d_preset_command("editor.hd2d.preset.noir.apply") is True
        assert is_hd2d_preset_command("editor.hd2d.preset.dreamy.apply") is True

    def test_is_hd2d_preset_command_false_cases(self) -> None:
        assert is_hd2d_preset_command("editor.light_tool.toggle") is False
        assert is_hd2d_preset_command("editor.hd2d.preset.soft") is False  # Missing .apply
        assert is_hd2d_preset_command("") is False
        assert is_hd2d_preset_command("editor.hd2d.preset") is False

    def test_extract_preset_id_from_command(self) -> None:
        assert extract_preset_id_from_command("editor.hd2d.preset.soft.apply") == "soft"
        assert extract_preset_id_from_command("editor.hd2d.preset.crisp.apply") == "crisp"
        assert extract_preset_id_from_command("editor.hd2d.preset.noir.apply") == "noir"
        assert extract_preset_id_from_command("editor.hd2d.preset.dreamy.apply") == "dreamy"

    def test_extract_preset_id_returns_none_for_invalid(self) -> None:
        assert extract_preset_id_from_command("editor.light_tool.toggle") is None
        assert extract_preset_id_from_command("") is None
        assert extract_preset_id_from_command("editor.hd2d.preset.soft") is None


# -----------------------------------------------------------------------------
# Integration tests for editor controller preview behavior
# -----------------------------------------------------------------------------


class _StubSceneController:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._loaded_scene_data = payload


class _StubEditor:
    """Minimal editor stub for testing preview behavior."""

    def __init__(self, scene_payload: dict[str, Any]) -> None:
        self.active = True
        self.window = SimpleNamespace(
            scene_controller=_StubSceneController(scene_payload),
        )
        self.scene_dirty = False
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []

        # HD2D preview state
        self._hd2d_preview_active = False
        self._hd2d_preview_snapshot: Any = None
        self._hd2d_preview_preset_id: str | None = None

        # Find everything state (minimal)
        self._find_everything_open = False
        self._find_everything_selection_index = 0
        self._find_everything_cached_results: list[Any] = []

    def _mark_dirty(self) -> None:
        self.scene_dirty = True

    def _push_command(self, cmd: dict[str, Any]) -> None:
        self.undo_stack.append(cmd)
        self.redo_stack.clear()


def _create_test_editor(scene_payload: dict[str, Any]) -> _StubEditor:
    """Create a minimal test editor with HD2D preview methods injected."""
    editor = _StubEditor(scene_payload)

    # Inject the preview methods from the real implementation
    from engine.editor.hd2d_preset_preview_model import (
        begin_preset_preview,
        end_preset_preview,
        update_preset_preview,
    )

    def preview_hd2d_preset(preset_id: str) -> bool:
        sc = editor.window.scene_controller
        scene = sc._loaded_scene_data
        if not isinstance(scene, dict):
            return False

        if editor._hd2d_preview_active and editor._hd2d_preview_snapshot is not None:
            if editor._hd2d_preview_preset_id == preset_id:
                return True
            new_scene = update_preset_preview(scene, preset_id, editor._hd2d_preview_snapshot)
        else:
            new_scene, snapshot = begin_preset_preview(scene, preset_id)
            editor._hd2d_preview_snapshot = snapshot
            editor._hd2d_preview_active = True

        editor._hd2d_preview_preset_id = preset_id
        sc._loaded_scene_data = new_scene
        return True

    def _cancel_hd2d_preview() -> None:
        if not editor._hd2d_preview_active or editor._hd2d_preview_snapshot is None:
            editor._hd2d_preview_active = False
            editor._hd2d_preview_snapshot = None
            editor._hd2d_preview_preset_id = None
            return

        sc = editor.window.scene_controller
        scene = sc._loaded_scene_data
        if isinstance(scene, dict):
            restored = end_preset_preview(scene, editor._hd2d_preview_snapshot)
            sc._loaded_scene_data = restored

        editor._hd2d_preview_active = False
        editor._hd2d_preview_snapshot = None
        editor._hd2d_preview_preset_id = None

    def commit_hd2d_preset(preset_id: str) -> bool:
        _cancel_hd2d_preview()

        from engine.editor.hd2d_look_presets_model import apply_hd2d_preset, get_hd2d_preset_name

        sc = editor.window.scene_controller
        scene = sc._loaded_scene_data
        if not isinstance(scene, dict):
            return False

        preset_name = get_hd2d_preset_name(preset_id)
        if preset_name is None:
            return False

        before_settings = copy.deepcopy(scene.get("settings", {}))
        new_scene = apply_hd2d_preset(scene, preset_id)
        after_settings = new_scene.get("settings", {})

        if before_settings == after_settings:
            return False

        sc._loaded_scene_data = new_scene
        editor._mark_dirty()
        editor._push_command({
            "type": "ApplyHd2dPreset",
            "label": f"Apply HD2D Preset · {preset_name}",
            "preset_id": preset_id,
            "before": before_settings,
            "after": after_settings,
        })
        return True

    editor.preview_hd2d_preset = preview_hd2d_preset
    editor._cancel_hd2d_preview = _cancel_hd2d_preview
    editor.commit_hd2d_preset = commit_hd2d_preset

    return editor


class TestPreviewDoesNotMarkDirty:
    """Tests that preview operations don't mark scene as dirty."""

    def test_preview_does_not_mark_dirty(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        assert editor.scene_dirty is False

        editor.preview_hd2d_preset("soft")
        assert editor.scene_dirty is False

    def test_preview_update_does_not_mark_dirty(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.preview_hd2d_preset("soft")
        editor.preview_hd2d_preset("crisp")
        assert editor.scene_dirty is False

    def test_preview_cancel_does_not_mark_dirty(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.preview_hd2d_preset("soft")
        editor._cancel_hd2d_preview()
        assert editor.scene_dirty is False


class TestPreviewDoesNotPushUndo:
    """Tests that preview operations don't push undo entries."""

    def test_preview_does_not_push_undo(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        assert len(editor.undo_stack) == 0

        editor.preview_hd2d_preset("soft")
        assert len(editor.undo_stack) == 0

    def test_preview_update_does_not_push_undo(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.preview_hd2d_preset("soft")
        editor.preview_hd2d_preset("crisp")
        editor.preview_hd2d_preset("noir")
        assert len(editor.undo_stack) == 0

    def test_preview_cancel_does_not_push_undo(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.preview_hd2d_preset("soft")
        editor._cancel_hd2d_preview()
        assert len(editor.undo_stack) == 0


class TestCommitPushesOneUndoEntry:
    """Tests that commit pushes exactly one undo entry."""

    def test_commit_pushes_one_undo_entry(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        assert len(editor.undo_stack) == 0

        editor.commit_hd2d_preset("soft")
        assert len(editor.undo_stack) == 1

    def test_commit_after_preview_pushes_one_undo_entry(self) -> None:
        """Preview followed by commit should push exactly ONE entry."""
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.preview_hd2d_preset("soft")
        editor.preview_hd2d_preset("crisp")  # Update preview
        assert len(editor.undo_stack) == 0

        editor.commit_hd2d_preset("crisp")
        assert len(editor.undo_stack) == 1
        assert editor.undo_stack[0]["preset_id"] == "crisp"

    def test_commit_marks_dirty(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        assert editor.scene_dirty is False

        editor.commit_hd2d_preset("soft")
        assert editor.scene_dirty is True

    def test_commit_undo_entry_has_correct_label(self) -> None:
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.commit_hd2d_preset("noir")

        cmd = editor.undo_stack[0]
        assert cmd["label"] == "Apply HD2D Preset · Noir"
        assert cmd["type"] == "ApplyHd2dPreset"


class TestPreviewStateTransitions:
    """Tests for preview state lifecycle."""

    def test_initial_state_is_not_active(self) -> None:
        editor = _create_test_editor({"settings": {}})
        assert editor._hd2d_preview_active is False
        assert editor._hd2d_preview_snapshot is None
        assert editor._hd2d_preview_preset_id is None

    def test_preview_activates_state(self) -> None:
        editor = _create_test_editor({"settings": {}})
        editor.preview_hd2d_preset("soft")
        assert editor._hd2d_preview_active is True
        assert editor._hd2d_preview_snapshot is not None
        assert editor._hd2d_preview_preset_id == "soft"

    def test_cancel_clears_state(self) -> None:
        editor = _create_test_editor({"settings": {}})
        editor.preview_hd2d_preset("soft")
        editor._cancel_hd2d_preview()
        assert editor._hd2d_preview_active is False
        assert editor._hd2d_preview_snapshot is None
        assert editor._hd2d_preview_preset_id is None

    def test_commit_clears_preview_state(self) -> None:
        editor = _create_test_editor({"settings": {}})
        editor.preview_hd2d_preset("soft")
        editor.commit_hd2d_preset("soft")
        assert editor._hd2d_preview_active is False
        assert editor._hd2d_preview_snapshot is None
        assert editor._hd2d_preview_preset_id is None

    def test_update_preserves_snapshot(self) -> None:
        """Update should keep original snapshot, only change preset_id."""
        editor = _create_test_editor({"settings": {"depth_tint_enabled": False}})
        editor.preview_hd2d_preset("soft")
        original_snapshot = editor._hd2d_preview_snapshot

        editor.preview_hd2d_preset("crisp")
        assert editor._hd2d_preview_snapshot is original_snapshot
        assert editor._hd2d_preview_preset_id == "crisp"


class TestPreviewCancelRestoresOriginal:
    """Tests that canceling preview restores exact original state."""

    def test_cancel_restores_original_settings(self) -> None:
        original_settings = {"depth_tint_enabled": False, "depth_tint_strength": 0.33}
        editor = _create_test_editor({"settings": copy.deepcopy(original_settings)})

        editor.preview_hd2d_preset("soft")
        # Verify preview changed something
        scene = editor.window.scene_controller._loaded_scene_data
        assert scene["settings"]["depth_tint_enabled"] is True

        editor._cancel_hd2d_preview()
        scene = editor.window.scene_controller._loaded_scene_data
        assert scene["settings"]["depth_tint_enabled"] is False
        assert scene["settings"]["depth_tint_strength"] == 0.33

    def test_cancel_after_multiple_updates_restores_original(self) -> None:
        original_settings = {"depth_tint_enabled": False}
        editor = _create_test_editor({"settings": copy.deepcopy(original_settings)})

        editor.preview_hd2d_preset("soft")
        editor.preview_hd2d_preset("crisp")
        editor.preview_hd2d_preset("noir")
        editor.preview_hd2d_preset("dreamy")

        editor._cancel_hd2d_preview()
        scene = editor.window.scene_controller._loaded_scene_data
        assert scene["settings"]["depth_tint_enabled"] is False
