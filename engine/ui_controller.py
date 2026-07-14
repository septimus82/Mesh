from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from .logging_tools import get_logger
from .ui import (
    AnimationStateOverlay,
    CharacterPanel,
    DevConsole,
    DialogueBox,
    EntityInspector,
    HealthBar,
    InventoryOverlay,
    QuestLog,
    ShopPanel,
    UIElement,
)

if TYPE_CHECKING:
    from arcade import Sprite

    from .game import GameWindow

logger = get_logger(__name__)


def creator_mode_hiding_editor_chrome(window: "GameWindow") -> bool:
    """True when Creator Mode is active and Advanced editor chrome should not draw."""
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return False
    creator = getattr(editor, "creator_mode", None)
    return bool(getattr(creator, "active", False))


class UIController:
    def __init__(self, window: GameWindow):
        self.window = window
        self.ui_elements: list[UIElement] = []
        self.dialogue_box: DialogueBox | None = None
        self.quest_log: QuestLog | None = None
        self.inventory_overlay: InventoryOverlay | None = None
        self.shop_panel: ShopPanel | None = None
        self.character_panel: CharacterPanel | None = None

    def register_ui_element(self, element: UIElement, *, editor_chrome: bool | None = None) -> None:
        if editor_chrome is not None:
            element.editor_chrome = bool(editor_chrome)
        self.ui_elements.append(element)

    def clear_ui_elements(self) -> None:
        self.ui_elements.clear()
        self.dialogue_box = None
        self.quest_log = None
        self.inventory_overlay = None
        self.shop_panel = None
        self.character_panel = None

    def reset_transient_state(self) -> None:
        """Close all blocking UI elements and reset transient state."""
        if self.dialogue_box:
            self.dialogue_box.close()
        if self.quest_log:
            self.quest_log.close()
        if self.inventory_overlay:
            self.inventory_overlay.close()
        if self.shop_panel:
            self.shop_panel.close()
        if self.character_panel:
            self.character_panel.close()

        # Handle PauseMenu via window if available
        pause_menu = getattr(self.window, "pause_menu", None)
        if pause_menu:
            pause_menu.visible = False
        self.window.paused = False

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        """Notify UI elements about window size changes."""
        for element in list(self.ui_elements):
            handler = getattr(element, "on_resize", None)
            if callable(handler):
                try:
                    handler(width, height)
                except Exception as exc:  # noqa: BLE001  # REASON: one misbehaving UI element should not prevent resize notifications from reaching the rest of the overlay stack
                    logger.warning("on_resize failed for %s: %r", element.__class__.__name__, exc)

    def update(self, dt: float) -> None:
        for element in list(self.ui_elements):
            element.update(dt)

    def draw(self) -> None:
        hide_editor_chrome = creator_mode_hiding_editor_chrome(self.window)
        for element in self.ui_elements:
            if hide_editor_chrome and getattr(element, "editor_chrome", True):
                continue
            element.draw()

    def rebuild_for_scene(self) -> None:
        self.clear_ui_elements()
        logger.info("Rebuilding UI for scene")
        self.register_ui_element(EntityInspector(self.window), editor_chrome=False)
        self.register_ui_element(AnimationStateOverlay(self.window), editor_chrome=False)
        self.register_ui_element(DevConsole(self.window), editor_chrome=False)
        self.inventory_overlay = InventoryOverlay(self.window)
        self.register_ui_element(self.inventory_overlay, editor_chrome=False)
        self.dialogue_box = DialogueBox(self.window)
        self.register_ui_element(self.dialogue_box, editor_chrome=False)
        self.quest_log = QuestLog(self.window)
        self.register_ui_element(self.quest_log, editor_chrome=False)
        self.shop_panel = ShopPanel(self.window)
        self.register_ui_element(self.shop_panel, editor_chrome=False)
        self.character_panel = CharacterPanel(self.window)
        self.register_ui_element(self.character_panel, editor_chrome=False)

    def register_health_bar(self, sprite: Sprite) -> None:
        logger.info(
            "Registering HealthBar for %s",
            getattr(sprite, "mesh_name", "<unnamed>"),
        )
        self.register_ui_element(HealthBar(self.window, sprite), editor_chrome=False)

    @property
    def input_blocked(self) -> bool:
        """Check if any active UI element is blocking gameplay input."""
        return any(element.blocks_input for element in self.ui_elements)

    # --- Dialogue ---
    def show_dialogue(self, entries: Sequence[dict[str, str]], *, owner: str) -> bool:
        box = self.dialogue_box
        if box is None:
            logger.warning("DialogueBox unavailable")
            return False
        return box.play(entries, owner=owner)

    def advance_dialogue(self, *, owner: str | None = None) -> bool:
        box = self.dialogue_box
        if box is None:
            return False
        return box.advance(owner=owner)

    def close_dialogue(self, *, owner: str | None = None) -> None:
        box = self.dialogue_box
        if box is None:
            return
        box.clear(owner=owner)

    def is_dialogue_active(self, *, owner: str | None = None) -> bool:
        box = self.dialogue_box
        if box is None:
            return False
        if owner is not None:
            return box.is_active_for(owner)
        return box.is_active()

    def dialogue_blocks_input(self) -> bool:
        return self.input_blocked

    # --- Quest Log ---
    def is_quest_log_visible(self) -> bool:
        log = self.quest_log
        return bool(log and log.is_visible())

    def quest_log_blocks_input(self) -> bool:
        return self.is_quest_log_visible()

    def shop_blocks_input(self) -> bool:
        panel = self.shop_panel
        return bool(panel and getattr(panel, "visible", False))

    def toggle_quest_log(self) -> bool:
        log = self.quest_log
        if log is None:
            return False
        state = log.toggle()
        return state

    def hide_quest_log(self) -> None:
        log = self.quest_log
        if log is not None:
            log.set_visible(False)

    # --- Character Panel ---
    def toggle_character_panel(self) -> bool:
        panel = self.character_panel
        if panel is None:
            return False
        return panel.toggle()

    def hide_character_panel(self) -> None:
        panel = self.character_panel
        if panel is not None:
            panel.set_visible(False)

    def is_character_panel_visible(self) -> bool:
        panel = self.character_panel
        return bool(panel and panel.visible)

    def character_panel_blocks_input(self) -> bool:
        return self.is_character_panel_visible()

    # --- Inventory ---
    def toggle_inventory_overlay(self) -> bool:
        overlay = self.inventory_overlay
        if overlay is None:
            return False
        state = overlay.toggle()
        return state

    # --- Shop ---
    def open_shop(self, vendor, items: list[dict[str, Any]]) -> None:
        panel = self.shop_panel
        if panel is not None:
            panel.open(vendor, items)

    def close_shop(self) -> None:
        panel = self.shop_panel
        if panel is not None:
            panel.close()

    def hide_inventory_overlay(self) -> None:
        overlay = self.inventory_overlay
        if overlay is not None:
            overlay.set_visible(False)

    def is_inventory_overlay_visible(self) -> bool:
        overlay = self.inventory_overlay
        return bool(overlay and overlay.visible)

    def on_key_press(self, key: int, modifiers: int) -> bool:
        """Dispatch key press to UI elements. Returns True if handled."""
        for element in reversed(self.ui_elements):
            if hasattr(element, "on_key_press"):
                if element.on_key_press(key, modifiers):
                    return True
        return False

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:
        """Dispatch mouse press to UI elements. Returns True if handled."""
        for element in reversed(self.ui_elements):
            handler = getattr(element, "on_mouse_press", None)
            if callable(handler) and handler(x, y, button, modifiers):
                return True
        return False

    def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> bool:
        """Dispatch mouse scroll to UI elements. Returns True if handled."""
        for element in reversed(self.ui_elements):
            handler = getattr(element, "on_mouse_scroll", None)
            if callable(handler) and handler(x, y, scroll_x, scroll_y):
                return True
        return False
