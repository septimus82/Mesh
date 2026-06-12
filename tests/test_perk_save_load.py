import unittest

from engine.game_state_controller import GameState


class TestPerkSaveLoad(unittest.TestCase):
    def test_save_load_perks(self):
        state = GameState()
        state.perks = ["p1", "p2"]

        snapshot = state.snapshot()
        self.assertIn("perks", snapshot)
        self.assertEqual(snapshot["perks"], ["p1", "p2"])

        new_state = GameState()
        new_state.restore(snapshot)
        self.assertEqual(new_state.perks, ["p1", "p2"])

if __name__ == "__main__":
    unittest.main()
