"""Input controller managing keyboard, mouse, and gamepad input.

Provides a unified input handling system that:

- **Action Mapping**: Maps physical keys/buttons to logical actions
- **Gamepad Support**: Xbox-style controller with deadzone handling
- **Input Capture**: Modal input capture for console/menus
- **Rebindable Keys**: Runtime key remapping via settings

Architecture:
    The InputController wraps Arcade's input system and adds:
    - Logical action layer ("move_left" instead of KEY_A)
    - Simultaneous keyboard + gamepad support
    - Input capture stack for UI priority
    - Gamepad axis deadzone filtering

Default Key Bindings:
    Movement: WASD / Arrow keys
    Interact: E / Gamepad A
    Attack: Space / Gamepad X
    Inventory: Tab / Gamepad Y
    Pause: Escape / Gamepad Start
    Console: F1 (not Help; Help is H / Gamepad Back)

Gamepad Support:
    - Left stick: Movement (with configurable deadzone)
    - A button: Interact
    - X button: Attack
    - Y button: Inventory
    - Start: Pause menu
    - Back: Help overlay

Example::

    # Check if action is pressed this frame
    if window.input_controller.is_action_pressed("interact"):
        talk_to_npc()

    # Check if action is held
    if window.input_controller.is_action_held("attack"):
        charge_attack()

    # Get movement vector (keyboard or gamepad)
    dx, dy = window.input_controller.get_movement_vector()
    player.velocity = (dx * speed, dy * speed)

Configuration (config.json)::

    {
        "keybinds": {
            "interact": ["E", "ENTER"],
            "attack": ["SPACE"],
            "move_left": ["A", "LEFT"]
        }
    }

See Also:
    - :mod:`engine.input_bindings` for action definitions
    - :mod:`engine.actions` for action dispatch
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Iterable, Set
import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from .actions import dispatch_action
from .input_runtime import capture as input_capture
from .input_runtime import dispatch as input_dispatch
from .logging_tools import get_logger
from engine.log_once import log_once_with_counter

logger = logging.getLogger(__name__)
_stderr_logger = get_logger(__name__)
from .input import InputManager
from .input_bindings import ACTION_SHOW_CHARACTER, apply_config_bindings, known_actions, snapshot_bindings


if TYPE_CHECKING:
    from .game import GameWindow

# Gamepad configuration constants
_GAMEPAD_DEADZONE_DEFAULT = 0.2  # Minimum stick deflection to register
_GAMEPAD_AXIS_PAIRS: tuple[tuple[str, str], ...] = (
    ("move_left", "move_right"),
    ("move_down", "move_up"),
)
_GAMEPAD_BUTTON_ACTIONS: dict[str, str] = {
    "a": "interact",
    "b": "toggle_help",
    "x": "attack",
    "y": "show_inventory",
    "start": "pause_menu",
    "back": "toggle_help",
}
_GAMEPAD_SUPPORTED_ACTIONS: set[str] = {
    "move_left",
    "move_right",
    "move_down",
    "move_up",
    *tuple(_GAMEPAD_BUTTON_ACTIONS.values()),
}
_EMPTY_GAMEPAD_AXES: dict[tuple[str, str], float] = {
    pair: 0.0 for pair in _GAMEPAD_AXIS_PAIRS
}


def _coerce_button_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    pressed = getattr(value, "pressed", None)
    if pressed is not None:
        return bool(pressed)
    is_pressed = getattr(value, "is_pressed", None)
    if callable(is_pressed):
        try:
            return bool(is_pressed())
        except Exception:  # noqa: BLE001  # REASON: input wrapper query failures should fall back to an unpressed state
            return False
    raw = getattr(value, "value", None)
    if isinstance(raw, (int, float)):
        return bool(raw)
    return False


def _read_axis_value(controller: object, names: Iterable[str]) -> float:
    for name in names:
        value = getattr(controller, name, None)
        if isinstance(value, (int, float)):
            return float(value)
    axis_values = getattr(controller, "axis_values", None)
    if isinstance(axis_values, dict):
        for name in names:
            if name in axis_values:
                try:
                    return float(axis_values[name])
                except (TypeError, ValueError):
                    return 0.0
    axes = getattr(controller, "axes", None)
    if isinstance(axes, Iterable):
        for axis in axes:
            axis_name = getattr(axis, "name", None)
            if isinstance(axis_name, str) and axis_name in names:
                value = getattr(axis, "value", None)
                if isinstance(value, (int, float)):
                    return float(value)
    return 0.0


def _read_button_state(controller: object, aliases: Iterable[str], index: int | None) -> bool:
    for name in aliases:
        value = getattr(controller, name, None)
        if value is not None:
            return _coerce_button_value(value)
    buttons = getattr(controller, "buttons", None)
    if isinstance(buttons, (list, tuple)) and index is not None and 0 <= index < len(buttons):
        return _coerce_button_value(buttons[index])
    return False


def read_gamepad_state(controller: object) -> tuple[float, float, set[str], float, float]:
    axis_x = _read_axis_value(controller, ("leftx", "left_x", "lx", "x"))
    axis_y = _read_axis_value(controller, ("lefty", "left_y", "ly", "y"))
    dpad_x = _read_axis_value(controller, ("dpadx", "dpad_x", "hat_x"))
    dpad_y = _read_axis_value(controller, ("dpady", "dpad_y", "hat_y"))
    button_aliases = {
        "a": (("a", "button_a", "south"), 0),
        "b": (("b", "button_b", "east"), 1),
        "x": (("x", "button_x", "west"), 2),
        "y": (("y", "button_y", "north"), 3),
        "back": (("back", "select", "button_back", "button_select"), 6),
        "start": (("start", "menu", "button_start", "button_menu"), 7),
    }
    buttons_down: set[str] = set()
    for name, (aliases, index) in button_aliases.items():
        if _read_button_state(controller, aliases, index):
            buttons_down.add(name)
    return axis_x, axis_y, buttons_down, dpad_x, dpad_y


def map_gamepad_state(
    axis_x: float,
    axis_y: float,
    buttons_down: Iterable[str],
    *,
    dpad_x: float = 0.0,
    dpad_y: float = 0.0,
    deadzone: float = _GAMEPAD_DEADZONE_DEFAULT,
) -> tuple[set[str], dict[tuple[str, str], float], bool]:
    axis_x = max(-1.0, min(1.0, float(axis_x)))
    axis_y = -max(-1.0, min(1.0, float(axis_y)))
    dpad_x = float(dpad_x)
    dpad_y = float(dpad_y)

    axis_values = {
        ("move_left", "move_right"): axis_x if abs(axis_x) >= deadzone else 0.0,
        ("move_down", "move_up"): axis_y if abs(axis_y) >= deadzone else 0.0,
    }

    actions_down: set[str] = set()
    if axis_x <= -deadzone:
        actions_down.add("move_left")
    elif axis_x >= deadzone:
        actions_down.add("move_right")
    if axis_y <= -deadzone:
        actions_down.add("move_down")
    elif axis_y >= deadzone:
        actions_down.add("move_up")

    if dpad_x <= -0.5:
        actions_down.add("move_left")
    elif dpad_x >= 0.5:
        actions_down.add("move_right")
    if dpad_y <= -0.5:
        actions_down.add("move_down")
    elif dpad_y >= 0.5:
        actions_down.add("move_up")

    for button in buttons_down:
        action = _GAMEPAD_BUTTON_ACTIONS.get(str(button))
        if action:
            actions_down.add(action)

    source_active = bool(actions_down)
    return actions_down, axis_values, source_active

ACTIONS_ALLOWED_WHEN_BLOCKED = input_capture.ACTIONS_ALLOWED_WHEN_BLOCKED
GAMEPLAY_ACTIONS = input_capture.GAMEPLAY_ACTIONS


class InputController:
    def __init__(self, window: GameWindow):
        self.window = window
        self.manager = InputManager()
        self._apply_rumble_config_from_engine_config()
        self._load_configured_bindings()

        self._keys: Set[int] = set()
        self._mouse_x: float = 0.0
        self._mouse_y: float = 0.0
        self._input_lock_owners: Set[str] = set()
        self._first_input_toast_fired: bool = False
        self._gamepad_deadzone: float = _GAMEPAD_DEADZONE_DEFAULT
        self._gamepad_controller: object | None = None

    def _apply_rumble_config_from_engine_config(self) -> None:
        cfg = getattr(self.window, "engine_config", None)
        input_cfg = getattr(cfg, "input", None) if cfg is not None else None
        enabled: object = False
        strength: object = 1.0
        if isinstance(input_cfg, dict):
            enabled = input_cfg.get("rumble_enabled", False)
            strength = input_cfg.get("rumble_strength", 1.0)
        setter = getattr(self.manager, "set_rumble_config", None)
        if callable(setter):
            setter(enabled=enabled, strength=strength)

    @property
    def mouse_x(self) -> float:
        return self._mouse_x

    @property
    def mouse_y(self) -> float:
        return self._mouse_y

    def _log_debug(self, message: str) -> None:
        info = getattr(_stderr_logger, "info", None)
        if callable(info):
            info("%s", message)

    def update(self, delta_time: float) -> None:
        self._poll_gamepad_state()
        input_dispatch.update(
            self,
            delta_time,
            dispatch_action=dispatch_action,
            log_once_with_counter=log_once_with_counter,
        )

    def _poll_gamepad_state(self) -> None:
        setter = getattr(self.manager, "set_gamepad_state", None)
        set_rumble_backend = getattr(self.manager, "set_rumble_backend", None)
        if not callable(setter):
            return

        arcade_mod = optional_arcade.arcade
        if arcade_mod is None:
            setter(
                actions_down=(),
                axis_values=_EMPTY_GAMEPAD_AXES,
                supported_actions=_GAMEPAD_SUPPORTED_ACTIONS,
                source_active=False,
            )
            if callable(set_rumble_backend):
                set_rumble_backend(None)
            self._gamepad_controller = None
            return

        get_controllers = getattr(arcade_mod, "get_game_controllers", None)
        if not callable(get_controllers):
            if callable(set_rumble_backend):
                set_rumble_backend(None)
            return

        try:
            controllers = list(get_controllers() or [])
        except Exception:  # noqa: BLE001  # REASON: controller enumeration failures should fall back to no connected controllers
            controllers = []

        if not controllers:
            setter(
                actions_down=(),
                axis_values=_EMPTY_GAMEPAD_AXES,
                supported_actions=_GAMEPAD_SUPPORTED_ACTIONS,
                source_active=False,
            )
            if callable(set_rumble_backend):
                set_rumble_backend(None)
            self._gamepad_controller = None
            return

        controller = controllers[0]
        if controller is not self._gamepad_controller:
            self._gamepad_controller = controller
            if callable(set_rumble_backend):
                set_rumble_backend(controller)
            opener = getattr(controller, "open", None)
            if callable(opener):
                try:
                    opener()
                except Exception:  # noqa: BLE001  # REASON: controller open failures should not break input backend initialization
                    _log_swallow("INPU-001", "engine/input_controller.py pass-only blanket swallow")
                    pass

        axis_x, axis_y, buttons_down, dpad_x, dpad_y = read_gamepad_state(controller)
        actions_down, axis_values, source_active = map_gamepad_state(
            axis_x,
            axis_y,
            buttons_down,
            dpad_x=dpad_x,
            dpad_y=dpad_y,
            deadzone=self._gamepad_deadzone,
        )
        setter(
            actions_down=actions_down,
            axis_values=axis_values,
            supported_actions=_GAMEPAD_SUPPORTED_ACTIONS,
            source_active=source_active,
        )

    def on_key_press(self, key: int, modifiers: int) -> bool:
        return input_capture.handle_key_press(self, key, modifiers)

    def on_key_release(self, key: int, modifiers: int) -> bool:
        return input_capture.handle_key_release(self, key, modifiers)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        input_capture.handle_mouse_motion(self, x, y, dx, dy)
        note = getattr(self.manager, "note_keyboard_mouse_activity", None)
        if callable(note):
            note()

    def on_mouse_drag(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> None:
        input_capture.handle_mouse_drag(self, x, y, dx, dy, buttons, modifiers)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        consumed = input_capture.handle_mouse_press(self, x, y, button, modifiers)
        note = getattr(self.manager, "note_keyboard_mouse_activity", None)
        if callable(note):
            note()
        return consumed

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> bool:
        return input_capture.handle_mouse_release(self, x, y, button, modifiers)

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        consumed = input_capture.handle_mouse_scroll(self, x, y, scroll_x, scroll_y)
        note = getattr(self.manager, "note_keyboard_mouse_activity", None)
        if callable(note):
            note()
        return consumed

    def on_text(self, text: str) -> None:
        input_capture.handle_text(self, text)

    def get_keys_down(self) -> Set[int]:
        return self.manager.get_keys_down()

    def lock_player_input(self, *, owner: str | None = None) -> None:
        key = owner or "<anonymous>"
        self._input_lock_owners.add(str(key))

    def unlock_player_input(self, *, owner: str | None = None) -> None:
        if owner is None:
            self._input_lock_owners.clear()
            return
        self._input_lock_owners.discard(str(owner))

    def clear_input_locks(self) -> None:
        self._input_lock_owners.clear()

    def is_input_locked(self) -> bool:
        return bool(self._input_lock_owners)

    def player_input_blocked(self) -> bool:
        return input_capture.player_input_blocked(self)

    def _load_configured_bindings(self) -> None:
        """Load bindings from config; fall back to default actions."""
        cfg = getattr(self.window, "engine_config", None)
        bindings = getattr(cfg, "input_bindings", None) if cfg is not None else None
        applied = apply_config_bindings(
            self.manager,
            bindings,
            warn=self._log_binding_warning,
            arcade_module=optional_arcade.arcade,
        )
        if ACTION_SHOW_CHARACTER not in self.manager.get_bindings():
            self.manager.bind(ACTION_SHOW_CHARACTER, optional_arcade.arcade.key.C)
        if "interact" not in self.manager.get_bindings():
            self.manager.bind("interact", optional_arcade.arcade.key.E)
        if bindings is None and not applied:
            self.manager.bind_default_actions(optional_arcade.arcade)
        # Keep baseline movement/pause bindings reachable even with partial config.
        if not self.manager.is_key_bound_to_action("move_up", optional_arcade.arcade.key.UP):
            self.manager.bind("move_up", optional_arcade.arcade.key.UP)
        if not self.manager.is_key_bound_to_action("move_down", optional_arcade.arcade.key.DOWN):
            self.manager.bind("move_down", optional_arcade.arcade.key.DOWN)
        if not self.manager.is_key_bound_to_action("move_left", optional_arcade.arcade.key.LEFT):
            self.manager.bind("move_left", optional_arcade.arcade.key.LEFT)
        if not self.manager.is_key_bound_to_action("move_right", optional_arcade.arcade.key.RIGHT):
            self.manager.bind("move_right", optional_arcade.arcade.key.RIGHT)
        if not self.manager.is_key_bound_to_action("pause_menu", optional_arcade.arcade.key.ESCAPE):
            self.manager.bind("pause_menu", optional_arcade.arcade.key.ESCAPE)
        self.persist_bindings(save=False)

    def _log_binding_warning(self, message: str) -> None:
        _stderr_logger.info("[Mesh][Input] %s", message)

    def persist_bindings(self, *, save: bool = True) -> dict[str, list[str]]:
        """
        Update the EngineConfig input_bindings field and optionally save.

        Returns the snapshot that was written back to the config object.
        """
        snapshot = snapshot_bindings(self.manager, arcade_module=optional_arcade.arcade)
        cfg = getattr(self.window, "engine_config", None)
        if cfg is not None:
            cfg.input_bindings = snapshot
            if save:
                try:
                    from .config import save_config

                    save_config(cfg)
                except Exception:
                    _log_swallow("input_save_bindings", "Failed to save bindings")
        return snapshot

    def get_bindings_as_names(self) -> dict[str, list[str]]:
        """Expose the current bindings as a config-friendly snapshot."""
        return snapshot_bindings(self.manager, arcade_module=optional_arcade.arcade)

    def get_known_actions(self) -> set[str]:
        """Return the union of default, config, and runtime actions."""
        cfg = getattr(self.window, "engine_config", None)
        bindings = getattr(cfg, "input_bindings", None) if cfg is not None else None
        return known_actions(self.manager, bindings)
