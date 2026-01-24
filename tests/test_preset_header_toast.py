import argparse
import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

from engine.game import GameWindow
from engine.tooling import preset_commands


pytestmark = [pytest.mark.builtin_behaviours, pytest.mark.integration, pytest.mark.slow]

class TestPresetHeaderToast(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock()
        self.mock_config.presets = {}
        self.patcher_config = patch("engine.tooling.preset_commands.load_config", return_value=self.mock_config)
        self.patcher_config.start()
        
        self.patcher_cli = patch("mesh_cli.main", return_value=0)
        self.mock_cli_main = self.patcher_cli.start()

    def tearDown(self):
        self.patcher_config.stop()
        self.patcher_cli.stop()
        if "MESH_ACTIVE_PRESET" in os.environ:
            del os.environ["MESH_ACTIVE_PRESET"]
        if "MESH_PRESET_DESCRIPTION" in os.environ:
            del os.environ["MESH_PRESET_DESCRIPTION"]
        if "MESH_PRESET_NOTES" in os.environ:
            del os.environ["MESH_PRESET_NOTES"]

    def test_run_preset_sets_env_vars(self):
        self.mock_config.presets = {
            "test_preset": {
                "description": "Test Description",
                "notes": "Test Notes",
                "steps": [{"cmd": "pipeline"}]
            }
        }
        
        def check_env(*args, **kwargs):
            self.assertEqual(os.environ.get("MESH_ACTIVE_PRESET"), "test_preset")
            self.assertEqual(os.environ.get("MESH_PRESET_DESCRIPTION"), "Test Description")
            self.assertEqual(os.environ.get("MESH_PRESET_NOTES"), "Test Notes")
            return 0
            
        self.mock_cli_main.side_effect = check_env
        
        args = argparse.Namespace(name="test_preset")
        preset_commands.run_preset_command(args)
        
        self.mock_cli_main.assert_called()
        
        # Verify env vars are cleaned up
        self.assertIsNone(os.environ.get("MESH_ACTIVE_PRESET"))
        self.assertIsNone(os.environ.get("MESH_PRESET_DESCRIPTION"))
        self.assertIsNone(os.environ.get("MESH_PRESET_NOTES"))

    def test_run_preset_sets_env_vars_no_description(self):
        self.mock_config.presets = {
            "test_preset_no_desc": {
                "description": "Test Description",
                "steps": [{"cmd": "pipeline"}]
            }
        }
        
        def check_env(*args, **kwargs):
            self.assertEqual(os.environ.get("MESH_ACTIVE_PRESET"), "test_preset_no_desc")
            self.assertEqual(os.environ.get("MESH_PRESET_DESCRIPTION"), "Test Description")
            self.assertIsNone(os.environ.get("MESH_PRESET_NOTES"))
            return 0
            
        self.mock_cli_main.side_effect = check_env
        
        args = argparse.Namespace(name="test_preset_no_desc")
        preset_commands.run_preset_command(args)
        
        self.mock_cli_main.assert_called()
        
        self.assertIsNone(os.environ.get("MESH_ACTIVE_PRESET"))

class TestGameWindowToast(unittest.TestCase):
    def setUp(self):
        # We need to mock a LOT of things to instantiate GameWindow without side effects
        self.patchers = []

        def _stub_window_init(self, width, height, title, fullscreen=False, vsync=True, **_kwargs):
            self._width = width
            self._height = height
            self._scale = 1.0

        patcher = patch("engine.optional_arcade.arcade.Window.__init__", new=_stub_window_init)
        patcher.start()
        self.patchers.append(patcher)
        patcher = patch("engine.optional_arcade.arcade.set_background_color", MagicMock())
        patcher.start()
        self.patchers.append(patcher)
        patcher = patch("engine.optional_arcade.arcade.Text", MagicMock())
        patcher.start()
        self.patchers.append(patcher)

        # Mock all the managers/controllers
        managers = [
            "WorldController", "SceneLoader", "AssetManager", "AnimationFactory",
            "TilemapManager", "AudioManager", "ConsoleController", "CameraController",
            "SceneController", "InputController", "UIController", "EditorModeController",
            "AIDebugOverlay", "CutsceneController", "LightManager", "DayNightCycle",
            "PlayerHUD", "GameOverScreen", "PauseMenu", "HelpOverlay", "InspectorOverlay",
            "GoldenSliceVariantPickerOverlay", "GoldenSliceDemoHUDStripOverlay",
            "DevBrowserOverlay", "EncounterDebugOverlay", "SceneDirtyOverlay",
            "HotReloadOverlay", "EntitySelectOverlay", "SceneInspectorOverlay",
            "TilePaintOverlay", "EntityPaintOverlay", "CaptureOverlay",
            "CommandPaletteOverlay", "InteractPromptOverlay", "ObjectiveTrackerOverlay",
            "DemoCompleteOverlay", "MainMenuOverlay", "SettingsOverlay",
            "GameStateController", "SaveManager", "QuestManager", "ParticleManager",
            "MeshEventBus"
        ]
        
        self.mocks = {}
        for mgr in managers:
            patcher = patch(f"engine.game.{mgr}")
            mock_cls = patcher.start()
            self.mocks[mgr] = mock_cls
            self.patchers.append(patcher)

        patcher = patch("engine.ui_overlays.perf.PerfOverlay")
        patcher.start()
        self.patchers.append(patcher)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        if "MESH_ACTIVE_PRESET" in os.environ:
            del os.environ["MESH_ACTIVE_PRESET"]
        if "MESH_PRESET_DESCRIPTION" in os.environ:
            del os.environ["MESH_PRESET_DESCRIPTION"]
        if "MESH_PRESET_NOTES" in os.environ:
            del os.environ["MESH_PRESET_NOTES"]

    def test_game_window_enqueues_toast_with_preset(self):
        os.environ["MESH_ACTIVE_PRESET"] = "test_preset"
        os.environ["MESH_PRESET_DESCRIPTION"] = "Test Description"
        os.environ["MESH_PRESET_NOTES"] = "Test Notes"
        
        window = GameWindow(800, 600, "Test")
        
        # Verify PlayerHUD.enqueue_toast was called
        mock_hud_instance = self.mocks["PlayerHUD"].return_value
        mock_hud_instance.enqueue_toast.assert_called_with("Preset: test_preset — Test Description (Notes: Test Notes)")

    def test_game_window_enqueues_toast_without_description(self):
        os.environ["MESH_ACTIVE_PRESET"] = "test_preset_simple"
        if "MESH_PRESET_DESCRIPTION" in os.environ:
            del os.environ["MESH_PRESET_DESCRIPTION"]
        if "MESH_PRESET_NOTES" in os.environ:
            del os.environ["MESH_PRESET_NOTES"]
            
        window = GameWindow(800, 600, "Test")
        
        mock_hud_instance = self.mocks["PlayerHUD"].return_value
        mock_hud_instance.enqueue_toast.assert_called_with("Preset: test_preset_simple")

    def test_game_window_no_toast_without_preset(self):
        if "MESH_ACTIVE_PRESET" in os.environ:
            del os.environ["MESH_ACTIVE_PRESET"]
            
        window = GameWindow(800, 600, "Test")
        
        mock_hud_instance = self.mocks["PlayerHUD"].return_value
        mock_hud_instance.enqueue_toast.assert_not_called()
