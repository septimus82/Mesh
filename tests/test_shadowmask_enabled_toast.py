import os
import unittest
from unittest.mock import MagicMock

from engine.ui import maybe_enqueue_shadowmask_enabled_toast


class TestShadowmaskEnabledToast(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.player_hud = MagicMock()
        # Reset persistence
        if hasattr(self.mock_window, "_mesh_shadowmask_toast_seen"):
            delattr(self.mock_window, "_mesh_shadowmask_toast_seen")

    def tearDown(self):
        if "MESH_SHADOWCAST_MASK" in os.environ:
            del os.environ["MESH_SHADOWCAST_MASK"]

    def test_toast_fires_when_enabled(self):
        os.environ["MESH_SHADOWCAST_MASK"] = "1"

        result = maybe_enqueue_shadowmask_enabled_toast(self.mock_window)

        self.assertTrue(result)
        self.mock_window.player_hud.enqueue_toast.assert_called_with(
            "Lighting: Shadow mask enabled", seconds=4.0
        )

        # Verify persistence
        self.assertTrue(getattr(self.mock_window, "_mesh_shadowmask_toast_seen"))

    def test_toast_does_not_fire_when_disabled(self):
        if "MESH_SHADOWCAST_MASK" in os.environ:
            del os.environ["MESH_SHADOWCAST_MASK"]

        result = maybe_enqueue_shadowmask_enabled_toast(self.mock_window)

        self.assertFalse(result)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_toast_fires_only_once(self):
        os.environ["MESH_SHADOWCAST_MASK"] = "1"

        # First call
        result1 = maybe_enqueue_shadowmask_enabled_toast(self.mock_window)
        self.assertTrue(result1)
        self.mock_window.player_hud.enqueue_toast.assert_called_once()

        self.mock_window.player_hud.enqueue_toast.reset_mock()

        # Second call
        result2 = maybe_enqueue_shadowmask_enabled_toast(self.mock_window)
        self.assertFalse(result2)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_toast_does_not_interfere_with_preset_toast(self):
        # This test ensures that the shadowmask toast logic is independent
        # We don't need to test preset toast logic here, just that our logic doesn't break
        # if preset toast attributes are present or not.

        os.environ["MESH_SHADOWCAST_MASK"] = "1"

        # Simulate preset toast already seen
        self.mock_window._mesh_preset_mode_toasts_seen = {"some_key"}

        result = maybe_enqueue_shadowmask_enabled_toast(self.mock_window)
        self.assertTrue(result)

        # Verify shadowmask persistence is separate
        self.assertTrue(getattr(self.mock_window, "_mesh_shadowmask_toast_seen"))
        self.assertEqual(self.mock_window._mesh_preset_mode_toasts_seen, {"some_key"})
