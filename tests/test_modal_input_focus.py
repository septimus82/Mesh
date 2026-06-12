import unittest
from unittest.mock import MagicMock, patch

from engine.input_controller import InputController
from engine.ui import UIElement
from engine.ui_controller import UIController


class BlockingElement(UIElement):
    @property
    def blocks_input(self) -> bool:
        return True

class NonBlockingElement(UIElement):
    @property
    def blocks_input(self) -> bool:
        return False

class TestModalInputFocus(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.ui_controller = UIController(self.window)
        self.window.ui_controller = self.ui_controller
        self.input_controller = InputController(self.window)

        # Mock InputManager
        self.input_controller.manager = MagicMock()
        self.input_controller.manager.was_action_pressed = MagicMock(return_value=False)
        self.input_controller.manager.get_bindings = MagicMock(return_value={"test_action": [1]})
        self.input_controller.manager.get_bound_action_names = MagicMock(return_value=["test_action"])

    def test_ui_element_blocks_input_default(self):
        element = UIElement(self.window)
        self.assertFalse(element.blocks_input)

    def test_ui_controller_input_blocked_false_by_default(self):
        self.assertFalse(self.ui_controller.input_blocked)

    def test_ui_controller_input_blocked_true_when_element_blocks(self):
        element = BlockingElement(self.window)
        self.ui_controller.register_ui_element(element)
        self.assertTrue(self.ui_controller.input_blocked)

    def test_ui_controller_input_blocked_false_when_element_does_not_block(self):
        element = NonBlockingElement(self.window)
        self.ui_controller.register_ui_element(element)
        self.assertFalse(self.ui_controller.input_blocked)

    def test_input_controller_update_blocked(self):
        # Setup an action that would normally fire
        self.input_controller.manager.was_action_pressed.return_value = True

        # Mock dispatch_action to verify it's NOT called
        with patch('engine.input_controller.dispatch_action') as mock_dispatch:
            # Case 1: Input NOT blocked
            # Ensure no blocking elements
            self.ui_controller.clear_ui_elements()

            self.input_controller.update(0.1)
            mock_dispatch.assert_called()

            mock_dispatch.reset_mock()

            # Case 2: Input BLOCKED
            element = BlockingElement(self.window)
            self.ui_controller.register_ui_element(element)

            self.input_controller.update(0.1)
            mock_dispatch.assert_not_called()
