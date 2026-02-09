from __future__ import annotations

from typing import List

from engine.editor.editor_panels_controller import EditorPanelsController


class _FakeWindow:
    width = 1280
    height = 720
    text_cache = None


class _FakeEditor:
    def __init__(self) -> None:
        self.window = _FakeWindow()
        self._keymap_overrides = {}

    def _handle_context_menu_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return False


class _FakeOverlay:
    def __init__(self, name: str, calls: List[str]) -> None:
        self._name = name
        self._calls = calls

    def draw(self, *args, **kwargs) -> None:
        self._calls.append(self._name)


def test_register_ui_layers_is_deterministic() -> None:
    editor_a = _FakeEditor()
    panels_a = EditorPanelsController(editor_a)
    layers_a = [
        (layer.id, layer.kind, layer.z, layer.blocks_input)
        for layer in editor_a.ui_layers._state.layers
    ]

    editor_b = _FakeEditor()
    panels_b = EditorPanelsController(editor_b)
    layers_b = [
        (layer.id, layer.kind, layer.z, layer.blocks_input)
        for layer in editor_b.ui_layers._state.layers
    ]

    assert layers_a == layers_b

    expected = [
        ("debug", "panel", 10, False),
        ("history", "panel", 10, False),
        ("inspector", "panel", 10, False),
        ("outliner", "panel", 10, False),
        ("prefab_variant", "panel", 10, False),
        ("problems", "panel", 10, False),
        ("project_explorer", "panel", 10, False),
        ("tooltips", "overlay", 500, False),
        ("command_palette", "modal", 1000, True),
        ("keybinds", "modal", 1500, True),
        ("context_menu", "modal", 2000, True),
        ("project_context_menu", "modal", 2000, True),
        ("confirm_modal", "modal", 2500, True),
    ]
    assert layers_a == expected
    assert panels_a is not None
    assert panels_b is not None


def test_draw_panels_calls_draw_in_stable_order() -> None:
    editor = _FakeEditor()
    panels = EditorPanelsController(editor)

    calls: List[str] = []
    editor.keybinds_overlay = _FakeOverlay("keybinds", calls)
    editor.project_context_menu_overlay = _FakeOverlay("project_context_menu", calls)
    editor.confirm_modal_overlay = _FakeOverlay("confirm_modal", calls)

    editor.ui_layers.toggle_layer("keybinds")
    editor.ui_layers.toggle_layer("project_context_menu")
    editor.ui_layers.toggle_layer("confirm_modal")

    panels.draw_panels()
    assert calls == ["keybinds", "project_context_menu", "confirm_modal"]

    calls.clear()
    panels.draw_panels()
    assert calls == ["keybinds", "project_context_menu", "confirm_modal"]


def test_toggle_open_close_calls_ui_stack_correctly() -> None:
    editor = _FakeEditor()
    panels = EditorPanelsController(editor)

    assert panels.is_command_palette_open() is False
    panels.open_command_palette()
    assert panels.is_command_palette_open() is True
    panels.close_command_palette()
    assert panels.is_command_palette_open() is False

    panels.open_keybinds()
    assert panels.is_keybinds_visible() is True
    panels.close_keybinds()
    assert panels.is_keybinds_visible() is False

    panels.open_confirm_modal()
    assert panels.is_confirm_modal_visible() is True
    panels.close_confirm_modal()
    assert panels.is_confirm_modal_visible() is False


def test_modal_blocking_is_preserved() -> None:
    editor = _FakeEditor()
    panels = EditorPanelsController(editor)

    panels.open_command_palette()
    assert editor.ui_layers._state.active_modal_id == "command_palette"

    panels.open_context_menu()
    assert editor.ui_layers._state.active_modal_id == "context_menu"

    panels.close_context_menu()
    assert editor.ui_layers._state.active_modal_id == "command_palette"
