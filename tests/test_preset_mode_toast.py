import os
import unittest
from unittest.mock import MagicMock

from engine.ui import maybe_enqueue_preset_mode_toast


class TestPresetModeToast(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.player_hud = MagicMock()
        # Reset persistence
        if hasattr(self.mock_window, "_mesh_preset_mode_toasts_seen"):
            delattr(self.mock_window, "_mesh_preset_mode_toasts_seen")

    def tearDown(self):
        if "MESH_ACTIVE_PRESET" in os.environ:
            del os.environ["MESH_ACTIVE_PRESET"]
        if "MESH_PRESET_DESCRIPTION" in os.environ:
            del os.environ["MESH_PRESET_DESCRIPTION"]
        if "MESH_PRESET_NOTES" in os.environ:
            del os.environ["MESH_PRESET_NOTES"]

    def test_toast_fires_for_variant_b(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_b"
        os.environ["MESH_PRESET_NOTES"] = "Focus on ranged combat"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_b.json"

        result = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)

        self.assertTrue(result)
        self.mock_window.player_hud.enqueue_toast.assert_called_with(
            "Mode: Variant B (Focus on ranged combat)", seconds=4.0
        )

    def test_toast_fires_for_variant_c(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_c"
        os.environ["MESH_PRESET_NOTES"] = "Good luck!"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_c.json"

        result = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)

        self.assertTrue(result)
        self.mock_window.player_hud.enqueue_toast.assert_called_with(
            "Mode: Variant C (Good luck!)", seconds=4.0
        )

    def test_toast_fires_for_variant_d(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_d"
        os.environ["MESH_PRESET_NOTES"] = "Timer starts on input"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_d.json"

        result = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)

        self.assertTrue(result)
        self.mock_window.player_hud.enqueue_toast.assert_called_with(
            "Mode: Variant D (Timer starts on input)", seconds=4.0
        )

    def test_toast_does_not_fire_for_baseline(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_dungeon.json"

        result = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)

        self.assertFalse(result)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_toast_does_not_fire_for_non_dungeon_scene(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_b"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_hub.json"

        result = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)

        self.assertFalse(result)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_toast_is_idempotent_per_run(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_b"
        os.environ["MESH_PRESET_NOTES"] = "Notes"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_b.json"

        # First call
        result1 = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)
        self.assertTrue(result1)
        self.mock_window.player_hud.enqueue_toast.assert_called_once()
        self.mock_window.player_hud.enqueue_toast.reset_mock()

        # Second call (same scene)
        result2 = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)
        self.assertFalse(result2)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

        # Third call (different scene, e.g. re-entering dungeon?)
        # Wait, if I re-enter the dungeon, the scene_id is the same.
        # If I go to hub and back?
        # The key is f"{preset}:{sid}". So if sid is same, it won't fire.
        # This satisfies "Do NOT show repeatedly on re-entering the dungeon in the same run".

        # What if I load a DIFFERENT dungeon scene? (Unlikely in this game structure, but possible)
        scene_id_2 = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_b_part2.json"
        result3 = maybe_enqueue_preset_mode_toast(self.mock_window, scene_id_2)
        self.assertTrue(result3) # Should fire for a new dungeon scene if it matches the filter
        self.mock_window.player_hud.enqueue_toast.assert_called_once()

    def test_truncates_long_info(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_b"
        os.environ["MESH_PRESET_NOTES"] = "This is a very long note that should be truncated because it is too long"
        scene_id = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_b.json"

        maybe_enqueue_preset_mode_toast(self.mock_window, scene_id)

        args, _ = self.mock_window.player_hud.enqueue_toast.call_args
        msg = args[0]
        self.assertTrue(msg.startswith("Mode: Variant B (This is a very long note th...)"))
        self.assertLess(len(msg), 60) # "Mode: Variant B (" is ~17 chars + 30 chars info + ")"
