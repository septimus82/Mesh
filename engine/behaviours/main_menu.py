from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import engine.optional_arcade as optional_arcade

from ..input_bindings import known_actions, snapshot_bindings
from ..ui import UIElement
from .base import Behaviour
from .registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite

    from ..game import GameWindow

@register_behaviour("MainMenuBehaviour", description="Handles the main menu logic and rendering.")
class MainMenuBehaviour(Behaviour):

    """Handles the main menu logic and rendering."""

    def __init__(self, entity: "Sprite", window: GameWindow, **config: Any):
        super().__init__(entity, window, **config)

        self.options = ["New Game", "Load Game", "Settings", "Credits", "Quit"]
        self.selected_index = 0
        self.state = "main"  # main, load_game, settings, credits
        self.save_slots: list[str] = []
        self.selected_save_index = 0

        # Settings
        self.volume_options = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        # Try to find current volume in options, default to 1.0 (index 10)
        current_vol = getattr(self.window, "audio", None)
        current_vol_val = current_vol.master_volume if current_vol else 1.0
        # Find closest match
        self.current_volume_index = min(range(len(self.volume_options)), key=lambda i: abs(self.volume_options[i] - current_vol_val))

        # Credits
        self.credits_text = [
            "MESH ENGINE DEMO",
            "",
            "Created by: The Mesh Team",
            "",
            "Programming: Copilot",
            "Art: Placeholder Assets",
            "Music: Generated",
            "",
            "Thanks for playing!"
        ]

        # Simple text drawing setup
        self.font_size = 20
        self.line_height = 30
        self.start_y = self.window.height / 2 + 50

    def on_update(self, delta_time: float) -> None:
        # Input handling is done in on_key_press via InputController hook or direct check
        # Since Behaviour doesn't have on_key_press, we check input controller state or hook into events
        # But InputController is designed for game input.
        # For menu, we might need to check key presses directly or use the input controller's state.
        # However, InputController.get_keys_down() returns a set of currently pressed keys, not "just pressed".
        # We need "just pressed" for menu navigation.

        # Let's use the window's input controller to check for "just pressed" if available,
        # or we can subscribe to key events if we had a way.
        # The current InputController doesn't expose "just_pressed".
        # We can implement a simple "just pressed" logic here or modify InputController.

        # Actually, let's use the fact that we are in a specific scene.
        # We can check `self.window.input_controller` state if we add `key_pressed` event handling to behaviours.
        # The `SceneController` delivers events to behaviours.
        # But key presses are not events in the EventBus sense currently.

        # Let's check `self.window.input_controller` for raw key state, but we need debouncing.
        # Better approach: The GameWindow calls `input_controller.on_key_press`.
        # We can add a hook in `InputController` or `GameWindow` to forward key presses to behaviours?
        # Or we can just poll `self.window.input_controller` if we add `just_pressed` tracking there.

        # For now, let's use a simple polling with a timer for navigation to avoid super fast scrolling.
        pass

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset()

    def on_event(self, event: Any) -> None:
        # We can use the event bus for input if we wire it up, but standard input isn't on the bus.
        pass

    # We need to hook into drawing. Behaviours don't have a `draw` method called by SceneController by default.
    # SceneController calls `draw()` on layers.
    # We can use `late_update` to draw directly to the screen? No, `on_draw` clears the screen.
    # We need to register a UI element or use a UI overlay.
    # Let's register a UI element for the menu.

    def start(self) -> None:
        self.ui_element = MainMenuUI(self.window, self)
        self.window.register_ui_element(self.ui_element)
        print("[Mesh][MainMenu] Menu started")

    def destroy(self) -> None:
        if hasattr(self, "ui_element"):
            self.window.ui_controller.ui_elements.remove(self.ui_element)

    def handle_input(self, key: int) -> None:

        if self.state == "main":
            if key == optional_arcade.arcade.key.UP:
                self.selected_index = (self.selected_index - 1) % len(self.options)
            elif key == optional_arcade.arcade.key.DOWN:
                self.selected_index = (self.selected_index + 1) % len(self.options)
            elif key == optional_arcade.arcade.key.ENTER:
                self.select_option()
        elif self.state == "load_game":
            if not self.save_slots:
                if key == optional_arcade.arcade.key.ESCAPE or key == optional_arcade.arcade.key.ENTER:
                    self.state = "main"
                return

            if key == optional_arcade.arcade.key.UP:
                self.selected_save_index = (self.selected_save_index - 1) % len(self.save_slots)
            elif key == optional_arcade.arcade.key.DOWN:
                self.selected_save_index = (self.selected_save_index + 1) % len(self.save_slots)
            elif key == optional_arcade.arcade.key.ENTER:
                self.load_selected_save()
            elif key == optional_arcade.arcade.key.ESCAPE:
                self.state = "main"
        elif self.state == "settings":
            if key == optional_arcade.arcade.key.LEFT:
                self.change_volume(-1)
            elif key == optional_arcade.arcade.key.RIGHT:
                self.change_volume(1)
            elif key == optional_arcade.arcade.key.ESCAPE or key == optional_arcade.arcade.key.ENTER:
                self.state = "main"
        elif self.state == "credits":
            if key == optional_arcade.arcade.key.ESCAPE or key == optional_arcade.arcade.key.ENTER:
                self.state = "main"

    def select_option(self) -> None:
        option = self.options[self.selected_index]
        if option == "New Game":
            self.start_new_game()
        elif option == "Load Game":
            self.open_load_menu()
        elif option == "Settings":
            self.state = "settings"
        elif option == "Credits":
            self.state = "credits"
        elif option == "Quit":
            self.window.close()

    def change_volume(self, delta: int) -> None:
        self.current_volume_index = max(0, min(len(self.volume_options) - 1, self.current_volume_index + delta))
        new_vol = self.volume_options[self.current_volume_index]
        if hasattr(self.window, "audio"):
            self.window.audio.set_master_volume(new_vol)
        # Play a test sound if we had one, or just rely on music volume changing

    def _confirm_unsaved_action(self, reason: str, action: Callable[[], object]) -> bool:
        editor = getattr(self.window, "editor_controller", None)
        if editor is None or not getattr(editor, "active", False):
            return False
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker(reason, action)
            return isinstance(blocked, bool) and blocked
        return False

    def start_new_game(self) -> None:
        if self._confirm_unsaved_action("Start New Game", self._start_new_game_impl):
            return
        self._start_new_game_impl()

    def _start_new_game_impl(self) -> None:
        print("[Mesh][MainMenu] Starting new game...")
        # Reset state
        self.window.game_state_controller.replace_state({})
        # Load start scene
        start_scene = self.window.engine_config.start_scene
        self.window.request_scene_change(start_scene)

    def open_load_menu(self) -> None:
        self.save_slots = self.window.save_manager.list_saves()
        if not self.save_slots:
            print("[Mesh][MainMenu] No saves found")
            # Could show a message, but for now just stay in main or show empty list
        self.state = "load_game"
        self.selected_save_index = 0

    def load_selected_save(self) -> None:
        if not self.save_slots:
            return
        slot = self.save_slots[self.selected_save_index]
        print(f"[Mesh][MainMenu] Loading slot '{slot}'...")
        if self._confirm_unsaved_action("Load Game", lambda: self.window.save_manager.load_game(slot)):
            return
        if not self.window.save_manager.load_game(slot):
            print(f"[Mesh][MainMenu] Failed to load slot '{slot}'")


class MainMenuUI(UIElement):
    def __init__(self, window: GameWindow, behaviour: MainMenuBehaviour):
        super().__init__(window)
        self.behaviour = behaviour


    def draw(self) -> None:
        if self.behaviour.state == "main":
            self._draw_main_menu()
        elif self.behaviour.state == "load_game":
            self._draw_load_menu()
        elif self.behaviour.state == "settings":
            self._draw_settings()
        elif self.behaviour.state == "credits":
            self._draw_credits()

    def _draw_main_menu(self) -> None:

        start_y = self.window.height / 2 + 50
        optional_arcade.arcade.draw_text("MESH ENGINE", self.window.width / 2, start_y + 60, optional_arcade.arcade.color.WHITE, 40, anchor_x="center")

        for i, option in enumerate(self.behaviour.options):
            color = optional_arcade.arcade.color.YELLOW if i == self.behaviour.selected_index else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                option,
                self.window.width / 2,
                start_y - i * 40,
                color,
                20,
                anchor_x="center"
            )

    def _draw_load_menu(self) -> None:

        start_y = self.window.height / 2 + 100
        optional_arcade.arcade.draw_text("LOAD GAME", self.window.width / 2, start_y + 40, optional_arcade.arcade.color.WHITE, 30, anchor_x="center")

        if not self.behaviour.save_slots:
            optional_arcade.arcade.draw_text("No saves found", self.window.width / 2, start_y, optional_arcade.arcade.color.GRAY, 20, anchor_x="center")
            optional_arcade.arcade.draw_text(
                "Press ESC to return",
                self.window.width / 2,
                start_y - 40,
                optional_arcade.arcade.color.WHITE,
                16,
                anchor_x="center",
            )
            return

        # Show a scrolling list if needed, but simple list for now
        visible_slots = self.behaviour.save_slots # Could limit this

        for i, slot in enumerate(visible_slots):
            color = optional_arcade.arcade.color.YELLOW if i == self.behaviour.selected_save_index else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                slot,
                self.window.width / 2,
                start_y - i * 30,
                color,
                20,
                anchor_x="center"
            )

        optional_arcade.arcade.draw_text("Press ESC to return", self.window.width / 2, 50, optional_arcade.arcade.color.GRAY, 14, anchor_x="center")

    def _draw_settings(self) -> None:

        start_y = self.window.height / 2 + 50
        optional_arcade.arcade.draw_text("SETTINGS", self.window.width / 2, start_y + 60, optional_arcade.arcade.color.WHITE, 30, anchor_x="center")

        vol_percent = int(self.behaviour.volume_options[self.behaviour.current_volume_index] * 100)
        optional_arcade.arcade.draw_text(
            f"Master Volume: < {vol_percent}% >",
            self.window.width / 2,
            start_y,
            optional_arcade.arcade.color.YELLOW,
            20,
            anchor_x="center",
        )

        optional_arcade.arcade.draw_text(
            "Use LEFT/RIGHT to adjust",
            self.window.width / 2,
            start_y - 40,
            optional_arcade.arcade.color.GRAY,
            14,
            anchor_x="center",
        )
        optional_arcade.arcade.draw_text("Controls:", self.window.width / 2, start_y - 90, optional_arcade.arcade.color.WHITE, 16, anchor_x="center")
        lines = self._controls_lines()
        for idx, line in enumerate(lines):
            optional_arcade.arcade.draw_text(
                line,
                self.window.width / 2,
                start_y - 120 - idx * 18,
                optional_arcade.arcade.color.LIGHT_GRAY,
                14,
                anchor_x="center",
            )
        optional_arcade.arcade.draw_text(
            "Press ESC to return",
            self.window.width / 2,
            start_y - 140 - len(lines) * 18,
            optional_arcade.arcade.color.WHITE,
            14,
            anchor_x="center",
        )

    def _draw_credits(self) -> None:

        start_y = self.window.height / 2 + 100
        optional_arcade.arcade.draw_text("CREDITS", self.window.width / 2, start_y + 40, optional_arcade.arcade.color.WHITE, 30, anchor_x="center")

        for i, line in enumerate(self.behaviour.credits_text):
            optional_arcade.arcade.draw_text(
                line,
                self.window.width / 2,
                start_y - i * 30,
                optional_arcade.arcade.color.WHITE,
                16,
                anchor_x="center"
            )

        optional_arcade.arcade.draw_text("Press ESC to return", self.window.width / 2, 50, optional_arcade.arcade.color.GRAY, 14, anchor_x="center")

    def _controls_lines(self) -> list[str]:
        manager = getattr(self.window, "input", None)
        if manager is None:
            controller = getattr(self.window, "input_controller", None)
            manager = getattr(controller, "manager", None)
        if manager is None:
            return []
        cfg = getattr(self.window, "engine_config", None)
        cfg_bindings = getattr(cfg, "input_bindings", None) if cfg is not None else None
        actions = sorted(known_actions(manager, cfg_bindings))
        bindings = snapshot_bindings(manager)
        lines: list[str] = []
        for action in actions:
            names = bindings.get(action, [])
            label = ", ".join(names) if names else "<unbound>"
            lines.append(f"{action}: {label}")
        return lines

    def on_key_press(self, key: int, modifiers: int) -> bool:
        self.behaviour.handle_input(key)
        return True
