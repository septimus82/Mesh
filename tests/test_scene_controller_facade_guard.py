import ast
import pathlib
import unittest
from unittest.mock import MagicMock, patch

import pytest

import engine.scene_controller as scene_controller_module
from engine.scene_controller import SceneController


pytestmark = [pytest.mark.integration, pytest.mark.slow]

class TestSceneControllerFacadeGuard(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        # Mock prefab manager to avoid loading assets during test
        with patch("engine.scene_controller.get_prefab_manager") as mock_pm:
            self.controller = SceneController(self.mock_window)

    def test_reload_scene_delegates_to_runtime(self):
        with patch("engine.scene_controller._reload_scene_runtime") as mock_reload:
            self.controller.reload_scene("new_path")
            mock_reload.assert_called_once_with(self.controller, new_path="new_path")

    def test_perform_scene_change_delegates_to_runtime(self):
        with patch("engine.scene_controller._perform_scene_change_runtime") as mock_perform:
            self.controller._perform_scene_change("path", "spawn")
            mock_perform.assert_called_once_with(self.controller, "path", spawn_id="spawn")

    def test_build_scene_snapshot_delegates_to_runtime(self):
        with patch("engine.scene_controller._build_scene_snapshot_runtime") as mock_build:
            self.controller.build_scene_snapshot(compact=True)
            mock_build.assert_called_once_with(self.controller, compact=True)

    def test_apply_scene_state_delegates_to_runtime(self):
        with patch("engine.scene_controller._apply_scene_state_runtime") as mock_apply:
            state = {"foo": "bar"}
            self.controller._apply_scene_state(state)
            mock_apply.assert_called_once_with(self.controller, state)

    def test_snapshot_player_state_delegates_to_runtime(self):
        with patch("engine.scene_controller._snapshot_player_state_runtime") as mock_snap:
            self.controller._snapshot_player_state()
            mock_snap.assert_called_once_with(self.controller)

    def test_restore_player_state_delegates_to_runtime(self):
        with patch("engine.scene_controller._restore_player_state_runtime") as mock_restore:
            snap = {"pos": (0, 0)}
            self.controller._restore_player_state(snap)
            mock_restore.assert_called_once_with(self.controller, snap)

    def test_snapshot_camera_state_delegates_to_runtime(self):
        with patch("engine.scene_controller._snapshot_camera_state_runtime") as mock_snap:
            self.controller._snapshot_camera_state()
            mock_snap.assert_called_once_with(self.controller)

    def test_restore_camera_state_delegates_to_runtime(self):
        with patch("engine.scene_controller._restore_camera_state_runtime") as mock_restore:
            snap = {"zoom": 1.0}
            self.controller._restore_camera_state(snap)
            mock_restore.assert_called_once_with(self.controller, snap)

    def test_authoring_methods_are_thin_delegates(self):
        authoring_part_methods = {
            "_call_authoring",
            "enable_authoring_trace",
            "reset_authoring_trace",
            "get_authoring_trace_snapshot",
            "refresh_tilemap_layers",
            "debug_find_sprite_by_entity_id",
            "_debug_iter_authoring_payloads",
            "_debug_remove_sprite",
            "debug_add_entity_payload",
            "debug_remove_entity_by_id",
            "debug_move_entity_by_id",
            "debug_duplicate_entities_by_ids",
            "debug_copy_entities_by_ids",
            "debug_paste_entities_from_clipboard",
            "debug_transform_entities_by_ids",
            "debug_set_prefab_id",
            "debug_add_behaviour",
            "debug_remove_behaviour",
            "debug_set_name",
            "debug_add_tag",
            "debug_remove_tag",
            "debug_toggle_tag",
            "debug_batch_rename",
            "debug_set_names",
            "debug_config_triggerzone_set_zone_id",
            "debug_config_triggerzone_set_radius",
            "_debug_config_entity_has_behaviour",
            "_debug_config_mutate_for_behaviour",
            "_debug_config_set_field_for_behaviour",
            "debug_build_macro_objective_zone_payload",
            "debug_build_macro_door_transition_payload",
            "debug_build_macro_dialogue_choice_flag_payload",
            "_debug_preview_diff",
            "debug_preview_macro_objective_zone",
            "debug_preview_macro_door_transition",
            "debug_preview_macro_dialogue_choice_flag",
        }
        quests_flags_methods = {
            "debug_config_set_game_state_set_toast",
            "debug_config_set_game_state_add_require_flag",
            "debug_config_set_game_state_add_forbid_flag",
            "debug_config_set_game_state_set_flag_true",
            "debug_config_scene_transition_set_target_scene",
            "debug_config_scene_transition_set_spawn_id",
        }
        selection_methods = {
            "debug_align_selection",
            "debug_distribute_selection",
            "debug_snap_to_grid",
            "debug_nudge_selection",
            "debug_rotate_selection",
            "debug_mirror_selection",
            "debug_group_selection",
            "debug_ungroup_selection",
            "debug_duplicate_to_grid",
            "debug_duplicate_along_path",
            "debug_scatter_selection",
        }

        for name in sorted(authoring_part_methods):
            method = getattr(SceneController, name, None)
            self.assertTrue(callable(method), msg=f"{name} missing or not callable")
            self.assertEqual(method.__module__, "engine.scene_controller_parts.authoring")

        for name in sorted(quests_flags_methods):
            method = getattr(SceneController, name, None)
            self.assertTrue(callable(method), msg=f"{name} missing or not callable")
            self.assertEqual(method.__module__, "engine.scene_controller_parts.quests_flags")

        for name in sorted(selection_methods):
            method = getattr(SceneController, name, None)
            self.assertTrue(callable(method), msg=f"{name} missing or not callable")
            self.assertEqual(method.__module__, "engine.scene_controller_selection")

        self.assertEqual(SceneController.get_authored_scene_payload.__module__, "engine.scene_controller_core")
        self.assertEqual(SceneController.debug_apply_authored_scene_payload.__module__, "engine.scene_controller_core")
