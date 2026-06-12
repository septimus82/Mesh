from types import SimpleNamespace

import arcade

from engine.input_runtime.capture import handle_key_press
from engine.palette_mode import get_state


def test_palette_blocks_gameplay_keys():
    """Test that palette mode blocks interact keys but allows movement keys."""
    # Use SimpleNamespace to avoid MagicMock's truthy attribute behavior
    window = SimpleNamespace(
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(on_key_press=lambda key, mods: False),
        editor_controller=SimpleNamespace(active=False, panels=None),
        command_palette_enabled=False,
        show_debug=True,
    )
    manager = SimpleNamespace(
        is_key_bound_to_action=lambda action, key: False,
        press=lambda key: None,
        release=lambda key: None,
    )
    controller = SimpleNamespace(
        window=window,
        manager=manager,
        _keys=set(),
        _log_debug=lambda msg: None,
    )

    state = get_state()
    state.reset()
    state.enabled = True

    try:
        # E should be blocked (return True)
        assert handle_key_press(controller, arcade.key.E, 0) is True

        # Space should be blocked
        assert handle_key_press(controller, arcade.key.SPACE, 0) is True

        # F3 should be handled (return True)
        assert handle_key_press(controller, arcade.key.F3, 0) is True

        # WASD should NOT be blocked (return False)
        # Assuming they are not mapped to palette keys
        assert handle_key_press(controller, arcade.key.W, 0) is False
    finally:
        state.reset()
