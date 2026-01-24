import unittest
from unittest.mock import MagicMock, patch
import io
import sys

from engine.input_controller import InputController
from engine.tooling import get_log_count, reset_log_counters

class TestEventSpamGuard(unittest.TestCase):
    def setUp(self):
        reset_log_counters()
        self.window = MagicMock()
        # Mock UI controller to not block input
        self.window.ui_controller = MagicMock()
        self.window.ui_controller.input_blocked = False
        
        self.controller = InputController(self.window)
        # Bind a test action
        self.controller.manager.bind("test_spam_action", 1)

    def test_spam_guard_logs_once_and_counts(self):
        # Mock dispatch_action to always fail (return False), triggering the warning
        with patch("engine.input_controller.dispatch_action", return_value=False):
            # Mock was_action_pressed to always return True for our action
            self.controller.manager.was_action_pressed = MagicMock(return_value=True)
            
            # Capture stderr (logs should never go to stdout)
            captured_output = io.StringIO()
            sys.stderr = captured_output
            
            try:
                # Trigger 5 times
                for _ in range(5):
                    self.controller.update(0.1)
            finally:
                sys.stderr = sys.__stderr__
            
            output = captured_output.getvalue()
            
            # Assert log message appears exactly once
            expected_msg = "[Mesh][Input] Unknown action 'test_spam_action'"
            self.assertIn(expected_msg, output)
            self.assertEqual(output.count(expected_msg), 1, "Should only log once")
            
            # Assert counter is 5
            count = get_log_count("input_unknown_action:test_spam_action")
            self.assertEqual(count, 5, "Counter should track all occurrences")

    def test_micro_optimization_usage(self):
        # Verify that get_bound_action_names is used instead of get_bindings().keys()
        # We can check this by mocking the manager methods
        
        self.controller.manager.get_bindings = MagicMock()
        self.controller.manager.get_bound_action_names = MagicMock(return_value=["test_action"])
        self.controller.manager.was_action_pressed = MagicMock(return_value=False)
        
        self.controller.update(0.1)
        
        # get_bindings should NOT be called (that's the optimization)
        self.controller.manager.get_bindings.assert_not_called()
        # get_bound_action_names SHOULD be called
        self.controller.manager.get_bound_action_names.assert_called_once()
