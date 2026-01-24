from __future__ import annotations

import arcade


def test_partial_config_bindings_still_bind_interact_to_e() -> None:
    from engine.input_controller import InputController

    class _Config:
        input_bindings = {"move_up": ["W"]}

    class _Window:
        engine_config = _Config()

    controller = InputController(_Window())
    bindings = controller.manager.get_bindings()
    assert "interact" in bindings
    assert int(arcade.key.E) in set(bindings["interact"])

