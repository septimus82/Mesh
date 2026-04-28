"""UI overlay primitives for Mesh Engine."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, TypeAlias
import engine.optional_arcade as optional_arcade

from .animation_state import get_animation_state_snapshot
from .inventory import Inventory, load_item_database
from .tooling_runtime.state_dump import dump_state

logger = logging.getLogger(__name__)

# Allow importing shared widget primitives via ``engine.ui.widgets`` while
# keeping this legacy module path intact.
__path__ = [str(Path(__file__).with_name("ui"))]



if TYPE_CHECKING:  # pragma: no cover
    from arcade import Sprite as ArcadeSprite

    # Fallback for headless environments to verify types
    Sprite: TypeAlias = ArcadeSprite

    from .behaviours.health import Health
    from .game import GameWindow
else:
    Sprite: TypeAlias = Any


def _sprite_under_cursor(window: "GameWindow") -> "Sprite | None":
    if not getattr(window, "show_debug", False):
        return None

    world_x, world_y = window.screen_to_world(window._mouse_x, window._mouse_y)

    candidates: list["Sprite"] = []
    layers = getattr(window.scene_controller, "layers", {})
    for layer in layers.values():
        hits = optional_arcade.arcade.get_sprites_at_point((world_x, world_y), layer)
        if hits:
            candidates.extend(hits)

    if not candidates:
        return None
    return candidates[-1]


from .ui_overlays.common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
    _sprite_under_cursor,
)
from .ui_overlays.debug import (
    AnimationStateOverlay,
    DevConsole,
    EncounterDebugOverlay,
    EntityInspector,
    HD2DPreviewIndicatorOverlay,
    HotReloadOverlay,
    PaletteOverlay,
    PhysicsBroadphaseOverlay,
    SceneDirtyOverlay,
    SceneInspectorOverlay,
    format_encounter_debug_text,
    format_physics_broadphase_lines,
    format_scene_dirty_overlay_lines,
    format_scene_inspector_text,
)
from .ui_overlays.hd2d_settings_panel_overlay import (
    Hd2dSettingsPanelOverlay,
)
from .ui_overlays.editors import (
    CaptureOverlay,
    EntityPaintOverlay,
    EntitySelectOverlay,
    TilePaintOverlay,
    format_capture_overlay_lines,
    format_entity_paint_overlay_lines,
    format_entity_select_overlay_lines,
    format_tile_paint_overlay_lines,
)

from .ui_overlays.hud import (
    DEMO_INTERIOR_HINT_SECONDS,
    DEMO_INTERIOR_HINT_TOAST,
    HealthBar,
    InteractPromptOverlay,
    ObjectiveTrackerOverlay,
    PlayerHUD,
    QuestLog,
    ToastQueue,
    begin_boss_gold_reward_tracking,
    compute_objective_tracker_lines,
    maybe_auto_open_quest_log,
    maybe_enqueue_boss_defeat_toast,
    maybe_enqueue_boss_spawn_toast,
    maybe_enqueue_controls_hint_toast,
    maybe_enqueue_demo_interior_hint,
    maybe_enqueue_exit_unlocked_toast,
    maybe_enqueue_lighting_toggle_tip,
    maybe_enqueue_miniboss_defeat_toast,
    maybe_enqueue_miniboss_spawn_toast,
    maybe_enqueue_preset_mode_toast,
    maybe_enqueue_quest_progress_toast,
    maybe_enqueue_shadowmask_enabled_toast,
    maybe_finish_boss_gold_reward_toast,
)

from .ui_overlays.menus import (
    DEMO_COMPLETE_ENDCAP_SECONDS,
    CharacterPanel,
    DemoCompleteOverlay,
    DialogueBox,
    GameOverScreen,
    HelpOverlay,
    MainMenuOverlay,
    PauseMenu,
    SettingsOverlay,
    ShopPanel,
    maybe_trigger_demo_complete_endcap,
)

from .ui_overlays.command_palette import (
    CommandPaletteOverlay,
    format_command_palette_overlay_lines,
)


from .ui_contract import (
    PERSISTENT_UI_ATTRS,
    REQUIRED_PERSISTENT_UI_ATTRS,
    missing_persistent_ui_attrs,
)


from .ui_overlays.inspector import (
    INSPECTOR_MAX_LINE_CHARS,
    INSPECTOR_MAX_LINES,
    INSPECTOR_MAX_LIST_ITEMS,
    InspectorOverlay,
    build_inspector_lines,
)


from .ui_overlays.common import load_config_json
from .ui_overlays.dev_browser import (
    DEV_BROWSER_MAX_FILTER_CHARS,
    DEV_BROWSER_MAX_ITEMS,
    DEV_BROWSER_NO_RESULTS_MESSAGE,
    DevBrowserOverlay,
    build_dev_browser_scene_source,
    build_dev_browser_world_source,
    filter_dev_browser_items,
)

from .ui_overlays.golden_slice import (
    GOLDEN_SLICE_DEMO_HUD_MAX_CHARS,
    GoldenSliceDemoHUDStripOverlay,
    GoldenSliceVariantPickerOverlay,
    build_act1_demo_hud_status_line,
    build_golden_slice_demo_hud_status_line,
    build_golden_slice_variant_picker_presets,
    build_golden_slice_variant_picker_presets_from_file,
    build_golden_slice_variant_picker_source,
    is_act1_demo_context,
    is_golden_slice_demo_context,
)

class InventoryOverlay(UIElement):
    """Text-only overlay that lists current inventory contents."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self.background_color = getattr(optional_arcade.arcade.color, "BLACK", (0, 0, 0))
        self.text_color = getattr(optional_arcade.arcade.color, "WHITE", (255, 255, 255))
        self.selected_index = 0
        self._text = optional_arcade.arcade.Text(
            text="",
            x=20,
            y=window.height - 20,
            color=self.text_color,
            anchor_x="left",
            anchor_y="top",
            font_size=14,
        )

    def toggle(self) -> bool:
        self.visible = not self.visible
        if self.visible:
            self.selected_index = 0
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    def close(self) -> None:
        self.visible = False

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        self._text.y = self.window.height - 20

    def on_key_press(self, key: int, modifiers: int) -> bool:
        if not self.visible:
            return False

        game_state = self.window.game_state
        inventory_state = getattr(game_state, "values", {}).get("inventory", {})
        inventory = Inventory(inventory_state)
        items = list(inventory.list_items())

        if not items:
            return False

        if key == optional_arcade.arcade.key.UP or key == optional_arcade.arcade.key.W:
            self.selected_index = (self.selected_index - 1) % len(items)
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_hover.wav")
            return True
        elif key == optional_arcade.arcade.key.DOWN or key == optional_arcade.arcade.key.S:
            self.selected_index = (self.selected_index + 1) % len(items)
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_hover.wav")
            return True
        elif key == optional_arcade.arcade.key.ENTER or key == optional_arcade.arcade.key.SPACE:
            self._use_selected_item(items)
            return True
        elif key == optional_arcade.arcade.key.E:
            self._equip_selected_item(items)
            return True

        return False # Don't block other input? Or should we?
        # If inventory is open, we probably want to block movement.
        # But UIController checks return value. If True, it blocks.
        # So we should return True if we handled it or if we want to block.
        # Let's return True for navigation keys, False for others (like I to close).

    def _use_selected_item(self, items: list[tuple[str, int]]) -> None:
        if not items or self.selected_index >= len(items):
            return

        item_id, amount = items[self.selected_index]
        db = load_item_database()
        definition = db.get(item_id)

        if not definition:
            return

        # Check effects
        effects = definition.effects
        used = False

        if "heal" in effects:
            # Find player
            player = self.window.find_sprite_by_name("Player")
            if player:
                # Find health behaviour
                behaviours = getattr(player, "mesh_behaviours_runtime", [])
                for b in behaviours:
                    if hasattr(b, "heal"):
                        heal_amount = float(effects["heal"])
                        b.heal(heal_amount)
                        used = True
                        if hasattr(self.window, "audio"):
                            self.window.audio.play_sound("assets/sounds/ui_click.wav") # Should be potion sound
                        break

        if used:
            # Remove 1 from inventory
            game_state = self.window.game_state
            inventory_state = getattr(game_state, "values", {}).get("inventory", {})
            inventory = Inventory(inventory_state)
            inventory.remove_item(item_id, 1)

            # Adjust selection if list shrinks
            new_items = list(inventory.list_items())
            if self.selected_index >= len(new_items):
                self.selected_index = max(0, len(new_items) - 1)

    def _equip_selected_item(self, items: list[tuple[str, int]]) -> None:
        """Attempt to equip the selected item if it's equippable."""
        if not items or self.selected_index >= len(items):
            return

        item_id, _ = items[self.selected_index]
        db = load_item_database()
        definition = db.get(item_id)

        if not definition:
            return

        # Check if it's equippable (has "equipment" tag)
        if "equipment" not in definition.tags:
            # Show toast that item can't be equipped
            hud = getattr(self.window, "player_hud", None)
            enqueue = getattr(hud, "enqueue_toast", None) if hud else None
            if callable(enqueue):
                enqueue(f"{definition.name} cannot be equipped", seconds=2.0)
            return

        # Use the game state controller to equip
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return

        result = gs.equip_item(item_id)
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud else None

        if result.get("ok"):
            slot = result.get("slot", "?")
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_click.wav")
            if callable(enqueue):
                enqueue(f"Equipped {definition.name} ({slot})", seconds=2.0)
        else:
            reason = result.get("reason", "unknown")
            if callable(enqueue):
                enqueue(f"Cannot equip: {reason}", seconds=2.0)

    def draw(self) -> None:  # noqa: D401
        """Draw overlay when visible."""
        if not self.visible:
            return
        game_state = self.window.game_state
        inventory_state = getattr(game_state, "values", {}).get("inventory", {})
        inventory = Inventory(inventory_state)
        db = load_item_database()

        # Get equipped items to mark them
        gs = getattr(self.window, "game_state_controller", None)
        equipped = gs.get_equipment() if gs else {}
        equipped_ids = set(v for v in equipped.values() if v)

        items = list(inventory.list_items())
        lines = ["Inventory", "Enter: Use  E: Equip"]

        if not items:
            lines.append("<empty>")
        else:
            for i, (item_id, amount) in enumerate(items):
                definition = db.get(item_id)
                label = definition.name if definition else item_id
                prefix = "➤ " if i == self.selected_index else "  "
                suffix = " [E]" if item_id in equipped_ids else ""
                lines.append(f"{prefix}{label} x{amount}{suffix}")

        text = "\n".join(lines)
        self._text.text = text
        padding = 12
        width = max(280, self._text.content_width + padding * 2)
        height = self._text.content_height + padding * 2
        _draw_rectangle_filled(width / 2 + 10, self.window.height - height / 2 - 10, width, height, (0, 0, 0, 180))
        self._text.y = self.window.height - 20
        self._text.draw()



