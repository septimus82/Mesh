"""Input abstraction layer for Mesh Engine."""

from __future__ import annotations

from typing import Dict, Iterable, List, Set


class InputManager:
    """
    Minimal input manager that maps raw key presses to simple actions.

    Consumers can query raw keys, boolean actions, or axis pairs without
    depending on Arcade-specific constants outside of binding time.
    """

    def __init__(self) -> None:
        self._keys_down: Set[int] = set()
        self._actions: Dict[str, Set[int]] = {}
        self._capturing_text: bool = False
        self._text_buffer: str = ""
        self._action_state: Dict[str, bool] = {}
        self._actions_pressed: Set[str] = set()
        self._gamepad_actions_down: Set[str] = set()
        self._gamepad_actions_supported: Set[str] = set()
        self._gamepad_axes: Dict[tuple[str, str], float] = {}
        self._input_source: str = "keyboard_mouse"

    @property
    def input_source(self) -> str:
        """Return the last detected input source."""
        return self._input_source

    def note_keyboard_mouse_activity(self) -> None:
        """Mark that keyboard/mouse input was observed recently."""
        self._input_source = "keyboard_mouse"

    def set_gamepad_state(
        self,
        *,
        actions_down: Iterable[str] | None = None,
        axis_values: Dict[tuple[str, str], float] | None = None,
        supported_actions: Iterable[str] | None = None,
        source_active: bool = False,
    ) -> None:
        """Inject gamepad-derived action/axis state for this frame."""
        actions = {str(action) for action in (actions_down or []) if str(action)}
        if supported_actions is None:
            self._gamepad_actions_supported.update(actions)
        else:
            self._gamepad_actions_supported = {
                str(action) for action in supported_actions if str(action)
            }
        self._gamepad_actions_down = actions
        if axis_values is not None:
            self._gamepad_axes = {
                (str(neg), str(pos)): float(value)
                for (neg, pos), value in axis_values.items()
            }
        if source_active:
            self._input_source = "gamepad"

    # --- raw key tracking -------------------------------------------------
    def press(self, key: int) -> None:
        """Record that the provided key is currently held down."""
        self._keys_down.add(key)
        self.note_keyboard_mouse_activity()

    def release(self, key: int) -> None:
        """Mark the provided key as no longer pressed."""
        self._keys_down.discard(key)

    def is_key_down(self, key: int) -> bool:
        """Return True when the provided key is currently pressed."""
        return key in self._keys_down

    def get_keys_down(self) -> Set[int]:
        """Return a copy of the currently pressed raw keys."""
        return set(self._keys_down)

    # --- action mappings --------------------------------------------------
    def bind(self, action: str, key: int) -> None:
        """Bind a key to an action name."""
        if action not in self._actions:
            self._actions[action] = set()
            self._action_state[action] = False
        self._actions[action].add(key)

    def unbind(self, action: str, key: int) -> None:
        """Remove a key binding from an action."""
        if action in self._actions:
            self._actions[action].discard(key)
            if not self._actions[action]:
                del self._actions[action]
                self._action_state.pop(action, None)
        if not self._actions:
            self._actions_pressed.clear()

    def get_bindings(self) -> Dict[str, List[int]]:
        """Return the current action bindings as sorted key code lists."""
        return {
            action: sorted(keys)
            for action, keys in self._actions.items()
        }

    def get_bound_action_names(self) -> Iterable[str]:
        """Return an iterator over bound action names (zero-allocation)."""
        for action in self._actions.keys():
            yield action
        extras = [action for action in self._gamepad_actions_supported if action not in self._actions]
        for action in sorted(extras):
            yield action

    def is_key_bound_to_action(self, action: str, key: int) -> bool:
        """Return True if the raw key is currently bound to the action."""
        keys = self._actions.get(action)
        if not keys:
            return False
        return int(key) in keys

    def clear_bindings(self) -> None:
        """Remove all action bindings."""
        self._actions.clear()
        self._action_state.clear()
        self._actions_pressed.clear()

    def set_bindings(self, bindings: Dict[str, Iterable[int]]) -> None:
        """Replace all action bindings with the provided mapping."""
        self._actions.clear()
        for action, keys in bindings.items():
            key_set = {int(code) for code in keys if code is not None}
            if key_set:
                self._actions[action] = key_set
        self._action_state = {action: False for action in self._actions}
        self._actions_pressed.clear()

    def is_action_down(self, action: str) -> bool:
        """Return True if any key bound to the action is currently down."""
        action = str(action)
        if action in self._gamepad_actions_down:
            return True
        keys = self._actions.get(action)
        if not keys:
            return False
        return any(k in self._keys_down for k in keys)

    def was_action_pressed(self, action: str) -> bool:
        """Return True if the action transitioned from up->down this frame."""
        return action in self._actions_pressed

    def get_axis(self, negative_action: str, positive_action: str) -> float:
        """
        Return -1, 0, or 1 based on two opposing actions.

        Example: get_axis("move_left", "move_right")
        """
        axis_key = (str(negative_action), str(positive_action))
        analog = self._gamepad_axes.get(axis_key)
        if analog is not None and abs(analog) > 0.0:
            return max(-1.0, min(1.0, float(analog)))
        neg = self.is_action_down(negative_action)
        pos = self.is_action_down(positive_action)
        if neg and not pos:
            return -1.0
        if pos and not neg:
            return 1.0
        return 0.0

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        """Refresh action edge-detection state each frame."""
        active_actions = set(self._actions.keys())
        active_actions.update(self._gamepad_actions_supported)
        pressed: Set[str] = set()
        for action in active_actions:
            down = self.is_action_down(action)
            previous = self._action_state.get(action, False)
            if down and not previous:
                pressed.add(action)
            self._action_state[action] = down
        # Drop state for actions that were removed since the last frame.
        for action in list(self._action_state.keys()):
            if action not in active_actions:
                self._action_state.pop(action, None)
        self._actions_pressed = pressed

    # --- convenience defaults --------------------------------------------
    def bind_default_movement(self, arcade_module) -> None:
        """
        Bind a default WASD movement scheme using arcade.key codes.

        Accepts the arcade module so this file keeps a clean dependency
        surface and remains importable without Arcade present.
        """
        self.bind("move_up", arcade_module.key.W)
        self.bind("move_down", arcade_module.key.S)
        self.bind("move_left", arcade_module.key.A)
        self.bind("move_right", arcade_module.key.D)

    def bind_default_actions(self, arcade_module) -> None:
        """Bind the default movement keys plus interaction shortcuts."""
        self.bind_default_movement(arcade_module)
        self.bind("interact", arcade_module.key.E)
        self.bind("attack", arcade_module.key.SPACE)
        self.bind("show_quests", arcade_module.key.Q)
        self.bind("show_quests", arcade_module.key.J)
        self.bind("show_inventory", arcade_module.key.TAB)
        self.bind("show_character", arcade_module.key.C)
        self.bind("toggle_editor", arcade_module.key.F4)
        self.bind("toggle_help", arcade_module.key.H)
        self.bind("toggle_inspector", arcade_module.key.I)


    def start_text_capture(self) -> None:
        """Begin capturing printable text into an internal buffer."""
        self._capturing_text = True
        self._text_buffer = ""

    def stop_text_capture(self) -> str:
        """Stop capture and return the current text buffer."""
        text = self._text_buffer
        self._capturing_text = False
        self._text_buffer = ""
        return text

    def feed_text(self, text: str) -> None:
        """Append text to the capture buffer if capturing is active."""
        if self._capturing_text and text:
            self._text_buffer += text
            self.note_keyboard_mouse_activity()

    def backspace(self) -> None:
        """Remove the last character from the capture buffer."""
        if self._capturing_text and self._text_buffer:
            self._text_buffer = self._text_buffer[:-1]
            self.note_keyboard_mouse_activity()

    def get_text_buffer(self) -> str:
        """Expose the current capture buffer without modifying it."""
        return self._text_buffer

    def set_text_buffer(self, value: str) -> None:
        """Replace the capture buffer contents when capturing is active."""
        if self._capturing_text:
            self._text_buffer = value
