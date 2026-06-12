
import json
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock engine.optional_arcade locally for test to avoid dependency issues if it's missing or complex
mock_arcade = Mock()
mock_arcade.arcade.key.ESCAPE = 65307
mock_arcade.arcade.key.UP = 65362
mock_arcade.arcade.key.DOWN = 65364
mock_arcade.arcade.key.ENTER = 65293
mock_arcade.arcade.key.BACKSPACE = 65288
mock_arcade.arcade.key.DELETE = 65535
mock_arcade.arcade.key.S = 115
mock_arcade.arcade.key.MOD_CTRL = 2
sys.modules['engine.optional_arcade'] = mock_arcade

from engine.editor.editor_keybinds_controller import EditorKeybindsController
from engine.editor.keybinds_ui_model import KeybindsState


class MockEditor:
    def __init__(self):
        self.window = Mock()
        self._keymap_overrides = {}
        # Mocking window actions
        self.window.actions = []

@pytest.fixture
def controller():
    editor = MockEditor()
    # Mock get_editor_actions to return empty list or controlled list
    with patch("engine.editor.editor_keybinds_controller.get_editor_actions") as mock_get_actions:
        mock_get_actions.return_value = []
        c = EditorKeybindsController(editor)
        # Force initial refresh to clear dirty state if needed, though constructor doesn't call it.
        yield c

def test_initial_state(controller):
    assert not controller.state.visible
    assert not controller.state.recording
    assert controller.state.query == ""

def test_open_sets_visible(controller):
    controller.open()
    assert controller.state.visible
    assert controller.state.selected_index == 0

def test_close_hides(controller):
    controller.open()
    controller.close()
    assert not controller.state.visible

def test_recording_flow(controller):
    # Setup rows
    controller._cached_rows = (Mock(scope="global", action_id="test.action", shortcut=""),)
    controller._rows_dirty = False
    controller.state = KeybindsState(visible=True, staged_overrides={})

    # Start recording
    # No patching needed if we prepopulated cache and cleared dirty
    controller.start_recording_selected()
    assert controller.state.recording
    assert controller.state.recording_target == ("global", "test.action")

    # Simulate input
    # Note: We need to mock arcade keys.
    # We can't easily run handle_input without real arcade constant logic unless we mock the import in the controller module
    # or use the real constants.
    pass

def test_save_persists_overrides(controller):
    controller.state = KeybindsState(
        staged_overrides={("global", "test.action"): "Ctrl+X"}
    )

    with patch("engine.editor.editor_keybinds_controller.get_repo_root") as mock_root, \
         patch("engine.editor.editor_keybinds_controller.write_atomic_utf8") as mock_write:

        mock_path = MagicMock()
        mock_root.return_value = mock_path
        target_file = Mock()
        mock_path.__truediv__.return_value = target_file

        # Act
        controller.apply_changes()

        # Assert checks editor state
        assert controller._editor._keymap_overrides == {("global", "test.action"): "Ctrl+X"}

        # Assert file write to the resolved file path
        mock_write.assert_called_once()
        args, _ = mock_write.call_args
        assert args[0] == target_file
        # Data check
        saved_json = args[1]
        saved_data = json.loads(saved_json)
        assert isinstance(saved_data, list)
        assert saved_data[0]["action_id"] == "test.action"
        assert saved_data[0]["shortcut"] == "Ctrl+X"
        assert saved_data[0]["scope"] == "global"

