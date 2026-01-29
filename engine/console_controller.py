"""Console controller for Mesh Engine."""

from __future__ import annotations

import difflib
import json
from typing import TYPE_CHECKING, Any, Sequence
import engine.optional_arcade as optional_arcade

from .console_runtime import commands as console_commands
from .console_runtime import history as console_history
from .console_runtime import render as console_render
from . import json_io
from .logging_tools import get_logger
from .ai_ops import AIOps, load_job
from .animation_state import get_animation_state_snapshot, request_animation_state
from .behaviours import (
    get_behaviour_info,
    get_behaviour_param_defs,
    reload_behaviour_modules,
)
from .input_bindings import (
    key_code_to_name,
    key_name_to_code,
    known_actions,
    snapshot_bindings,
)
from .inventory import get_or_create_inventory, load_item_database

if TYPE_CHECKING:
    from .game import GameWindow

logger = get_logger(__name__)

class ConsoleController:
    """Handles dev console state, input, and command execution."""

    def __init__(self, window: GameWindow) -> None:
        self.window = window
        self.active: bool = False
        self.lines: list[str] = []
        self.max_lines: int = 300
        self.scroll_offset: int = 0
        self.visible_line_count: int = 8
        self.history: list[str] = []
        self.history_index: int | None = None
        self._hotkeys_banner_logged: bool = False

    def toggle(self) -> None:
        self.active = not self.active
        
        # Fallback for input manager access
        input_mgr = getattr(self.window, "input", None)
        if input_mgr is None:
            ctrl = getattr(self.window, "input_controller", None)
            input_mgr = getattr(ctrl, "manager", None)
            
        if input_mgr is None:
            logger.error("[Mesh][Console] Cannot toggle: InputManager not found")
            self.active = False
            return

        if self.active:
            input_mgr.start_text_capture()
            self.snap_to_bottom()
            self.history_reset_cursor()
            self.log_hotkeys_banner()
        else:
            input_mgr.stop_text_capture()
            self.history_reset_cursor()
        logger.info("[Mesh][Debug] console_active = %s", self.active)

    def process_key(self, key: int, modifiers: int) -> bool:
        """Process a key press if the console is active. Returns True if handled."""
        if not self.active:
            return False

        # Fallback for input manager access
        input_mgr = getattr(self.window, "input", None)
        if input_mgr is None:
            ctrl = getattr(self.window, "input_controller", None)
            input_mgr = getattr(ctrl, "manager", None)
            
        if input_mgr is None:
            return False

        # self.log(f"DEBUG: Key pressed: {key}")

        if key == optional_arcade.arcade.key.UP:
            previous = self.history_previous()
            if previous is not None:
                input_mgr.set_text_buffer(previous)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            nxt = self.history_next()
            if nxt is not None:
                input_mgr.set_text_buffer(nxt)
            return True
        
        # Check for various Enter keys (Standard, Numpad, Linefeed)
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN, getattr(optional_arcade.arcade.key, "NUM_ENTER", 65421), 10, 13):
            command = input_mgr.stop_text_capture()
            self.log(f"DEBUG: Enter pressed (key={key}). Command: '{command}'")
            self.execute_command(command)
            self.scroll_end()
            input_mgr.start_text_capture()
            return True
        if key in (optional_arcade.arcade.key.BACKSPACE, 8, 127):
            self.log(f"DEBUG: Backspace pressed (key={key})")
            input_mgr.backspace()
            return True
        if key == optional_arcade.arcade.key.PAGEUP:
            self.scroll_page(1)
            return True
        if key == optional_arcade.arcade.key.PAGEDOWN:
            self.scroll_page(-1)
            return True
        if key == optional_arcade.arcade.key.HOME:
            self.scroll_home()
            return True
        if key == optional_arcade.arcade.key.END:
            self.scroll_end()
            return True

        # self.log(f"DEBUG: Unhandled key: {key}")
        return False

    def log(self, message: str) -> None:
        logger.info("[Mesh][Console] %s", message)
        at_bottom = self.scroll_offset == 0
        self.lines.append(str(message))

        _, self.scroll_offset = console_render.trim_lines_and_adjust_scroll(
            self.lines,
            max_lines=self.max_lines,
            scroll_offset=self.scroll_offset,
        )

        _, max_offset = self._visible_metrics()
        self.scroll_offset = min(self.scroll_offset, max_offset)
        if at_bottom:
            self.snap_to_bottom()

    def _visible_metrics(self) -> tuple[int, int]:
        return console_render.visible_metrics(len(self.lines), self.visible_line_count)

    def history_reset_cursor(self) -> None:
        self.history_index = console_history.history_reset_cursor()

    def _history_push(self, command: str) -> None:
        history_cap = self.max_lines if self.max_lines > 0 else 300
        self.history_index = console_history.history_push(
            self.history,
            command,
            cap=history_cap,
            history_index=self.history_index,
        )

    def history_previous(self) -> str | None:
        value, idx = console_history.history_previous(self.history, self.history_index)
        self.history_index = idx
        return value

    def history_next(self) -> str | None:
        value, idx = console_history.history_next(self.history, self.history_index)
        self.history_index = idx
        return value

    def snap_to_bottom(self) -> None:
        self.scroll_offset = 0

    def scroll_page(self, direction: int) -> None:
        if not self.lines:
            return
        step = max(1, self.visible_line_count)
        _, max_offset = self._visible_metrics()
        if direction > 0:
            self.scroll_offset = min(self.scroll_offset + step, max_offset)
        else:
            self.scroll_offset = max(self.scroll_offset - step, 0)

    def scroll_home(self) -> None:
        _, max_offset = self._visible_metrics()
        self.scroll_offset = max_offset

    def scroll_end(self) -> None:
        self.snap_to_bottom()

    def _trimmed(self, removed: int) -> None:
        if removed <= 0:
            return
        if self.scroll_offset <= removed:
            self.scroll_offset = 0
        else:
            self.scroll_offset -= removed

    def get_visible_lines(self) -> list[str]:
        visible_lines, scroll_offset = console_render.get_visible_lines(
            self.lines,
            visible_line_count=self.visible_line_count,
            scroll_offset=self.scroll_offset,
        )
        self.scroll_offset = scroll_offset
        return visible_lines

    def get_scroll_state(self) -> dict[str, int]:
        return console_render.get_scroll_state(
            self.lines,
            visible_line_count=self.visible_line_count,
            scroll_offset=self.scroll_offset,
        )

    def execute_command(self, command: str) -> None:
        parsed = console_commands.parse_command_line(command or "")
        if parsed is None:
            return

        self._history_push(parsed.raw)
        self.log(parsed.raw)
        handled = console_commands.dispatch_command(self, parsed.cmd, parsed.args)
        if not handled:
            self.log(f"Unknown command: {parsed.cmd}")

    def help_sections(self) -> list[tuple[str, list[tuple[str, str]]]]:
        return [
            (
                "meta",
                [
                    ("help / ?", "Show this help"),
                    ("save <slot> [--compact]", "Save game state to a slot"),
                    ("load <slot>", "Load game state from a slot"),
                    ("clear", "Clear console scrollback"),
                    ("pause", "Toggle paused state"),
                    ("strict_on", "Enable strict exception mode (crash on error)"),
                    ("strict_off", "Disable strict exception mode (log errors)"),
                    ("selftest", "Run engine self-checks (behaviours/scenes/worlds)"),
                    ("flag [get|set|toggle]", "Inspect or mutate global flags"),
                    ("counter [get|set|add]", "Inspect or mutate global counters"),
                    ("encounter [reroll|overlay]", "Debug encounter system"),
                    ("xp [get|add|set]", "Inspect or mutate player xp/level"),
                    ("stats", "Show derived player stats"),
                    ("gstate", "Show chapter, main quest, and playtime"),
                    ("quest [list|start|complete]", "Inspect or manipulate quest states"),
                    ("cutscene <id>", "Start a cutscene by id"),
                    ("world [scenes|neighbors]", "Inspect loaded world metadata"),
                    ("ai_bundle [dir]", "Build full AI bundle (index, context, docs)"),
                    ("ai_job <path>", "Apply an AI job JSON and reload scene"),
                    ("daynight [on|off]", "Toggle day/night cycle"),
                    ("day_night [on|off]", "Alias: toggle day/night cycle"),
                    ("time_of_day", "Show current time-of-day hour"),
                    ("set_time_of_day <hour>", "Set time-of-day hour"),
                    ("lighting [on|off]", "Show or toggle lighting"),
                    ("lighting_limit [static|dynamic] [value|none]", "View or set lighting caps"),
                ],
            ),
            (
                "scenes",
                [
                    ("reload", "Reload the current scene"),
                    ("reload_scene [path]", "Reload the current scene or a specific path"),
                    ("scene <path>", "Load a different scene JSON"),
                    ("scene save [path]", "Save current state to JSON (default: overwrite)"),
                    ("scene dump [path]", "Dump raw scene state to JSON (debug)"),
                ],
            ),
            (
                "behaviours",
                [
                    ("behaviours", "List registered behaviours"),
                    ("behaviour <name>", "Show info for a behaviour"),
                    ("beh list [entity]", "List runtime behaviour parameters"),
                    ("beh get <ref> <beh> <param>", "Inspect a behaviour parameter"),
                    (
                        "beh set <ref> <beh> <param> <value>",
                        "Update a behaviour parameter at runtime",
                    ),
                    (
                        "reload_behaviours",
                        "Reload behaviour modules (run reload_scene afterwards)",
                    ),
                ],
            ),
            (
                "entities",
                [
                    ("entity", "List all entities with indices"),
                    ("entity <i|name>", "Show details for entity by index or name"),
                    ("entity set <ref> ...", "Modify entity position, tag, or scale"),
                    ("entity beh list <ref>", "List behaviours + config for an entity"),
                    (
                        "entity beh set <ref> <beh> <field> <value>",
                        "Set per-entity behaviour config",
                    ),
                    (
                        "entity beh reload <ref>",
                        "Rebuild behaviours for an entity",
                    ),
                    ("spawn <sprite> <x> <y>", "Spawn a new entity at runtime"),
                    ("spawn_like <ref> <x> <y>", "Clone an existing entity at new coords"),
                ],
            ),
            (
                "collision",
                [
                    ("rules", "List collision rules"),
                ],
            ),
            (
                "assets",
                [
                    ("assets", "Show texture cache info"),
                    ("assets clear", "Clear texture cache"),
                ],
            ),
            (
                "prefabs",
                [
                    ("prefab_source [prefab_id] [--json]", "Show prefab source (hovered/inspected if omitted)"),
                    ("prefab_source_chain <prefab_id> [--json]", "Show override chain for prefab id"),
                ],
            ),
            (
                "audio",
                [
                    ("sound <path>", "Play a one-shot sound"),
                    ("music <path>", "Play music (looped)"),
                    ("stopmusic", "Stop current music"),
                ],
            ),
            (
                "config",
                [
                    ("config", "Print current config values"),
                    ("bindings", "List current input bindings"),
                    ("bind <action> <key>", "Add a key binding"),
                    ("unbind <action> [key]", "Remove one or all keys for an action"),
                    ("saveconfig", "Save config to disk"),
                    ("set volume <0..1>", ""),
                    ("set master <0..1>", ""),
                    ("set music <0..1>", ""),
                    ("set sfx <0..1>", ""),
                    ("set fullscreen <on|off>", ""),
                    ("set vsync <on|off>", ""),
                    ("set show_fps <on|off>", ""),
                    ("set debug_on_start <on|off>", ""),
                ],
            ),
            (
                "inventory",
                [
                    ("inventory [list]", "Show current inventory contents"),
                    ("inventory add <id> [amount]", "Grant an item using items.json ids"),
                    ("inventory remove <id> [amount]", "Remove an item from the shared inventory"),
                    ("inventory clear", "Empty the shared inventory bucket"),
                    ("inventory show|hide|toggle", "Control the inventory overlay visibility"),
                ],
            ),
            (
                "camera",
                [
                    ("camera", "Inspect camera state or subcommands"),
                    ("camera zoom <value>", "Set the zoom target immediately"),
                    (
                        "camera shake <duration> <amplitude> [freq] [falloff]",
                        "Trigger a temporary camera shake",
                    ),
                    ("camera stopshake", "Clear any active camera shake"),
                    ("camera areas", "List configured camera areas"),
                ],
            ),
            (
                "hotkeys",
                [
                    ("F1 / ` / Insert", "Toggle console"),
                    ("Ctrl+F1", "Toggle command palette (debug)"),
                    ("F2", "Toggle capture mode (debug)"),
                    ("H", "Toggle help overlay"),
                    ("F3", "Toggle debug overlay"),
                    ("F4", "Toggle editor mode"),
                    ("F5", "Quick save (debug)"),
                    ("F6", "Quick load (debug)"),
                    ("F8", "Toggle encounter debug overlay"),
                    ("F9", "Toggle paused state"),
                    ("F10", "Toggle scene inspector overlay"),
                    ("F11", "Toggle tile paint mode (debug)"),
                    ("F12", "Toggle selection lock from hover (debug)"),
                    ("Esc", "Toggle settings overlay"),
                    ("Q", "Toggle quest log"),
                    ("I", "Toggle inventory overlay"),
                    ("C", "Toggle character panel"),
                    ("V", "Toggle variant picker"),
                    ("PgUp/PgDn/Home/End", "Scroll console"),
                    ("Up/Down", "Navigate console history"),
                ],
            ),
        ]

    def _help(self) -> None:
        """Print a short help reference for the dev console."""
        help_sections = self.help_sections()
        self.log("Mesh Console Help:")
        for idx, (section, commands) in enumerate(help_sections):
            self.log(f"  {section}:")
            for command, description in commands:
                if description:
                    padded_command = command.ljust(20)
                    self.log(f"    - {padded_command} {description}")
                else:
                    self.log(f"    - {command}")
            if idx < len(help_sections) - 1:
                self.log("")

    def log_hotkeys_banner(self) -> None:
        if self._hotkeys_banner_logged:
            return

        hotkeys: list[tuple[str, str]] = []
        for section, commands in self.help_sections():
            if section == "hotkeys":
                hotkeys = commands
                break

        if not hotkeys:
            return

        summary_parts: list[str] = []
        for command, description in hotkeys:
            if description:
                summary_parts.append(f"{command} - {description}")
            else:
                summary_parts.append(command)

        if not summary_parts:
            return

        banner = "  |  ".join(summary_parts)
        self.log(f"hotkeys: {banner}")
        self._hotkeys_banner_logged = True


    def _camera_command(self, args: list[str]) -> None:
        if not args:
            center_x, center_y = self.window.get_camera_center()
            zoom_state = self.window.camera_controller.zoom_state
            area = self.window.camera_controller.active_area
            shake = self.window.camera_controller.shake_state
            self.log(
                f"Camera center=({center_x:.1f}, {center_y:.1f}) zoom={zoom_state.current:.2f}->{zoom_state.target:.2f}"
            )
            if area:
                self.log(
                    f"  area: {area.name} ({area.x},{area.y},{area.width}x{area.height}) priority={area.priority}"
                )
            else:
                self.log("  area: <default>")
            if shake.duration > 0:
                remaining = max(0.0, shake.duration - shake.timer)
                self.log(
                    f"  shake: amp={shake.amplitude:.2f} freq={shake.frequency:.1f} remaining={remaining:.2f}s"
                )
            else:
                self.log("  shake: <inactive>")
            return

        sub = args[0].lower()
        if sub == "zoom":
            if len(args) < 2:
                self.log("Usage: camera zoom <value>")
                return
            zoom_value = self._parse_float(args[1], "zoom")
            if zoom_value is None:
                return
            self.window.set_camera_zoom_target(zoom_value)
            self.log(f"Camera zoom target set to {self.window.camera_controller.zoom_state.target:.2f}")
            return

        if sub == "shake":
            if len(args) < 3:
                self.log("Usage: camera shake <duration> <amplitude> [frequency] [falloff]")
                return
            duration = self._parse_float(args[1], "duration")
            amplitude = self._parse_float(args[2], "amplitude")
            frequency = self._parse_float(args[3], "frequency") if len(args) >= 4 else 18.0
            falloff = self._parse_float(args[4], "falloff") if len(args) >= 5 else 1.0
            if None in {duration, amplitude, frequency, falloff}:
                return
            self.window.start_camera_shake(
                duration=float(duration),
                amplitude=float(amplitude),
                frequency=float(frequency),
                falloff=float(falloff),
            )
            self.log("Camera shake started")
            return

        if sub == "stopshake":
            self.window.stop_camera_shake()
            self.log("Camera shake cleared")
            return

        if sub == "areas":
            if not self.window.camera_controller.areas:
                self.log("No camera areas configured")
                return
            self.log("Camera areas:")
            for area in self.window.camera_controller.areas:
                indicator = "*" if area is self.window.camera_controller.active_area else "-"
                self.log(
                    f"  {indicator} {area.name} [{area.x},{area.y},{area.width}x{area.height}] priority={area.priority} zoom={area.zoom or '<inherit>'}"
                )
            return

        self.log("Unknown camera command. Usage: camera [zoom|shake|stopshake|areas]")

    def _inventory_command(self, args: list[str]) -> None:
        inventory = get_or_create_inventory(self.window.game_state.values)
        subcommand = args[0].lower() if args else "list"

        if subcommand in {"list", "ls"}:
            self._inventory_list(inventory)
            return

        if subcommand in {"add", "give"}:
            if len(args) < 2:
                self.log("Usage: inventory add <item_id> [amount]")
                return
            item_id = args[1]
            amount = 1
            if len(args) >= 3:
                parsed = self._inventory_parse_amount(args[2])
                if parsed is None:
                    return
                amount = parsed
            self._inventory_add(inventory, item_id, amount)
            return

        if subcommand in {"remove", "rm", "take"}:
            if len(args) < 2:
                self.log("Usage: inventory remove <item_id> [amount]")
                return
            item_id = args[1]
            amount = 1
            if len(args) >= 3:
                parsed = self._inventory_parse_amount(args[2])
                if parsed is None:
                    return
                amount = parsed
            self._inventory_remove(inventory, item_id, amount)
            return

        if subcommand == "clear":
            inventory.clear()
            self.log("Inventory cleared")
            return

        if subcommand == "show":
            overlay = self.window.ui_controller.inventory_overlay
            if overlay is None:
                self.log("Inventory overlay unavailable")
                return
            overlay.set_visible(True)
            self.log("Inventory overlay shown")
            return

        if subcommand == "hide":
            self.window.hide_inventory_overlay()
            self.log("Inventory overlay hidden")
            return

        if subcommand == "toggle":
            visible = self.window.toggle_inventory_overlay()
            self.log(f"Inventory overlay {'shown' if visible else 'hidden'}")
            return

        self.log(
            "Usage: inventory [list|add|remove|clear|show|hide|toggle]",
        )

    def _equip_command(self, args: list[str]) -> None:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            self.log("[Equip] No game state controller.")
            return
        if not args:
            self.log("Usage: equip <item_id> [slot]")
            return
        item_id = args[0]
        slot = args[1] if len(args) > 1 else None
        result = gs.equip_item(item_id, slot=slot)
        if result.get("ok"):
            self.log(f"[Equip] Equipped {result.get('item')} to {result.get('slot')}")
        else:
            self.log(f"[Equip] Failed: {result.get('reason', 'unknown')}")

    def _unequip_command(self, args: list[str]) -> None:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            self.log("[Unequip] No game state controller.")
            return
        if not args:
            self.log("Usage: unequip <weapon|armor|accessory>")
            return
        slot = args[0]
        result = gs.unequip(slot)
        if result.get("ok"):
            self.log(f"[Unequip] Cleared {result.get('slot')}")
        else:
            self.log(f"[Unequip] Failed: {result.get('reason', 'unknown')}")

    def _inventory_list(self, inventory) -> None:
        entries = list(inventory.list_items())
        if not entries:
            self.log("Inventory: <empty>")
            return
        db = self._inventory_db()
        self.log("Inventory contents:")
        for item_id, amount in entries:
            label = self._inventory_label(item_id, db)
            self.log(f"  - {label} ({item_id}) x{amount}")

    def _inventory_add(self, inventory, item_id: str, amount: int) -> None:
        normalized = item_id.strip()
        if not normalized:
            self.log("Item id required")
            return
        before = inventory.get_count(normalized)
        try:
            added = inventory.add_item(normalized, amount)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Inventory add failed: {exc}")
            return
        after = inventory.get_count(normalized)
        if not added:
            db = self._inventory_db()
            definition = db.get(normalized) if db else None
            if definition is None:
                self._inventory_unknown_item(normalized, db)
            else:
                self.log(
                    f"{definition.name or normalized} already at max stack ({definition.max_stack})",
                )
            return
        delta = max(0, after - before)
        label = self._inventory_label(normalized)
        self.log(f"Added {delta} x {label}")

    def _inventory_remove(self, inventory, item_id: str, amount: int) -> None:
        normalized = item_id.strip()
        if not normalized:
            self.log("Item id required")
            return
        before = inventory.get_count(normalized)
        if before <= 0:
            self.log(f"Item '{normalized}' not currently in inventory")
            return
        try:
            removed = inventory.remove_item(normalized, amount)
        except Exception as exc:  # noqa: BLE001
            self.log(f"Inventory remove failed: {exc}")
            return
        if not removed:
            self.log(f"Item '{normalized}' not currently in inventory")
            return
        after = inventory.get_count(normalized)
        delta = before - after
        label = self._inventory_label(normalized)
        self.log(f"Removed {delta} x {label}")

    def _inventory_parse_amount(self, text: str) -> int | None:
        parsed = self._parse_int(text, "amount")
        if parsed is None:
            return None
        if parsed <= 0:
            self.log("Amount must be positive")
            return None
        return parsed

    def _inventory_db(self):  # noqa: ANN201 - helper returns ItemDatabase | None
        try:
            return load_item_database()
        except Exception:  # pragma: no cover - best effort for console UX
            return None

    def _inventory_label(self, item_id: str, db=None) -> str:
        if db is None:
            db = self._inventory_db()
        if db is not None:
            definition = db.get(item_id)
            if definition is not None and definition.name:
                return definition.name
        return item_id

    def _inventory_unknown_item(self, item_id: str, db=None) -> None:
        message = f"Unknown item '{item_id}'"
        db = db or self._inventory_db()
        if db is not None:
            suggestion = db.suggest(item_id)
            if suggestion:
                message += f". Did you mean '{suggestion}'?"
        self.log(message)

    def _encounter_command(self, args: list[str]) -> None:
        console_commands.dispatch_command(self, "encounter", list(args))

    def _entity_command(self, args: list[str]) -> None:
        if args and args[0].lower() == "set":
            self._entity_set(args[1:])
            return

        if args and args[0].lower() == "beh":
            self._entity_beh_command(args[1:])
            return

        if args and args[0].lower() == "anim":
            self._entity_anim_command(args[1:])
            return

        sprites = list(self.window.scene_controller.all_sprites)
        if not sprites:
            self.log("No entities loaded")
            return

        if not args:
            self.log("Entities:")
            for idx, sprite in enumerate(sprites):
                name = getattr(sprite, "mesh_name", None) or "<unnamed>"
                tag = getattr(sprite, "mesh_tag", None) or "<none>"
                layer = self._find_layer_name(sprite)
                self.log(
                    f"  [{idx}] {name} (layer={layer}, tag={tag})",
                )
            return

        target = args[0]
        sprite, index, _ = self._resolve_entity_reference(target, sprites)

        if sprite is None or index is None:
            self.log(f"No entity found for '{target}'")
            return

        name = getattr(sprite, "mesh_name", None) or "<unnamed>"
        tag = getattr(sprite, "mesh_tag", None) or "<none>"
        layer = self._find_layer_name(sprite)
        solid = bool(getattr(sprite, "mesh_is_solid", False))
        asset = getattr(sprite, "mesh_entity_data", {}).get("sprite", "<unknown>")
        declared_behaviours = list(getattr(sprite, "mesh_behaviours", []))
        runtime_behaviours = list(getattr(sprite, "mesh_behaviours_runtime", []))

        self.log(f"Entity [{index}] {name}")
        self.log(f"  tag: {tag}")
        self.log(
            f"  position: ({sprite.center_x:.1f}, {sprite.center_y:.1f})",
        )
        rotation_text = self._format_scalar(getattr(sprite, "angle", 0.0))
        scale_text = self._format_scalar(getattr(sprite, "scale", 1.0))
        self.log(f"  rotation: {rotation_text}°, scale: {scale_text}")
        self.log(
            f"  layer: {layer}, solid: {'yes' if solid else 'no'}",
        )
        self.log(f"  texture: {asset}")

        if declared_behaviours:
            self.log(
                f"  behaviours (declared): {', '.join(declared_behaviours)}",
            )
        else:
            self.log("  behaviours (declared): <none>")

        if runtime_behaviours:
            runtime_names = ", ".join(
                behaviour.__class__.__name__ for behaviour in runtime_behaviours
            )
            self.log(f"  behaviours (runtime): {runtime_names}")
        else:
            self.log("  behaviours (runtime): <none>")

        health_line = self._entity_health_summary(runtime_behaviours)
        if health_line:
            self.log(f"  health: {health_line}")

    def _find_layer_name(self, target: optional_arcade.arcade.Sprite) -> str:
        for layer_name, sprite_list in self.window.scene_controller.layers.items():
            if target in sprite_list:
                return layer_name
        return "<unknown>"

    def _parse_float(self, value: Any, label: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            self.log(f"Invalid {label}: {value}")
            return None

    def _parse_int(self, value: Any, label: str) -> int | None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            self.log(f"Invalid {label}: {value}")
            return None

    @staticmethod
    def _format_scalar(value: Any, *, precision: int = 2) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        fmt = f"{{:.{precision}f}}"
        return fmt.format(number)

    @staticmethod
    def _entity_health_summary(behaviours: list[Any]) -> str | None:
        for behaviour in behaviours:
            max_hp = getattr(behaviour, "max_health", None)
            current_hp = getattr(behaviour, "health", None)
            if max_hp is None and current_hp is None:
                continue
            safe_current = current_hp if current_hp is not None else max_hp
            if safe_current is None:
                continue
            try:
                cur = float(safe_current)
            except (TypeError, ValueError):
                cur = 0.0
            try:
                maximum = float(max_hp) if max_hp is not None else cur
            except (TypeError, ValueError):
                maximum = cur
            return f"{cur:.1f}/{maximum:.1f}"
        return None

    def _resolve_entity_reference(
        self,
        ref: str,
        sprites: list[optional_arcade.arcade.Sprite] | None = None,
    ) -> tuple[optional_arcade.arcade.Sprite | None, int | None, list[optional_arcade.arcade.Sprite]]:
        if sprites is None:
            sprites = list(self.window.scene_controller.all_sprites)
        if not sprites:
            return None, None, sprites

        sprite: optional_arcade.arcade.Sprite | None = None
        index: int | None = None

        try:
            idx = int(ref)
        except ValueError:
            idx = None

        if idx is not None and 0 <= idx < len(sprites):
            sprite = sprites[idx]
            index = idx
            return sprite, index, sprites

        lowered = ref.strip().lower()
        for idx, candidate in enumerate(sprites):
            name = getattr(candidate, "mesh_name", None)
            if isinstance(name, str) and name.strip().lower() == lowered:
                sprite = candidate
                index = idx
                break

        return sprite, index, sprites

    def _entity_set(self, args: list[str]) -> None:
        if len(args) < 3:
            self.log(
                "Usage: entity set <index|name> <field> <value>"
            )
            return

        target = args[0]
        field = args[1].lower()
        values = args[2:]

        sprite, index, _ = self._resolve_entity_reference(target)
        if sprite is None or index is None:
            self.log(f"No entity found for '{target}'")
            return

        if field == "x":
            x_value = self._parse_float(values[0], "x")
            if x_value is None:
                return
            self.window.scene_controller._apply_entity_mutation(sprite, x=x_value)
            self.log(f"Entity [{index}] x set to {x_value:.1f}")
            return

        if field == "y":
            y_value = self._parse_float(values[0], "y")
            if y_value is None:
                return
            self.window.scene_controller._apply_entity_mutation(sprite, y=y_value)
            self.log(f"Entity [{index}] y set to {y_value:.1f}")
            return

        if field == "pos":
            if len(values) < 2:
                self.log("Usage: entity set <ref> pos <x> <y>")
                return
            x_value = self._parse_float(values[0], "x")
            y_value = self._parse_float(values[1], "y")
            if x_value is None or y_value is None:
                return
            self.window.scene_controller._apply_entity_mutation(sprite, x=x_value, y=y_value)
            self.log(
                f"Entity [{index}] position set to ({x_value:.1f}, {y_value:.1f})"
            )
            return

        if field == "tag":
            tag_value = self._normalize_tag_value(values[0])
            self.window.scene_controller._apply_entity_mutation(sprite, tag=tag_value)
            display = tag_value if tag_value is not None else "<none>"
            self.log(f"Entity [{index}] tag set to {display}")
            return

        if field == "scale":
            scale_value = self._parse_float(values[0], "scale")
            if scale_value is None:
                return
            self.window.scene_controller._apply_entity_mutation(sprite, scale=scale_value)
            self.log(f"Entity [{index}] scale set to {scale_value:.3f}")
            return

        self.log(
            "Unknown entity field. Supported fields: x, y, pos, tag, scale"
        )

    def _beh_command(self, args: list[str]) -> None:
        usage = (
            "Usage: beh list [ref] | beh get <ref> <behaviour> <param> | "
            "beh set <ref> <behaviour> <param> <value>"
        )
        if not args:
            self._beh_list_all()
            return

        action = args[0].lower()
        if action == "list":
            if len(args) >= 2:
                self._beh_list_entity(args[1])
            else:
                self._beh_list_all()
            return

        if action == "get":
            if len(args) < 4:
                self.log("Usage: beh get <ref> <behaviour> <param>")
                return
            self._beh_get(args[1], args[2], args[3])
            return

        if action == "set":
            if len(args) < 5:
                self.log("Usage: beh set <ref> <behaviour> <param> <value>")
                return
            ref = args[1]
            behaviour_ref = args[2]
            param = args[3]
            value = " ".join(args[4:])
            self._entity_beh_set(ref, behaviour_ref, param, value)
            return

        self.log(usage)

    def _beh_list_all(self) -> None:
        sprites = list(self.window.scene_controller.all_sprites)
        if not sprites:
            self.log("No entities loaded")
            return
        self.log("Behaviour parameters:")
        for idx, sprite in enumerate(sprites):
            behaviours = getattr(sprite, "mesh_behaviours", [])
            if not behaviours:
                continue
            label = getattr(sprite, "mesh_name", None) or "<unnamed>"
            self.log(f"  [{idx}] {label}:")
            self._print_behaviour_params(sprite, behaviours)

    def _beh_list_entity(self, ref: str) -> None:
        sprite, index, _ = self._resolve_entity_reference(ref)
        if sprite is None or index is None:
            self.log(f"No entity found for '{ref}'")
            return
        behaviours = getattr(sprite, "mesh_behaviours", [])
        if not behaviours:
            self.log(f"Entity [{index}] has no behaviours")
            return
        label = getattr(sprite, "mesh_name", None) or "<unnamed>"
        self.log(f"Behaviours for [{index}] {label}:")
        self._print_behaviour_params(sprite, behaviours)

    def _print_behaviour_params(
        self,
        sprite: optional_arcade.arcade.Sprite,
        behaviours: Sequence[str],
    ) -> None:
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        for index, behaviour_name in enumerate(behaviours):
            overrides = config_root.get(behaviour_name)
            if not isinstance(overrides, dict):
                overrides = {}
            lines = self._describe_behaviour_params(behaviour_name, overrides)
            header = f"    - [{index}] {behaviour_name}"
            if lines:
                self.log(f"{header}:")
                for line in lines:
                    self.log(f"        {line}")
            else:
                self.log(f"{header}: <no params>")

    def _describe_behaviour_params(
        self,
        behaviour_name: str,
        overrides: dict[str, Any],
    ) -> list[str]:
        param_defs = get_behaviour_param_defs(behaviour_name)
        lines: list[str] = []

        for name in sorted(param_defs.keys()):
            spec = param_defs[name]
            explicit = name in overrides
            value = overrides[name] if explicit else spec.default
            kind = self._param_kind_from_def(spec.type)
            state = "set" if explicit else "default"
            value_repr = self._format_param_value(value)
            lines.append(f"{name} = {value_repr} [{kind}; {state}]")

        custom_names = sorted(name for name in overrides.keys() if name not in param_defs)
        for name in custom_names:
            value_repr = self._format_param_value(overrides[name])
            lines.append(f"{name} = {value_repr} [custom]")

        return lines

    def _format_param_value(self, value: Any) -> str:
        # Helper to format values for console output
        if isinstance(value, str):
            return f"'{value}'"
        return str(value)

    def _suggest_param_name(self, target: str, candidates: Sequence[str]) -> str | None:
        pool = [name for name in candidates if isinstance(name, str) and name.strip()]
        if not target or not pool:
            return None
        lookup = {name.lower(): name for name in pool}
        matches = difflib.get_close_matches(target.lower(), lookup.keys(), n=1, cutoff=0.7)
        if matches:
            return lookup[matches[0]]
        return None

    def _beh_get(self, ref: str, behaviour_ref: str, field: str) -> None:
        sprite, index, _ = self._resolve_entity_reference(ref)
        if sprite is None or index is None:
            self.log(f"No entity found for '{ref}'")
            return
        behaviour_name, _ = self._resolve_sprite_behaviour(sprite, behaviour_ref)
        if behaviour_name is None:
            self.log(f"No behaviour '{behaviour_ref}' on entity [{index}]")
            return
        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        behaviour_config = config_root.get(behaviour_name, {})
        if not isinstance(behaviour_config, dict):
            behaviour_config = {}

        param_defs = get_behaviour_param_defs(behaviour_name)
        spec = param_defs.get(field)
        explicit = field in behaviour_config

        if explicit:
            value = behaviour_config[field]
            state = "set"
        elif spec is not None:
            value = spec.default
            state = "default"
        else:
            value = "<unset>"
            state = "unset"

        value_repr = self._format_param_value(value)
        if spec is not None:
            kind = self._param_kind_from_def(spec.type)
            detail = f"[{kind}; {state}]"
        elif explicit:
            detail = "[custom]"
        else:
            detail = "[unknown]"

        self.log(
            f"Entity [{index}] behaviour '{behaviour_name}' param '{field}' = {value_repr} {detail}"
        )

    def _resolve_sprite_behaviour(
        self,
        sprite: optional_arcade.arcade.Sprite,
        reference: str,
    ) -> tuple[str | None, int | None]:
        behaviours = [
            str(name)
            for name in getattr(sprite, "mesh_behaviours", [])
            if isinstance(name, str)
        ]
        if not behaviours:
            return None, None

        try:
            idx = int(reference)
        except (TypeError, ValueError):
            idx = None

        if idx is not None and 0 <= idx < len(behaviours):
            return behaviours[idx], idx

        lowered = reference.strip().lower()
        for position, name in enumerate(behaviours):
            if name.lower() == lowered:
                return name, position

        return None, None

    def _reload_behaviours(self) -> None:
        try:
            reloaded = reload_behaviour_modules()
        except Exception as exc:  # noqa: BLE001
            self.window.scene_controller._hot_reload_log(f"Behaviour reload failed: {exc}")
            return
        self.window.scene_controller._hot_reload_log(
            f"Reloaded {reloaded} behaviour module(s). Run `reload_scene` to apply new logic."
        )

    def _entity_beh_command(self, args: list[str]) -> None:
        usage = (
            "Usage: entity beh list <ref> | entity beh set <ref> <behaviour> <field> <value> | "
            "entity beh reload <ref>"
        )
        if not args:
            self.log(usage)
            return

        action = args[0].lower()
        if action == "list":
            if len(args) < 2:
                self.log("Usage: entity beh list <ref>")
                return
            self._entity_beh_list(args[1])
            return

        if action == "set":
            if len(args) < 5:
                self.log("Usage: entity beh set <ref> <behaviour> <field> <value>")
                return
            ref = args[1]
            behaviour_ref = args[2]
            field_name = args[3]
            raw_value = " ".join(args[4:])
            self._entity_beh_set(ref, behaviour_ref, field_name, raw_value)
            return

        if action == "reload":
            if len(args) < 2:
                self.log("Usage: entity beh reload <ref>")
                return
            self._entity_beh_reload(args[1])
            return

        self.log(usage)

    def _entity_beh_list(self, ref: str) -> None:
        sprite, index, _ = self._resolve_entity_reference(ref)
        if sprite is None or index is None:
            self.log(f"No entity found for '{ref}'")
            return

        behaviours = [str(name) for name in getattr(sprite, "mesh_behaviours", []) if name]
        if not behaviours:
            self.log(f"Entity [{index}] has no behaviours")
            return

        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        label = getattr(sprite, "mesh_name", None) or "<unnamed>"
        self.log(f"Behaviours for [{index}] {label}:")
        self._print_behaviour_params(sprite, behaviours)

    def _entity_beh_set(
        self,
        ref: str,
        behaviour_ref: str,
        field_name: str,
        raw_value: str,
    ) -> None:
        sprite, index, _ = self._resolve_entity_reference(ref)
        if sprite is None or index is None:
            self.log(f"No entity found for '{ref}'")
            return

        behaviour_name, behaviour_index = self._resolve_sprite_behaviour(sprite, behaviour_ref)
        if behaviour_name is None or behaviour_index is None:
            self.log(f"No behaviour '{behaviour_ref}' on entity [{index}]")
            return

        param_defs = get_behaviour_param_defs(behaviour_name)
        spec = param_defs.get(field_name)
        info = get_behaviour_info(behaviour_name)
        info_fields: dict[str, dict[str, Any]] = {}
        if info is not None:
            info_fields = {
                str(field.get("name")): field
                for field in info.config_fields
                if isinstance(field, dict) and field.get("name")
            }
        if spec is None and field_name not in info_fields:
            suggestion = self._suggest_param_name(
                field_name,
                list(param_defs.keys()) + list(info_fields.keys()),
            )
            warning = (
                f"Warning: behaviour '{behaviour_name}' does not declare a param named '{field_name}'"
            )
            if suggestion:
                warning += f" (did you mean '{suggestion}'?)"
            self.log(warning)

        value = self._coerce_behaviour_field_input(behaviour_name, field_name, raw_value)
        value_repr = self._format_param_value(value)
        if spec is not None:
            kind_detail = f" [{self._param_kind_from_def(spec.type)}]"
        elif field_name in info_fields:
            field_spec = info_fields[field_name]
            field_type = str(field_spec.get("type", "string"))
            kind_detail = f" [{field_type}]"
        else:
            kind_detail = ""

        entity_data = self.window.scene_controller._ensure_entity_data_dict(sprite)
        config_root = self.window.scene_controller._ensure_behaviour_config_root(entity_data)
        behaviour_config = config_root.setdefault(behaviour_name, {})
        behaviour_config[field_name] = value
        entity_data["behaviour_config"] = config_root

        entries = self.window.scene_controller._get_behaviour_configs_for_sprite(sprite)
        if 0 <= behaviour_index < len(entries):
            params_bucket = entries[behaviour_index].setdefault("params", {})
            if isinstance(params_bucket, dict):
                params_bucket[field_name] = value
            entity_data["behaviours"] = entries
            sprite.mesh_behaviour_configs = entries  # type: ignore[attr-defined]

        entity_data[field_name] = value

        updated_runtime = self._apply_behaviour_runtime_update(
            sprite,
            behaviour_index,
            field_name,
            value,
        )

        if updated_runtime:
            self.log(
                f"Entity [{index}] behaviour '{behaviour_name}' field '{field_name}' set to {value_repr}{kind_detail}"
            )
        else:
            self.log(
                f"Updated config for behaviour '{behaviour_name}' field '{field_name}' = {value_repr}{kind_detail}. "
                "Use 'entity beh reload' to apply runtime changes if needed",
            )
        return

    def _apply_behaviour_runtime_update(
        self,
        sprite: optional_arcade.arcade.Sprite,
        behaviour_index: int,
        field_name: str,
        value: Any,
    ) -> bool:
        runtime_behaviours = getattr(sprite, "mesh_behaviours_runtime", [])
        if not isinstance(runtime_behaviours, list):
            return False
        if not (0 <= behaviour_index < len(runtime_behaviours)):
            return False

        behaviour = runtime_behaviours[behaviour_index]
        updated = False
        config = getattr(behaviour, "config", None)
        if isinstance(config, dict):
            config[field_name] = value
            updated = True

        if hasattr(behaviour, field_name):
            setattr(behaviour, field_name, value)
            updated = True

        hook = getattr(behaviour, "on_config_updated", None)
        if callable(hook):
            try:
                hook(field_name, value)
                updated = True
            except Exception as exc:  # noqa: BLE001
                self.log(f"Warning: behaviour runtime update failed: {exc}")

        return updated

    def _coerce_behaviour_field_input(
        self,
        behaviour_name: str,
        field_name: str,
        raw_value: str,
    ) -> Any:
        param_defs = get_behaviour_param_defs(behaviour_name)
        spec = param_defs.get(field_name)
        if spec is not None:
            expected = self._param_kind_from_def(spec.type)
        else:
            info = get_behaviour_info(behaviour_name)
            expected = "string"
            if info is not None:
                for field in info.config_fields:
                    if field.get("name") == field_name:
                        expected = str(field.get("type", "string")).lower()
                        break

        return self._parse_value_for_kind(expected, raw_value)

    def _param_kind_from_def(self, raw_type: Any) -> str:
        if raw_type in {int, "int"}:
            return "int"
        if raw_type in {float, "float"}:
            return "float"
        if raw_type in {bool, "bool"}:
            return "bool"
        if raw_type in {list, tuple, "array"}:
            return "array"
        if raw_type in {dict, "object"}:
            return "object"
        return "string"

    def _parse_value_for_kind(self, kind: str, raw_value: str) -> Any:
        text = (raw_value or "").strip()
        if kind == "float":
            try:
                return float(text)
            except ValueError:
                return 0.0
        if kind == "int":
            try:
                return int(float(text))
            except ValueError:
                return 0
        if kind == "bool":
            lowered = text.lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
            return bool(text)
        if kind == "array":
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            if "," in text:
                return [chunk.strip() for chunk in text.split(",") if chunk.strip()]
            return [text] if text else []
        if kind == "object":
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return {"value": text} if text else {}
        return text

    def _entity_anim_command(self, args: list[str]) -> None:
        usage = (
            "Usage: entity anim list <ref> | entity anim set <ref> <state> | "
            "entity anim state <ref> | entity anim pulse <ref> <state> [priority] [ttl]"
        )
        if not args:
            self.log(usage)
            return

        action = args[0].lower()
        if action == "list":
            if len(args) < 2:
                self.log("Usage: entity anim list <ref>")
                return
            sprite, index, _ = self._resolve_entity_reference(args[1])
            if sprite is None or index is None:
                self.log(f"No entity found for '{args[1]}'")
                return
            animator = getattr(sprite, "mesh_animator", None)
            if animator is None:
                self.log(f"Entity [{index}] has no animator")
                return
            name = getattr(sprite, "mesh_name", "<unnamed>")
            self.log(f"Animator states for entity [{index}] {name}:")
            enumerator = getattr(animator, "available_states", None)
            states = enumerator() if callable(enumerator) else []
            current = getattr(animator, "current_state", "<unknown>")
            if not states:
                self.log("  <no states>")
            else:
                for state in states:
                    marker = "*" if state == current else "-"
                    self.log(f"  {marker} {state}")
            return

        if action == "state":
            if len(args) < 2:
                self.log("Usage: entity anim state <ref>")
                return
            sprite, index, _ = self._resolve_entity_reference(args[1])
            if sprite is None or index is None:
                self.log(f"No entity found for '{args[1]}'")
                return
            snapshot = get_animation_state_snapshot(sprite)
            animator = getattr(sprite, "mesh_animator", None)
            clip_state = getattr(animator, "current_state", None) if animator else None
            clip_info = "<none>"
            clip_obj = None
            if animator and clip_state:
                clip = getattr(animator, "clips", {}).get(clip_state)
                clip_obj = clip
                if clip is not None:
                    clip_info = (
                        f"{clip_state} ({len(clip.frames)}f @ {clip.fps:.1f}fps, "
                        f"loop={'yes' if clip.loop else 'no'}"
                    )
                else:
                    clip_info = clip_state
            self.log(f"Entity [{index}] animation debug:")
            movement = snapshot.get("movement_state") or "<unset>"
            requested = snapshot.get("animation_state") or "<unset>"
            default = snapshot.get("default_animation") or "<unset>"
            priority = float(snapshot.get("priority", 0.0))
            timer = float(snapshot.get("timer", 0.0))
            override_active = "active" if snapshot.get("override_active") else "inactive"
            self.log(f"  movement_state: {movement}")
            self.log(f"  animation_state: {requested} (default: {default})")
            self.log(f"  animator clip: {clip_info}")
            self.log(
                f"  override: priority={priority:.2f} timer={timer:.2f}s [{override_active}]"
            )
            if animator is not None:
                blend_duration = float(getattr(animator, "_blend_duration", 0.0))
                blend_elapsed = float(getattr(animator, "_blend_elapsed", 0.0))
                blend_active = bool(getattr(animator, "_blend_from_texture", None))
                default_blend = float(getattr(animator, "default_blend", 0.0))
                if blend_active or default_blend > 0.0:
                    if blend_active and blend_duration > 0.0:
                        self.log(
                            f"  blend: {blend_elapsed:.2f}/{blend_duration:.2f}s (default {default_blend:.2f}s)"
                        )
                    else:
                        self.log(f"  blend: default {default_blend:.2f}s (inactive)")
                if clip_obj is not None and getattr(clip_obj, "events", None):
                    events = getattr(clip_obj, "events", ())
                    labels = ", ".join(marker.label for marker in events)
                    self.log(f"  events: {labels}")
            return

        if action == "pulse":
            if len(args) < 3:
                self.log("Usage: entity anim pulse <ref> <state> [priority] [ttl]")
                return
            sprite, index, _ = self._resolve_entity_reference(args[1])
            if sprite is None or index is None:
                self.log(f"No entity found for '{args[1]}'")
                return
            state = args[2]
            priority = 0.0
            ttl = 0.0
            if len(args) >= 4:
                parsed = self._parse_float(args[3], "priority")
                if parsed is None:
                    return
                priority = float(parsed)
            if len(args) >= 5:
                parsed_ttl = self._parse_float(args[4], "ttl")
                if parsed_ttl is None:
                    return
                ttl = float(parsed_ttl)
            accepted = request_animation_state(sprite, state, priority=priority, ttl=ttl)
            if accepted:
                self.log(
                    f"Requested animation '{state}' on entity [{index}] (priority={priority:.2f}, ttl={ttl:.2f})"
                )
            else:
                self.log(
                    "Animation request ignored: another state holds a higher priority override",
                )
            return

        if action == "set":
            if len(args) < 3:
                self.log("Usage: entity anim set <ref> <state>")
                return
            sprite, index, _ = self._resolve_entity_reference(args[1])
            if sprite is None or index is None:
                self.log(f"No entity found for '{args[1]}'")
                return
            animator = getattr(sprite, "mesh_animator", None)
            if animator is None:
                self.log(f"Entity [{index}] has no animator")
                return
            setter = getattr(animator, "set_state", None)
            if callable(setter) and setter(args[2], force=True):
                current = getattr(animator, "current_state", args[2])
                self.log(f"Entity [{index}] animation set to '{current}'")
            else:
                self.log(f"Animator has no state '{args[2]}'")
            return

        self.log("Unknown entity anim command. Use 'list' or 'set'.")

    def _entity_beh_reload(self, ref: str) -> None:
        sprite, index, _ = self._resolve_entity_reference(ref)
        if sprite is None or index is None:
            self.log(f"No entity found for '{ref}'")
            return

        self.window.scene_controller._rebuild_behaviours_for_sprite(sprite)
        self.log(f"Reloaded behaviours for entity [{index}]")

    def _save_scene(self, args: list[str]) -> None:
        compact = "--compact" in args
        clean_args = [a for a in args if a != "--compact"]

        if not clean_args:
            # Default to current scene path if available, else error
            if not self.window.scene_controller.current_scene_path:
                self.log("Error: No scene loaded to save. Provide a path.")
                return
            target_path = self.window.scene_controller.current_scene_path
        else:
            target_path = clean_args[0]

        try:
            snapshot = self.window.build_scene_snapshot(compact=compact)

            json_io.write_json_atomic(target_path, snapshot)

            self.log(f"Scene saved to '{target_path}'")

        except Exception as e:
            self.log(f"Error saving scene: {e}")
            logger.error("[Mesh][Save] Error: %s", e)

    def _dump_scene(self, target_path: str) -> None:
        try:
            snapshot = self.window.build_scene_snapshot()
            json_io.write_json_atomic(target_path, snapshot)
            self.log(f"Dumped scene to '{target_path}'")
        except Exception as e:
            self.log(f"Error dumping scene: {e}")
            logger.error("[Mesh][Dump] Error: %s", e)


    def _normalize_tag_value(self, value: str) -> str | None:
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"none", "null", "nil"}:
            return None
        return cleaned

    def _spawn_command(self, args: list[str]) -> None:
        if len(args) < 3:
            self.log("Usage: spawn <sprite_path> <x> <y>")
            return
        sprite_path = args[0]
        x = self._parse_float(args[1], "x")
        y = self._parse_float(args[2], "y")
        if x is None or y is None:
            return

        entity = {
            "sprite": sprite_path,
            "x": x,
            "y": y,
            "name": f"spawned_{len(list(self.window.all_sprites))}",
            "layer": "entities"
        }
        sprite = self.window.scene_controller._create_sprite(entity)
        if sprite:
            self.window.scene_controller.layers["entities"].append(sprite)
            self.log(f"Spawned {entity['name']} at ({x}, {y})")

    def _spawn_like_command(self, args: list[str]) -> None:
        if len(args) < 3:
            self.log("Usage: spawn_like <ref> <x> <y>")
            return
        ref = args[0]
        x = self._parse_float(args[1], "x")
        y = self._parse_float(args[2], "y")
        if x is None or y is None:
            return

        sprite, _, _ = self._resolve_entity_reference(ref)
        if not sprite:
            self.log(f"Entity '{ref}' not found")
            return

        entity_data = getattr(sprite, "mesh_entity_data", {})
        new_entity = dict(entity_data)
        new_entity["x"] = x
        new_entity["y"] = y
        new_entity["name"] = f"{new_entity.get('name', 'entity')}_clone"

        new_sprite = self.window.scene_controller._create_sprite(new_entity)
        if new_sprite:
            layer_name = self._find_layer_name(sprite)
            if layer_name in self.window.scene_controller.layers:
                self.window.scene_controller.layers[layer_name].append(new_sprite)
            else:
                self.window.scene_controller.layers["entities"].append(new_sprite)
            self.log(f"Spawned clone at ({x}, {y})")

    def _list_registered_behaviours(self) -> None:
        from .behaviours import list_behaviours
        self.log("Registered Behaviours:")
        for name in list_behaviours():
            self.log(f"  - {name}")

    def _behaviour_detail(self, args: list[str]) -> None:
        if not args:
            self.log("Usage: behaviour <name>")
            return
        name = args[0]
        from .behaviours import get_behaviour_info
        info = get_behaviour_info(name)
        if not info:
            self.log(f"Behaviour '{name}' not found")
            return
        self.log(f"Behaviour: {name}")
        self.log(f"  Description: {info.description or '<none>'}")
        self.log("  Params:")
        for field in info.config_fields:
            fname = field.get("name")
            ftype = field.get("type")
            fdefault = field.get("default")
            self.log(f"    - {fname} ({ftype}) default={fdefault}")

    def _events_command(self) -> None:
        bus = self.window.event_bus
        self.log(f"Event Bus: {len(bus._subscribers)} topics")
        for topic, subs in bus._subscribers.items():
            self.log(f"  {topic}: {len(subs)} subscribers")

    def _update_order_command(self) -> None:
        self.log("Update Order:")
        self.log("  1. Input")
        self.log("  2. Behaviours (Pre-Update)")
        self.log("  3. Behaviours (Update)")
        self.log("  4. Movement (Physics)")
        self.log("  5. Animation")
        self.log("  6. Collision Resolution")
        self.log("  7. Behaviours (Late-Update)")
        self.log("  8. UI")

    def _dump_state(self, path: str) -> None:
        state = self.window.game_state.snapshot()
        try:
            json_io.write_json_atomic(path, state)
            self.log(f"State dumped to {path}")
        except Exception as e:
            self.log(f"Error dumping state: {e}")

    def _load_state(self, path: str) -> None:
        try:
            with open(path, "r") as f:
                state = json.load(f)
            self.window.scene_controller._apply_scene_state(state)
            self.log(f"State loaded from {path}")
        except Exception as e:
            self.log(f"Error loading state: {e}")

    def _build_project_index(self, args: list[str]) -> None:
        output = args[0] if args else "mesh_index.json"
        from .tooling_runtime.project_index import build_project_index
        try:
            build_project_index(".", output)
            self.log(f"Project index built to {output}")
        except Exception as e:
            self.log(f"Error building index: {e}")

    def _ai_context(self, path: str) -> None:
        self.log("Command 'ai_context' is deprecated. Use 'mesh ai-export-context' CLI instead.")

    def _generate_docs(self, target_dir: str) -> None:
        from .tooling_runtime.generate_docs import generate_docs
        try:
            generate_docs(".", target_dir)
            self.log(f"Docs generated in {target_dir}")
        except Exception as e:
            self.log(f"Error generating docs: {e}")

    def _ai_bundle(self, target_dir: str) -> None:
        self.log("Command 'ai_bundle' is deprecated. Use 'mesh ai-bundle' CLI instead.")

    def _ai_job(self, job_path: str) -> None:
        try:
            job = load_job(job_path)
        except Exception as exc:  # noqa: BLE001
            self.log(f"[AI] Failed to load job '{job_path}': {exc}")
            return

        ops = AIOps(".")
        result = ops.apply_job(job)
        ok = result.get("ok", False)
        op_count = len(result.get("results") or [])
        scenes = {
            str(op.get("scene_path"))
            for op in job.get("operations", [])
            if isinstance(op, dict) and op.get("scene_path")
        }
        if ok:
            scene_hint = f" | scenes: {', '.join(sorted(scenes))}" if scenes else ""
            self.log(f"[AI] Applied {op_count} operation(s) from {job_path}{scene_hint}")
            reloader = getattr(self.window, "reload_scene", None)
            if callable(reloader):
                reloader()
        else:
            self.log(f"[AI] Job failed ({op_count} op(s)); see details:")
            for entry in result.get("results") or []:
                if not entry.get("ok"):
                    self.log(f" - {entry.get('message')}")

    def _validate_scene(self, path: str) -> None:
        from .tooling_runtime.scene_validate import validate_scene_file
        try:
            errors = validate_scene_file(path)
            if not errors:
                self.log(f"Scene '{path}' is valid.")
            else:
                self.log(f"Scene '{path}' has errors:")
                for err in errors:
                    self.log(f"  - {err}")
        except Exception as e:
            self.log(f"Error validating scene: {e}")

    def _assets_command(self, args: list[str]) -> None:
        if args and args[0] == "clear":
            self.window.assets.clear()
            self.log("Texture cache cleared")
            return

        count = len(self.window.assets._texture_cache)
        self.log(f"Assets: {count} textures cached")

    def _print_config(self) -> None:
        cfg = self.window.engine_config
        self.log(f"  Title: {cfg.title}")
        self.log(f"  Fullscreen: {cfg.fullscreen}")
        self.log(f"  VSync: {cfg.vsync}")
        self.log(f"  Debug: {cfg.debug_on_start}")

    def _bindings_command(self) -> None:
        manager = self._get_input_manager()
        if manager is None:
            self.log("Input manager not available")
            return
        cfg_bindings = getattr(getattr(self.window, "engine_config", None), "input_bindings", None)
        actions = sorted(known_actions(manager, cfg_bindings))
        bindings = snapshot_bindings(manager)
        self.log("Input Bindings:")
        for action in actions:
            keys = bindings.get(action, [])
            label = ", ".join(keys) if keys else "<unbound>"
            self.log(f"  {action}: {label}")

    def _bind_command(self, args: list[str]) -> None:
        if len(args) < 2:
            self.log("Usage: bind <action> <key_name>")
            return
        manager = self._get_input_manager()
        if manager is None:
            self.log("Input manager not available")
            return

        action, key_name = args[0], args[1]
        if not self._is_known_action(action, manager):
            self.log(f"Unknown action '{action}'")
            return

        code = key_name_to_code(key_name)
        if code is None:
            self.log(f"Unknown key name '{key_name}'")
            return

        manager.bind(action, code)
        self._persist_bindings(manager)
        self.log(f"Bound {action} -> {key_code_to_name(code)}")

    def _unbind_command(self, args: list[str]) -> None:
        if not args:
            self.log("Usage: unbind <action> [<key_name>]")
            return

        manager = self._get_input_manager()
        if manager is None:
            self.log("Input manager not available")
            return

        action = args[0]
        if not self._is_known_action(action, manager):
            self.log(f"Unknown action '{action}'")
            return

        if len(args) > 1:
            key_name = args[1]
            code = key_name_to_code(key_name)
            if code is None:
                self.log(f"Unknown key name '{key_name}'")
                return
            manager.unbind(action, code)
            self._persist_bindings(manager)
            self.log(f"Unbound {key_code_to_name(code)} from {action}")
            return

        current = manager.get_bindings().get(action, [])
        if not current:
            self.log(f"No bindings to clear for '{action}'")
            return

        for code in list(current):
            manager.unbind(action, code)
        self._persist_bindings(manager)
        self.log(f"Cleared bindings for '{action}'")

    def _is_known_action(self, action: str, manager) -> bool:
        cfg_bindings = getattr(getattr(self.window, "engine_config", None), "input_bindings", None)
        return action in known_actions(manager, cfg_bindings)

    def _get_input_manager(self):
        manager = getattr(self.window, "input", None)
        if manager is not None:
            return manager
        controller = getattr(self.window, "input_controller", None)
        return getattr(controller, "manager", None)

    def _persist_bindings(self, manager) -> None:
        controller = getattr(self.window, "input_controller", None)
        if controller is not None and hasattr(controller, "persist_bindings"):
            controller.persist_bindings(save=True)
            return

        cfg = getattr(self.window, "engine_config", None)
        if cfg is None:
            self.log("Config not available; bindings not saved")
            return

        cfg.input_bindings = snapshot_bindings(manager)
        try:
            from .config import save_config

            save_config(cfg, getattr(self.window, "config_path", "config.json"))
        except Exception as exc:  # noqa: BLE001
            self.log(f"Failed to save bindings: {exc}")





    def _handle_set(self, args: list[str]) -> None:
        if len(args) < 2:
            self.log("Usage: set <key> <value>")
            return
        key = args[0].lower()
        value = args[1].lower()

        if key == "volume" or key == "master":
            vol = self._parse_float(value, "volume")
            if vol is not None:
                self.window.audio.set_master_volume(vol)
                self.window.engine_config.master_volume = vol
                self.log(f"Master volume set to {vol:.2f}")
            return

        if key == "sfx":
            vol = self._parse_float(value, "sfx")
            if vol is not None:
                self.window.audio.set_sfx_volume(vol)
                self.window.engine_config.sfx_volume = vol
                self.log(f"SFX volume set to {vol:.2f}")
            return

        if key == "music":
            vol = self._parse_float(value, "music")
            if vol is not None:
                self.window.audio.set_music_volume(vol)
                self.window.engine_config.music_volume = vol
                self.log(f"Music volume set to {vol:.2f}")
            return

        if key == "fullscreen":
            is_fs = value in ("1", "true", "yes", "on")
            self.window.set_fullscreen(is_fs)
            self.window.engine_config.fullscreen = is_fs
            self.log(f"Fullscreen set to {is_fs}")
            return

        if key == "vsync":
            is_vsync = value in ("1", "true", "yes", "on")
            self.window.set_vsync(is_vsync)
            self.window.engine_config.vsync = is_vsync
            self.log(f"VSync set to {is_vsync}")
            return

        if key == "show_fps":
            self.log("show_fps not implemented")
            return

        if key == "debug_on_start":
            is_debug = value in ("1", "true", "yes", "on")
            self.window.engine_config.debug_on_start = is_debug
            self.log(f"debug_on_start set to {is_debug}")
            return

        self.log(f"Unknown setting: {key}")

    def _save_config_to_disk(self) -> None:
        from .config import save_config
        try:
            save_config(self.window.engine_config, self.window.config_path)
            self.log(f"Config saved to {self.window.config_path}")
        except Exception as e:
            self.log(f"Error saving config: {e}")
