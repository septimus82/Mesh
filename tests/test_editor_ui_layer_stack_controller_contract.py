"""
Contract tests for Editor UI Layer Stack Controller methods.
"""
from engine.editor_ui_layer_stack_controller import EditorUiLayerStackController


class MockEditor:
    pass

def test_controller_flow():
    ctl = EditorUiLayerStackController(MockEditor())

    handled_keys = []
    def handler(key, mods):
        handled_keys.append(key)
        return True

    ctl.register_layer(
        "cmd", "modal", z=100, blocks_input=True,
        input_handler=handler
    )

    # 1. Hidden -> dispatch fail
    assert ctl.dispatch_input(1, 0) is False

    # 2. Visble -> dispatch OK
    ctl.push_modal("cmd")
    assert ctl.is_visible("cmd") is True
    assert ctl.dispatch_input(1, 0) is True
    assert handled_keys == [1]

    # 3. Hidden -> dispatch fail
    ctl.pop_modal("cmd")
    assert ctl.dispatch_input(2, 0) is False

def test_input_blocking():
    ctl = EditorUiLayerStackController(MockEditor())

    log = []

    ctl.register_layer(
        "bg", "panel", z=0, visible=True,
        input_handler=lambda k, m: log.append("bg") or True
    )

    ctl.register_layer(
        "modal", "modal", z=10, blocks_input=True, visible=False,
        input_handler=lambda k, m: log.append("modal") or True
    )

    # 1. Modal hidden: bg gets it
    ctl.dispatch_input(0,0)
    assert log == ["bg"]

    log.clear()

    # 2. Modal shown: only modal gets it (blocking)
    ctl.push_modal("modal")
    ctl.dispatch_input(0,0)
    assert log == ["modal"]
