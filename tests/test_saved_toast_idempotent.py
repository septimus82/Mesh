"""Saving says so: every successful save confirms, a failed one says why and never claims success.

(Until Milestone 11 a repeated save of unchanged content said nothing, which left a player pressing Save
again unsure it had worked; the file name is kept from that earlier policy.)
"""

import unittest
from unittest.mock import MagicMock, patch

from engine.save_manager import SaveManager


class TestSavedToast(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.scene_controller = MagicMock()
        # Use side_effect to return a fresh dict each time, otherwise 'meta' from previous save persists in the mock's return_value
        self.mock_window.scene_controller.build_scene_snapshot.side_effect = lambda compact=False: {"entities": []}
        self.mock_window.scene_controller.current_scene_path = "scenes/test.json"
        self.mock_window.game_state_controller = MagicMock()
        self.mock_window.game_state_controller.export_state.return_value = {"gold": 100}
        self.mock_window.player_hud = MagicMock()

        self.save_manager = SaveManager(self.mock_window, save_dir="tests/temp_saves_saved_idempotent")
        if not self.save_manager.save_dir.exists():
            self.save_manager.save_dir.mkdir(parents=True)

    def tearDown(self):
        if self.save_manager.save_dir.exists():
            for f in self.save_manager.save_dir.glob("*"):
                f.unlink()
            self.save_manager.save_dir.rmdir()

    def test_every_save_is_confirmed(self):
        for slot in ("test_slot", "test_slot", "other_slot"):  # the same unchanged save twice, then another slot
            self.mock_window.player_hud.enqueue_toast.reset_mock()
            self.assertTrue(self.save_manager.save_game(slot))
            self.mock_window.player_hud.enqueue_toast.assert_called_once_with("Game saved")

    def test_a_failed_save_says_why_and_not_that_it_saved(self):
        with patch("pathlib.Path.open", side_effect=PermissionError("Mock error")):
            result = self.save_manager.save_game("slot_fail")
        self.assertFalse(result)
        toasts = [c.args[0] for c in self.mock_window.player_hud.enqueue_toast.call_args_list]
        self.assertEqual(len(toasts), 1)
        self.assertTrue(toasts[0].startswith("Couldn't save the game:"), toasts)


def test_toasts_show_for_a_player_without_health_stats():
    """Milestone 11: the HUD drew toasts after the health bar and gave up first when the player had no HP
    (every Studio game), so "Game saved" was never seen."""
    from types import SimpleNamespace

    from engine.ui import PlayerHUD

    hud = PlayerHUD.__new__(PlayerHUD)
    hud.window = SimpleNamespace(editor_controller=None, player=None)
    hud._draw_toasts = MagicMock()
    hud.draw()
    hud._draw_toasts.assert_called_once()


def test_a_studio_play_test_gets_no_engine_controls_hint():
    """Now that toasts draw in Studio games, the old runtime's "F2: Editor  I: Inspector" banner must not."""
    from types import SimpleNamespace

    from engine.ui import PlayerHUD

    window = SimpleNamespace(studio=object(), engine_config=SimpleNamespace(start_scene="scenes/a.json"))
    assert PlayerHUD.maybe_show_controls_hint(window, scene_id="scenes/a.json") is None
    assert PlayerHUD.maybe_show_controls_hint(SimpleNamespace(engine_config=window.engine_config), scene_id="scenes/a.json")
