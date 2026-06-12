"""
Controller for the editor UI layer stack.

Manages registration and runtime state of UI layers (modals, panels).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .ui_layer_stack_model import UiLayer, UiStackState, get_layer, pop_modal, push_modal, register_layer, route_input_targets, set_visible


class EditorUiLayerStackController:
    def __init__(self, editor: Any):
        self._editor = editor
        self._state = UiStackState()
        self._input_handlers: Dict[str, Callable[[int, int], bool]] = {}
        self._text_handlers: Dict[str, Callable[[str], bool]] = {}
        self._draw_handlers: Dict[str, Callable[[Any], None]] = {}

    def register_layer(
        self,
        id: str,
        kind: str,
        z: str | int,
        blocks_input: bool = False,
        visible: bool = False,
        input_handler: Optional[Callable[[int, int], bool]] = None,
        text_handler: Optional[Callable[[str], bool]] = None,
        draw_handler: Optional[Callable[[Any], None]] = None
    ) -> None:
        """Register a new UI layer."""
        layer = UiLayer(
            id=id,
            kind=kind,
            visible=visible,
            z=int(z),
            blocks_input=blocks_input
        )
        self._state = register_layer(self._state, layer)

        if input_handler:
            self._input_handlers[id] = input_handler
        if text_handler:
            self._text_handlers[id] = text_handler
        if draw_handler:
            self._draw_handlers[id] = draw_handler

    def is_visible(self, layer_id: str) -> bool:
        layer = get_layer(self._state, layer_id)
        return layer.visible if layer else False

    def push_modal(self, modal_id: str) -> None:
        self._state = push_modal(self._state, modal_id)

    def pop_modal(self, modal_id: str) -> None:
        self._state = pop_modal(self._state, modal_id)

    def toggle_layer(self, layer_id: str) -> None:
        visible = self.is_visible(layer_id)
        if visible:
            # Check if it was a modal, use pop?
            # Model pop_modal just uses set_visible(False).
            self._state = set_visible(self._state, layer_id, False)
        else:
            # Check if modal
            layer = get_layer(self._state, layer_id)
            if layer and layer.kind == "modal":
                self._state = push_modal(self._state, layer_id)
            else:
                self._state = set_visible(self._state, layer_id, True)

    def dispatch_input(self, key: int, modifiers: int) -> bool:
        """
        Route input to layers in priority order.
        Returns True if handled.
        """
        targets = route_input_targets(self._state)

        for target_id in targets:
            handler = self._input_handlers.get(target_id)
            if handler:
                if handler(key, modifiers):
                    return True

            # If layer blocks input, do we stop propagation even if not handled?
            # Model `route_input_targets` already stops returning targets if a blocking modal is hit.
            # But the blocking modal itself is included in targets.
            # If blocking modal doesn't handle it, does it fall through to global?
            # Prompt says: "Routes input in priority order... 1) active modal... 2) focused widget... 3) global"
            # If active modal blocks input, presumably it should consume it or allow fallthrough to global?
            # "modal first (if blocks_input), then other visible layers..."
            # If blocking modal is present, `route_input_targets` returns ONLY the modal.
            # If modal handler returns False, we return False here?
            # If we return False here, the caller (fallback) will try focused widget/global.
            # So "blocks_input" in model prevents *other layers* from getting input.
            # It does NOT necessarily prevent fallback to global shortcuts if the modal ignores it (e.g. F11 for fullscreen might still work?)
            # But usually a blocking modal (like command palette) wants to swallow everything except maybe special keys.
            pass

        return False

    def dispatch_text(self, text: str) -> bool:
        """
        Route text input to layers in priority order.
        Returns True if handled.
        """
        targets = route_input_targets(self._state)

        for target_id in targets:
            handler = self._text_handlers.get(target_id)
            if handler:
                if handler(text):
                    return True
        return False

    def draw_all(self, ctx: Any = None) -> None:
        """
        Draw all visible layers in Z order (asc).
        """
        # Model normalize_layers returns Z asc.
        for layer in self._state.layers:
            if layer.visible:
                handler = self._draw_handlers.get(layer.id)
                if handler:
                    handler(ctx)
