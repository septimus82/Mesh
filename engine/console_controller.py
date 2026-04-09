"""Console controller for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING
import engine.optional_arcade as optional_arcade

from .console_runtime import commands as console_commands
from .console_runtime import history as console_history
from .console_runtime import render as console_render
from .logging_tools import get_logger

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

    # ------------------------------------------------------------------
    # Trivial handlers still dispatched via lambda in commands.py
    # ------------------------------------------------------------------

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

    def _assets_command(self, args: list[str]) -> None:
        if args and args[0] == "clear":
            self.window.assets.clear()
            self.log("Texture cache cleared")
            return

        count = self.window.assets.get_cache_size()
        self.log(f"Assets: {count} textures cached")

