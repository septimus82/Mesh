import unittest
from unittest.mock import MagicMock, patch

import pytest

from engine.scene_controller import SceneController


pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestSceneAuthoringDelegation(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        with patch("engine.scene_controller.get_prefab_manager"):
            self.controller = SceneController(self.mock_window)

    def test_debug_build_macro_methods_delegate(self):
        with patch("engine.scene_controller._authoring_runtime.debug_build_macro_objective_zone_payload") as obj:
            obj.return_value = ({"entities": []}, 0, 0)
            self.controller.debug_build_macro_objective_zone_payload(
                center_x=1.0,
                center_y=2.0,
                zone_id="z",
                set_flag="f",
                radius=3.0,
                toast=None,
            )
            obj.assert_called_once()

        with patch("engine.scene_controller._authoring_runtime.debug_build_macro_door_transition_payload") as door:
            door.return_value = ({"entities": []}, 0, 0)
            self.controller.debug_build_macro_door_transition_payload(
                center_x=1.0,
                center_y=2.0,
                target_scene="scenes/x.json",
                spawn_id="spawn",
                primary_id=None,
            )
            door.assert_called_once()

        with patch("engine.scene_controller._authoring_runtime.debug_build_macro_dialogue_choice_flag_payload") as dlg:
            dlg.return_value = ({"entities": []}, 0, 0)
            self.controller.debug_build_macro_dialogue_choice_flag_payload(
                speaker_id="speaker",
                choice_id="choice",
                choice_text="text",
                set_flag="flag",
                toast=None,
            )
            dlg.assert_called_once()
