import pytest
from unittest.mock import MagicMock
from engine.console_runtime.commands import dispatch_command, _DISPATCH

def test_console_commands_registered():
    """Ensure critical commands are registered in the dispatch table."""
    expected_commands = {
        "clear", "pause", "strict_on", "strict_off", "selftest",
        "flag", "counter", "gstate", "quest", "cutscene", "xp", "stats", "world"
    }
    
    for cmd in expected_commands:
        assert cmd in _DISPATCH, f"Command '{cmd}' should be registered"

def test_console_dispatch_delegation():
    """Ensure dispatch_command calls the appropriate handler."""
    controller = MagicMock()
    controller.window = MagicMock()
    controller.lines = []
    
    # Test 'clear' command
    # It should clear lines (already empty) and set scroll_offset
    dispatch_command(controller, "clear", [])
    assert controller.scroll_offset == 0
    
    # Test 'flag' command (no args)
    # It should log something
    dispatch_command(controller, "flag", [])
    controller.log.assert_called()

def test_console_facade_structure():
    """
    Verify that ConsoleController still has the necessary structure 
    to support the runtime, even if methods are moved.
    """
    from engine.console_controller import ConsoleController
    
    # Check that ConsoleController has the attributes expected by handlers
    # We can't easily check instance attributes without instantiation, 
    # but we can check methods if any are expected.
    # Handlers mostly use 'window', 'log', 'lines', 'scroll_offset'.
    
    assert hasattr(ConsoleController, "log")
    # 'lines' and 'scroll_offset' are instance attributes set in __init__
