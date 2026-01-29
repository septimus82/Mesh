"""Menu and modal UI overlays."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence
import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..input_hints import get_action_hint, set_keyboard_hints
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

logger = logging.getLogger(__name__)
_LOG_ONCE: set[str] = set()


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def get_menu_legend(input_source: str) -> str:
    source = str(input_source or "").strip().lower()
    if source == "gamepad":
        return "A Select  B Back  D-pad Navigate"
    return "Enter Select  Esc Back  Up/Down Navigate"


class HelpOverlay(UIElement):
    """Simple overlay that lists controls and common hotkeys."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self._body_text = self._build_body_text()
        self._text_cache = TextCache()

    def _build_body_text(self) -> str:
        lines = [
            "Movement: W A S D",
            "Interact: E",
            "Attack: Space",
            "",
            "Q: Quest Log",
            "Tab: Inventory",
            "I: Inspector",
            "C: Character",
            "F2: Editor",
            "H: Help",
            "V: Golden Slice Variants",
            "",
            "F1: Command Palette (Debug)",
            "~ / Insert: Dev Console (Debug)",
            "F3: Toggle Debug Mode",
            "Esc: Pause",
            "",
            "Lighting demos:",
            "mesh run-preset lighting-shadowmask-demo",
            "mesh run-preset lighting-shadowmask-demo-debug",
        ]
        return "\n".join(lines)

    def toggle(self) -> bool:
        self.visible = not self.visible
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if key in (optional_arcade.arcade.key.H, optional_arcade.arcade.key.ESCAPE):
            self.toggle() if key == optional_arcade.arcade.key.H else self.set_visible(False)
            return True
        return True

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(620.0, max(360.0, self.window.width - 120.0))
        height = min(420.0, max(240.0, self.window.height - 160.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 210),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        text_left = left + 40.0
        title_y = top - 20.0
        draw_text_cached(
            "Help / Controls",
            text_left,
            title_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_y="top",
            cache=self._text_cache,
        )
        input_source = "keyboard_mouse"
        manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
        if manager is not None:
            input_source = str(getattr(manager, "input_source", input_source))
        bindings = getattr(getattr(self.window, "input_controller", None), "get_bindings_as_names", None)
        if callable(bindings):
            set_keyboard_hints(bindings())
        hint_parts = []
        for action, label in (
            ("interact", "Interact"),
            ("toggle_help", "Back"),
            ("attack", "Attack"),
            ("pause_menu", "Pause"),
        ):
            hint = get_action_hint(action, input_source)
            if hint:
                hint_parts.append(f"{hint} {label}")
        if hint_parts:
            draw_text_cached(
                "  ".join(hint_parts),
                text_left,
                title_y - 26.0,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=13,
                anchor_y="top",
                cache=self._text_cache,
            )
        draw_text_cached(
            self._body_text,
            text_left,
            title_y - 40.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=13,
            width=int(width - 80.0),
            multiline=True,
            anchor_y="top",
            cache=self._text_cache,
        )


class SettingsOverlay(UIElement):
    """
    Minimal settings UI (keyboard-only).

    - ESC: open/close
    - Up/Down: navigate
    - Enter: remap keybind / activate close
    - Left/Right: adjust volume
    """

    _ACTIONS: tuple[str, ...] = (
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "interact",
        "attack",
    )

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._paused_before_open: bool = False
        self._selection_index: int = 0
        self._capture_action: str | None = None
        self._dirty: bool = False
        self._text_cache = TextCache()

        from ..settings import load_settings, resolve_settings_path  # noqa: PLC0415

        self._settings_path = resolve_settings_path()
        self.settings = load_settings(self._settings_path)

        self._rows: list[tuple[str, str]] = []
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        self._rows = [(f"Keybind: {action}", action) for action in self._ACTIONS]
        self._rows.extend(
            [
                ("Audio: SFX Volume", "sfx_volume"),
                ("Audio: Music Volume", "music_volume"),
                ("Save & Close", "close"),
            ]
        )

    @property
    def blocks_input(self) -> bool:
        return bool(self.visible)

    def toggle(self) -> bool:
        if self.visible:
            self.close()
        else:
            self.open()
        return self.visible

    def open(self) -> None:
        self.visible = True
        self._paused_before_open = bool(getattr(self.window, "paused", False))
        setattr(self.window, "paused", True)
        self._selection_index = 0
        self._capture_action = None
        self._dirty = False

    def close(self) -> None:
        self.visible = False
        self._capture_action = None
        if not self._paused_before_open:
            setattr(self.window, "paused", False)
        self._paused_before_open = False
        if self._dirty:
            self.save()
        self._dirty = False

    def save(self) -> None:
        from ..settings import save_settings  # noqa: PLC0415

        save_settings(self._settings_path, self.settings)

    def apply(self) -> None:
        from ..settings import apply_settings  # noqa: PLC0415

        apply_settings(self.window, self.settings)

    def _key_name(self, code: int | None) -> str:
        if code is None:
            return "-"
        try:
            return str(optional_arcade.arcade.key.key_string(int(code)))
        except Exception:
            return str(code)

    def get_lines(self) -> list[str]:
        from ..settings import resolve_settings_path  # noqa: PLC0415

        rows: list[str] = ["Settings (ESC)"]
        rows.append(f"path: {resolve_settings_path(self._settings_path).as_posix()}")
        rows.append("")
        for idx, (label, key) in enumerate(self._rows):
            prefix = ">" if idx == self._selection_index else " "
            suffix = ""
            if key in self._ACTIONS:
                code = self.settings.keybinds.get(key)
                if code is None:
                    manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
                    get_bindings = getattr(manager, "get_bindings", None) if manager is not None else None
                    bindings = get_bindings() if callable(get_bindings) else {}
                    codes = bindings.get(key, []) if isinstance(bindings, dict) else []
                    code = int(codes[0]) if codes else None
                suffix = f": {self._key_name(code)}"
                if self._capture_action == key:
                    suffix = ": [press a key...]"
            elif key == "sfx_volume":
                suffix = f": {int(round(float(self.settings.sfx_volume) * 100.0)):d}%"
            elif key == "music_volume":
                suffix = f": {int(round(float(self.settings.music_volume) * 100.0)):d}%"
            rows.append(f"{prefix} {label}{suffix}")
        return rows

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False

        if self._capture_action is not None:
            if key == optional_arcade.arcade.key.ESCAPE:
                self._capture_action = None
                return True

            action = self._capture_action
            self._capture_action = None
            self.settings.keybinds[str(action)] = int(key)
            self.apply()
            self._dirty = True
            return True

        if key == optional_arcade.arcade.key.ESCAPE:
            self.close()
            return True

        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
            self._selection_index = (self._selection_index - 1) % len(self._rows)
            return True
        if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
            self._selection_index = (self._selection_index + 1) % len(self._rows)
            return True

        _, row_key = self._rows[self._selection_index]
        if row_key in ("sfx_volume", "music_volume") and key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.MINUS, optional_arcade.arcade.key.EQUAL):
            delta = 0.05 if key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.EQUAL) else -0.05
            if row_key == "sfx_volume":
                self.settings.sfx_volume = max(0.0, min(1.0, float(self.settings.sfx_volume) + delta))
            else:
                self.settings.music_volume = max(0.0, min(1.0, float(self.settings.music_volume) + delta))
            self.apply()
            self._dirty = True
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            if row_key in self._ACTIONS:
                self._capture_action = str(row_key)
                return True
            if row_key == "close":
                self.close()
                return True

        return True

    def draw(self) -> None:
        if not self.visible:
            return

        lines = self.get_lines()
        text = "\n".join(lines)

        width = min(680.0, max(440.0, self.window.width - 80.0))
        height = min(520.0, max(280.0, self.window.height - 140.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 210),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        draw_text_cached(
            text,
            left + 20.0,
            top - 20.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=14,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )


class MainMenuOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._selection_index = 0
        self.state = "main"  # project_browser, main, settings
        self._settings_index = 0
        self._project_index = 0
        self._create_name: str = ""
        self._create_path: str = ""
        self._create_error: str = ""
        self._create_template_id: str = "blank"
        self._template_index: int = 0
        self._open_path: str = ""
        self._open_error: str = ""
        self._title = optional_arcade.arcade.Text(
            text="MAIN MENU",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_y="top",
            anchor_x="center",
        )
        self._text_lines: list[Any] = []  # Cache for arcade.Text objects
        self._cache_valid: bool = False
        self._settings_text_cache = TextCache()

    @property
    def blocks_input(self) -> bool:
        return bool(self.visible)

    def open(self) -> None:
        self.visible = True
        self._selection_index = 0
        self._project_index = 0
        self.state = "main" if _is_web_runtime() else "project_browser"
        self._settings_index = 0
        self._cache_valid = False
        setattr(self.window, "paused", True)

    def close(self) -> None:
        self.visible = False
        self.state = "main"
        setattr(self.window, "paused", False)

    def _project_items(self) -> list[dict[str, str]]:
        from ..projects import get_recent_projects  # noqa: PLC0415
        from ..repo_root import get_repo_root  # noqa: PLC0415

        items: list[dict[str, str]] = []
        for root in get_recent_projects():
            label = Path(root).name or root
            items.append({"root": root, "label": label, "kind": "recent"})

        current_root = str(get_repo_root())
        items.append({"root": current_root, "label": "Use current repo", "kind": "current"})

        if not _is_web_runtime():
            items.append({"root": "", "label": "Create New Project...", "kind": "create"})
            items.append({"root": "", "label": "Open Existing Project...", "kind": "open"})
        return items

    def _apply_project_root(self, root: str) -> None:
        from ..paths import reset_path_caches  # noqa: PLC0415
        from ..projects import add_recent_project, set_last_project  # noqa: PLC0415

        root_text = str(root or "").strip()
        if not root_text:
            return
        editor = getattr(self.window, "editor_controller", None)
        flusher = getattr(editor, "_flush_workspace_autosave", None) if editor is not None else None
        if callable(flusher):
            flusher()
        os.environ["MESH_REPO_ROOT"] = root_text
        reset_path_caches()
        add_recent_project(root_text)
        set_last_project(root_text)

        # Reload config and world from the new project root
        self._reload_project_config()

        # Reload workspace settings if editor is present
        # This restores last scene, panels, etc.
        if hasattr(self.window, "editor") and callable(getattr(self.window.editor, "load_workspace", None)):
            self.window.editor.load_workspace()

    def _reload_project_config(self) -> None:
        """Reload the engine config and world controller from the current project root."""
        import json
        from ..config import load_config  # noqa: PLC0415
        from ..paths import resolve_path  # noqa: PLC0415
        from ..migrations import migrate_payload  # noqa: PLC0415
        from ..world_controller import WorldController  # noqa: PLC0415

        # Reload config
        new_config = load_config()
        self.window.engine_config = new_config

        # Reload world controller
        world_file = getattr(new_config, "world_file", None)
        if world_file:
            try:
                path = resolve_path(world_file)
                if path.exists():
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    raw = migrate_payload("world", raw)
                    self.window.world_controller = WorldController(raw)
                    logger.info(
                        "[MainMenu] Reloaded world '%s' from %s",
                        self.window.world_controller.id,
                        world_file,
                    )
                else:
                    self.window.world_controller = None
                    logger.warning("[MainMenu] World file not found: %s", world_file)
            except Exception as exc:
                self.window.world_controller = None
                logger.error("[MainMenu] Failed to reload world '%s': %s", world_file, exc)
        else:
            self.window.world_controller = None

    def _activate_project_selection(self) -> None:
        items = self._project_items()
        if not items:
            self.state = "main"
            self._selection_index = 0
            return
        self._project_index = max(0, min(self._project_index, len(items) - 1))
        selected = items[self._project_index]

        if selected.get("kind") == "create":
            self.state = "create_project_template"
            self._create_name = ""
            self._create_path = ""
            self._create_error = ""
            self._create_template_id = "blank"
            self._template_index = 0
            return

        if selected.get("kind") == "open":
            self.state = "open_project_path"
            self._open_path = ""
            self._open_error = ""
            return

        self._apply_project_root(selected["root"])
        self.state = "main"
        self._selection_index = 0

    def on_text(self, text: str) -> None:
        if not self.visible:
            return
        
        logger.info("[MainMenu] on_text received: '%s' (state=%s)", text, self.state)

        if self.state == "create_project_name":
            # Filter out disallowed characters for filenames
            filtered = "".join(ch for ch in text if ch.isprintable() and ch not in "\\/:*?\"<>|")
            self._create_name += filtered
            self._cache_valid = False
            return

        if self.state == "create_project_path":
            # Allow path characters
            filtered = "".join(ch for ch in text if ch.isprintable())
            self._create_path += filtered
            self._cache_valid = False
            return

        if self.state == "open_project_path":
            # Allow path characters
            filtered = "".join(ch for ch in text if ch.isprintable())
            self._open_path += filtered
            self._cache_valid = False
            return

    def _attempt_create_project(self) -> None:
        from ..project_scaffold import create_project, validate_new_project_target  # noqa: PLC0415

        path = Path(self._create_path)
        valid, msg = validate_new_project_target(path)
        if not valid:
            self._create_error = msg
            return

        try:
            create_project(path, self._create_name, template_id=self._create_template_id)
            self._apply_project_root(str(path))
            self._create_error = ""
            self._handle_start_game_impl()
        except Exception as e:
            self._create_error = str(e)

    def _attempt_open_project(self) -> None:
        from ..projects import is_valid_project_root  # noqa: PLC0415

        path = Path(self._open_path)
        if not is_valid_project_root(path):
            self._open_error = "Invalid project directory (missing config.json or packs/)"
            return

        self._apply_project_root(str(path))
        self.state = "main"
        self._open_error = ""

    def _has_continue(self) -> bool:
        try:
            from ..savegame import load_savegame, resolve_savegame_path  # noqa: PLC0415

            if _is_web_runtime():
                return False
            if os.environ.get("PYTEST_CURRENT_TEST"):
                if not (os.environ.get("MESH_SAVEGAME_PATH") or os.environ.get("MESH_SAVE_PATH")):
                    return False
            return load_savegame(resolve_savegame_path()) is not None
        except Exception:
            return False

    def _items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self._has_continue():
            items.append(("Continue", "continue"))
        items.extend(
            [
                ("Start Game", "start_game"),
                ("Settings", "settings"),
            ]
        )
        if not _is_web_runtime():
            items.append(("Run Web Demo (Local Preview)", "run_web_preview"))
            items.append(("Export Web Demo (.zip)", "export_web"))
            items.append(("Quit", "quit"))
        return items

    def get_lines(self) -> list[str]:
        if self.state == "project_browser":
            project_items = self._project_items()
            lines = ["PROJECT BROWSER", ""]
            if not project_items:
                lines.append("  (No projects)")
            else:
                for idx, item in enumerate(project_items):
                    prefix = ">" if idx == self._project_index else " "
                    label = item["label"]
                    root = item["root"]
                    lines.append(f"{prefix} {label} ({root})")
            lines.append("")

            input_source = "keyboard_mouse"
            manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
            if manager is not None:
                input_source = str(getattr(manager, "input_source", input_source))
            lines.append(get_menu_legend(input_source))
            return lines

        if self.state == "create_project_template":
            from ..project_templates import list_templates  # noqa: PLC0415
            templates = list_templates()
            lines = [
                "CREATE NEW PROJECT",
                "",
                "Choose Template:",
                ""
            ]
            
            for idx, tmpl in enumerate(templates):
                prefix = ">" if idx == self._template_index else " "
                lines.append(f"{prefix} {tmpl.title}")
            
            lines.append("")
            if 0 <= self._template_index < len(templates):
                desc = templates[self._template_index].description
                lines.append(f"Info: {desc}")
                
            lines.append("")
            lines.append("[Enter] Next  [Esc] Cancel")
            return lines

        if self.state == "create_project_name":
            return [
                "CREATE NEW PROJECT",
                "",
                "Enter Project Name:",
                f"> {self._create_name}_",
                "",
                "[Enter] Next  [Esc] Cancel"
            ]

        if self.state == "create_project_path":
            lines = [
                "CREATE NEW PROJECT",
                "",
                "Enter Project Path:",
                f"> {self._create_path}_",
                "",
                "[Enter] Create  [Esc] Cancel"
            ]
            if self._create_error:
                lines.append("")
                lines.append(f"Error: {self._create_error}")
            return lines

        if self.state == "open_project_path":
            lines = [
                "OPEN EXISTING PROJECT",
                "",
                "Enter Project Path:",
                f"> {self._open_path}_",
                "",
                "[Enter] Open  [Esc] Cancel"
            ]
            if self._open_error:
                lines.append("")
                lines.append(f"Error: {self._open_error}")
            return lines

        if self.state == "settings":
            return []

        menu_items = self._items()
        lines = ["TITLE SCREEN", ""]
        for idx, (label, _) in enumerate(menu_items):
            prefix = ">" if idx == self._selection_index else " "
            lines.append(f"{prefix} {label}")
        lines.append("")

        input_source = "keyboard_mouse"
        manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
        if manager is not None:
            input_source = str(getattr(manager, "input_source", input_source))
        lines.append(get_menu_legend(input_source))
        return lines

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False

        self._cache_valid = False

        if self.state == "project_browser":
            project_items = self._project_items()
            if not project_items:
                return True
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                self._project_index = max(0, self._project_index - 1)
                return True
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                self._project_index = min(len(project_items) - 1, self._project_index + 1)
                return True
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                self._activate_project_selection()
                return True
            # Remove recent project (Shift+Delete or Gamepad X - logic handled here via key binding only for now)
            # Or dedicated key. Let's use Delete.
            if key == optional_arcade.arcade.key.DELETE:
                self._remove_selected_project()
                return True
            return True

        if self.state == "create_project_template":
            from ..project_templates import list_templates  # noqa: PLC0415
            templates = list_templates()
            
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                self._template_index = max(0, self._template_index - 1)
                return True
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                self._template_index = min(len(templates) - 1, self._template_index + 1)
                return True
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                if 0 <= self._template_index < len(templates):
                    self._create_template_id = templates[self._template_index].id
                    self.state = "create_project_name"
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self.state = "project_browser"
                return True
            return True

        if self.state == "create_project_name":
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._create_name = self._create_name[:-1]
                return True
            if key == optional_arcade.arcade.key.ENTER:
                if self._create_name.strip():
                    self.state = "create_project_path"
                    # Propose a default path
                    safe_name = self._create_name.strip().replace(" ", "_").lower()
                    self._create_path = str((Path.cwd() / safe_name).resolve())
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self.state = "create_project_template"
                self._create_name = ""
                return True
            return True

        if self.state == "create_project_path":
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._create_path = self._create_path[:-1]
                self._create_error = ""
                return True
            if key == optional_arcade.arcade.key.ENTER:
                if self._create_path.strip():
                    self._attempt_create_project()
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self.state = "create_project_name"
                self._create_error = ""
                return True
            return True

        if self.state == "open_project_path":
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._open_path = self._open_path[:-1]
                self._open_error = ""
                return True
            if key == optional_arcade.arcade.key.ENTER:
                if self._open_path.strip():
                    self._attempt_open_project()
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self.state = "project_browser"
                self._open_error = ""
                return True
            return True

        if self.state == "settings":
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_settings_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_settings_action("down")
            if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.MINUS):
                return self._handle_settings_action(
                    "left",
                    large_step=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT),
                )
            if key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.EQUAL):
                return self._handle_settings_action(
                    "right",
                    large_step=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT),
                )
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_settings_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_settings_action("back")
            return True

        items = self._items()
        if not items:
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self.state = "settings"
            self._settings_index = 0
            return True

        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
            self._move_selection(-1)
            return True
        if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
            self._move_selection(1)
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            self._activate_current()
            return True

        return True

    def _remove_selected_project(self) -> None:
        from ..projects import remove_recent_project, get_repo_root

        items = self._project_items()
        if not items:
            return
        
        # Ensure index is valid
        self._project_index = max(0, min(self._project_index, len(items) - 1))
        selected = items[self._project_index]
        
        if selected.get("kind") == "recent":
            remove_recent_project(selected["root"])
            # Adjust index if it would be out of bounds after removal?
            # Actually next frame redraw will pick up the smaller list.
            # But we should clamp index immediately to avoid flash of weird selection or invalid state
            # if we were at the end.
            # Refresh items immediately to know new size
            new_items = self._project_items()
            self._project_index = max(0, min(self._project_index, len(new_items) - 1))

    def _handle_continue(self) -> None:
        try:
            from ..savegame import apply_savegame, load_savegame, resolve_savegame_path  # noqa: PLC0415

            save = load_savegame(resolve_savegame_path())
            if save is None:
                return
            if self._confirm_unsaved_action("Load Game", lambda: apply_savegame(self.window, save.to_payload())):
                return
            apply_savegame(self.window, save.to_payload())
            self.close()
        except Exception:
            return

    def _handle_start_game(self) -> None:
        if self._confirm_unsaved_action("Start Game", self._handle_start_game_impl):
            return
        self._handle_start_game_impl()

    def _confirm_unsaved_action(self, reason: str, action) -> bool:
        editor = getattr(self.window, "editor_controller", None)
        if editor is None or not getattr(editor, "active", False):
            return False
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker(reason, action)
            return isinstance(blocked, bool) and blocked
        return False

    def _handle_start_game_impl(self) -> None:
        state = getattr(getattr(self.window, "game_state_controller", None), "state", None)
        if state is not None and hasattr(state, "flags"):
            try:
                state.flags = {}
            except Exception:
                pass
        for key in (
            "_mesh_demo_complete_endcap_seen",
            "_mesh_demo_interior_hint_shown",
            "_mesh_demo_interior_hint_start_time",
        ):
            if hasattr(self.window, key):
                try:
                    delattr(self.window, key)
                except Exception:
                    pass

        target_scene: str | None = None
        world = getattr(self.window, "world_controller", None)
        if world is not None:
            getter = getattr(world, "get_start_scene_key", None)
            start_key = getter() if callable(getter) else None
            path_getter = getattr(world, "get_scene_path", None)
            if start_key and callable(path_getter):
                try:
                    target_scene = str(path_getter(start_key) or "").strip() or None
                except Exception:
                    target_scene = None

        if target_scene is None:
            cfg = getattr(self.window, "engine_config", None)
            target_scene = str(getattr(cfg, "start_scene", "") or "").strip() or None

        requester = getattr(self.window, "request_scene_change", None)
        if callable(requester) and target_scene is not None:
            requester(target_scene)
            self.close()

    def _rebuild_text_cache(self, left: float, top: float) -> None:
        self._text_lines.clear()
        lines = self.get_lines()
        text_x = left + 24.0
        text_y = top - 24.0
        line_height = 20.0

        for line in lines:
            t = optional_arcade.arcade.Text(
                text=line,
                x=text_x,
                y=text_y,
                color=optional_arcade.arcade.color.WHITE,
                font_size=16,
                anchor_y="top",
                font_name=("Consolas", "Courier New", "Courier"),
            )
            self._text_lines.append(t)
            text_y -= line_height
        self._cache_valid = True

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(560.0, max(320.0, self.window.width - 120.0))
        height = min(380.0, max(240.0, self.window.height - 200.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 220),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        if self.state == "settings":
            self._draw_settings_menu()
            return

        if not self._cache_valid:
            self._rebuild_text_cache(left, top)

        for text_obj in self._text_lines:
            text_obj.draw()

    def update(self, dt: float) -> None:  # noqa: ARG002
        if not self.visible:
            return
        manager = getattr(self.window, "input", None)
        if manager is None:
            return
        if getattr(manager, "input_source", "keyboard_mouse") != "gamepad":
            return

        if self.state == "settings":
            if manager.was_action_pressed("move_up"):
                self._handle_settings_action("up")
            if manager.was_action_pressed("move_down"):
                self._handle_settings_action("down")
            if manager.was_action_pressed("move_left"):
                self._handle_settings_action("left")
            if manager.was_action_pressed("move_right"):
                self._handle_settings_action("right")
            if manager.was_action_pressed("interact"):
                self._handle_settings_action("confirm")
            if manager.was_action_pressed("toggle_help"):
                self._handle_settings_action("back")
            return

        if manager.was_action_pressed("move_up"):
            self._move_selection(-1)
        if manager.was_action_pressed("move_down"):
            self._move_selection(1)
        if manager.was_action_pressed("interact"):
            self._activate_current()
        if manager.was_action_pressed("toggle_help"):
            self.state = "settings"
            self._settings_index = 0
            self._cache_valid = False

    def _move_selection(self, delta: int) -> None:
        items = self._items()
        if not items:
            self._selection_index = 0
            return
        next_index = self._selection_index + int(delta)
        if next_index < 0:
            next_index = 0
        if next_index >= len(items):
            next_index = len(items) - 1
        self._selection_index = next_index
        self._cache_valid = False

    def _activate_current(self) -> None:
        items = self._items()
        if not items:
            return
        _, action = items[self._selection_index]
        if action == "continue":
            self._handle_continue()
            return
        if action == "start_game":
            self._handle_start_game()
            return
        if action == "settings":
            self.state = "settings"
            self._settings_index = 0
            return
        if action == "run_web_preview":
            self._attempt_run_web_preview()
            return
        if action == "export_web":
            self._attempt_export_web_demo()
            return
        if action == "quit":
            try:
                optional_arcade.arcade.close_window()
            except Exception:
                pass
            return

    def _attempt_export_web_demo(self) -> None:
        try:
            from tooling.release_web_demo import build_and_zip_web_demo  # noqa: PLC0415
        except ImportError:
            logger.warning("Export tool missing (tooling.release_web_demo)")
            return

        from ..repo_root import get_repo_root  # noqa: PLC0415
        
        repo_root = get_repo_root()
        logger.info("Exporting web demo for %s", repo_root)

        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        
        # We assume build_and_zip_web_demo is blocking for v1
        try:
            out_zip = build_and_zip_web_demo(repo_root)
            if callable(enqueue):
                enqueue(f"Exported: {out_zip.name}", seconds=4.0)
        except Exception as e:
            logger.error("Export failed", exc_info=True)
            if callable(enqueue):
                msg = str(e) or "Check logs"
                enqueue(f"Export Failed: {msg}", seconds=4.0)
    def _attempt_run_web_preview(self) -> None:
        try:
            from tooling.web_preview import start_web_preview  # noqa: PLC0415
        except ImportError:
            logger.warning("Preview tool missing (tooling.web_preview)")
            return

        from ..repo_root import get_repo_root  # noqa: PLC0415
        
        repo_root = get_repo_root()
        logger.info("Starting web preview for %s", repo_root)

        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        
        try:
            _, url = start_web_preview(repo_root)
            if callable(enqueue):
                enqueue(f"Preview: {url}", seconds=5.0)
        except FileNotFoundError:
            if callable(enqueue):
                enqueue("Build web demo first", seconds=3.0)
        except Exception as e:
            logger.error("Preview failed", exc_info=True)
            if callable(enqueue):
                enqueue(f"Preview Failed: {e}", seconds=4.0)

    def _runtime_settings(self):
        from ..runtime_settings import ensure_runtime_settings  # noqa: PLC0415

        return ensure_runtime_settings(self.window)

    def _apply_runtime_settings(self) -> None:
        settings = self._runtime_settings()
        settings.apply(self.window)
        saver = getattr(self, "_save_runtime_settings", None)
        if callable(saver):
            saver()

    def _save_runtime_settings(self) -> None:
        from ..runtime_settings_storage import save_runtime_settings  # noqa: PLC0415
        from ..i18n import tr  # noqa: PLC0415

        path = getattr(self.window, "runtime_settings_path", None)
        settings = self._runtime_settings()
        save_runtime_settings(path, settings)
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue):
            enqueue(tr("UI_SETTINGS_SAVED"), seconds=2.0)

    def _handle_settings_action(self, action: str, *, large_step: bool = False) -> bool:
        action = str(action)
        if action == "up":
            self._settings_index = (self._settings_index - 1) % len(PauseMenu._SETTINGS_ROWS)
            return True
        if action == "down":
            self._settings_index = (self._settings_index + 1) % len(PauseMenu._SETTINGS_ROWS)
            return True
        if action in ("left", "right"):
            delta = 0.1 if large_step else 0.05
            if action == "left":
                delta = -delta
            return self._adjust_setting(delta)
        if action == "confirm":
            return self._confirm_setting()
        if action == "back":
            self.state = "main"
            self._cache_valid = False
            return True
        return False

    def _adjust_setting(self, delta: float) -> bool:
        key, _label, kind = PauseMenu._SETTINGS_ROWS[self._settings_index]
        settings = self._runtime_settings()
        if kind != "slider":
            return False
        if key == "music_volume":
            settings.music_volume = max(0.0, min(1.0, float(settings.music_volume) + delta))
        elif key == "sfx_volume":
            settings.sfx_volume = max(0.0, min(1.0, float(settings.sfx_volume) + delta))
        else:
            return False
        self._apply_runtime_settings()
        return True

    def _confirm_setting(self) -> bool:
        key, _label, kind = PauseMenu._SETTINGS_ROWS[self._settings_index]
        settings = self._runtime_settings()
        if kind == "toggle":
            current = bool(getattr(settings, key, False))
            setattr(settings, key, not current)
            self._apply_runtime_settings()
            return True
        if kind == "action" and key == "back":
            self.state = "main"
            return True
        return False

    def _draw_settings_menu(self) -> None:
        self._title.text = "SETTINGS"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 120
        self._title.draw()

        settings = self._runtime_settings()
        start_y = self.window.height / 2 + 40
        for i, (key, label, kind) in enumerate(PauseMenu._SETTINGS_ROWS):
            color = optional_arcade.arcade.color.YELLOW if i == self._settings_index else optional_arcade.arcade.color.GRAY
            value = ""
            if kind == "slider":
                if key == "music_volume":
                    value = f"{int(round(settings.music_volume * 100.0))}%"
                elif key == "sfx_volume":
                    value = f"{int(round(settings.sfx_volume * 100.0))}%"
            elif kind == "toggle":
                enabled = bool(getattr(settings, key, False))
                value = "ON" if enabled else "OFF"
            text = f"{label}: {value}" if value else label
            draw_text_cached(
                text,
                self.window.width / 2,
                start_y - i * 36,
                color=color,
                font_size=18,
                anchor_x="center",
                anchor_y="center",
                cache=self._settings_text_cache,
            )

        draw_text_cached(
            "Enter/A: Toggle   Left/Right: Adjust   Esc/B: Back",
            self.window.width / 2,
            50,
            color=optional_arcade.arcade.color.GRAY,
            font_size=14,
            anchor_x="center",
            cache=self._settings_text_cache,
        )


DEMO_COMPLETE_ENDCAP_SECONDS = 4.0


class DemoCompleteOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._remaining_seconds = 0.0
        self._text_cache = TextCache()

    def show(self, *, seconds: float = DEMO_COMPLETE_ENDCAP_SECONDS) -> None:
        self.visible = True
        self._remaining_seconds = max(0.0, float(seconds))

    def update(self, dt: float) -> None:
        if not self.visible:
            return
        self._remaining_seconds -= float(dt)
        if self._remaining_seconds <= 0.0:
            self.visible = False
            self._remaining_seconds = 0.0

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(560.0, max(320.0, self.window.width - 80.0))
        height = 100.0
        left = (self.window.width - width) / 2.0
        right = left + width
        top = self.window.height - 70.0
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 190),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.GOLD, 2)

        draw_text_cached(
            "DEMO COMPLETE",
            (left + right) / 2.0,
            (top + bottom) / 2.0 + 6.0,
            color=optional_arcade.arcade.color.GOLD,
            font_size=20,
            anchor_x="center",
            anchor_y="center",
            bold=True,
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )
        draw_text_cached(
            "Thanks for playing!",
            (left + right) / 2.0,
            (top + bottom) / 2.0 - 18.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=12,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )


def maybe_trigger_demo_complete_endcap(
    window: Any,
    *,
    previous: bool,
    current: bool,
    seconds: float = DEMO_COMPLETE_ENDCAP_SECONDS,
) -> bool:
    """
    Trigger a one-shot "Demo Complete" end-cap on a false->true transition.

    This is intentionally UI-only and safe to call from stub windows in tests.
    """

    if bool(previous):
        return False
    if not bool(current):
        return False

    if bool(getattr(window, "_mesh_demo_complete_endcap_seen", False)):
        return False
    setattr(window, "_mesh_demo_complete_endcap_seen", True)

    overlay = getattr(window, "demo_complete_overlay", None)
    show = getattr(overlay, "show", None) if overlay is not None else None
    if callable(show):
        show(seconds=float(seconds))
        return True
    return False


class DialogueBox(UIElement):
    """Simple bottom overlay that shows speaker-tagged dialogue lines."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._queue: list[dict[str, Any]] = []
        self._visible: bool = False
        self._owner: str | None = None
        self._current_entry: dict[str, Any] | None = None
        self._choices: list[dict[str, Any]] = []
        self._choice_index: int = -1
        self._choice_locked: bool = False
        self._text_cache = TextCache()
        speaker_color = getattr(optional_arcade.arcade.color, "ALPINE", optional_arcade.arcade.color.WHITE)
        self._speaker_text = optional_arcade.arcade.Text(
            text="",
            x=0,
            y=0,
            color=speaker_color,
            font_size=16,
            anchor_y="top",
            bold=True,
        )
        self._body_text = optional_arcade.arcade.Text(
            text="",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
            width=10,
            align="left",
            multiline=True,
            anchor_y="top",
        )

    def is_active(self) -> bool:
        return self._visible

    @property
    def blocks_input(self) -> bool:
        return self._visible

    def is_active_for(self, owner: str) -> bool:
        return self._visible and self._owner == owner

    def get_current_entry(self) -> dict[str, Any] | None:
        if not self._visible or self._current_entry is None:
            return None
        entry = dict(self._current_entry)
        if "choices" in self._current_entry:
            entry["choices"] = [dict(choice) for choice in self._current_entry["choices"]]
        return entry

    def play(self, entries: Sequence[dict[str, Any]], *, owner: str) -> bool:
        normalized = [entry for entry in (self._coerce_entry(value) for value in entries) if entry]
        if not normalized:
            self.clear(owner=owner)
            return False
        self._queue = normalized[1:]
        self._owner = owner
        self._visible = True
        self._apply_entry(normalized[0])

        if hasattr(self.window, "audio"):
            self.window.audio.play_sound("assets/sounds/ui_open.wav")

        return True

    def advance(self, *, owner: str | None = None) -> bool:
        if owner is not None and owner != self._owner:
            return False
        if not self._visible:
            return False
        if self._choices:
            return False
        if self._queue:
            self._apply_entry(self._queue.pop(0))
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_click.wav")
            return True
        self.clear(owner=owner)
        return False

    def clear(self, *, owner: str | None = None) -> None:
        if owner is not None and owner != self._owner:
            return
        self._queue.clear()
        self._visible = False
        self._owner = None
        self._current_entry = None
        self._choices = []
        self._choice_index = -1
        self._choice_locked = False
        self._speaker_text.text = ""
        self._body_text.text = ""

    def close(self) -> None:
        self.clear()

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        self._speaker_text.y = self.window.height - 54
        self._speaker_text.x = 20
        self._body_text.y = self.window.height - 80
        self._body_text.x = 20

    def has_choices(self) -> bool:
        if not self._visible or not self._choices:
            return False
        if self._choice_locked:
            return False
        return any(not choice.get("disabled") for choice in self._choices)

    def move_choice_cursor(self, delta: int, *, owner: str | None = None) -> int | None:
        if not self._can_control_choices(owner):
            return None
        if delta == 0 or not self._choices:
            return self._choice_index if self._choice_index >= 0 else None
        count = len(self._choices)
        next_index = self._choice_index if self._choice_index >= 0 else 0
        attempts = 0
        while attempts < count:
            next_index = (next_index + delta) % count
            attempts += 1
            if not bool(self._choices[next_index].get("disabled")):
                if next_index != self._choice_index:
                    self._choice_index = next_index
                    if hasattr(self.window, "audio"):
                        self.window.audio.play_sound("assets/sounds/ui_hover.wav")
                return next_index
        return self._choice_index

    def get_choice_cursor(self, *, owner: str | None = None) -> int | None:
        if not self._can_control_choices(owner):
            return None
        return self._choice_index if self._choice_index >= 0 else None

    def submit_choice(self, *, owner: str | None = None) -> dict[str, Any] | None:
        if not self._can_control_choices(owner):
            return None
        if self._choice_index < 0 or self._choice_index >= len(self._choices):
            return None
        current = self._choices[self._choice_index]
        if bool(current.get("disabled")):
            return None
        self._choice_locked = True
        if hasattr(self.window, "audio"):
            self.window.audio.play_sound("assets/sounds/ui_click.wav")
        return dict(current)

    def get_choices(self) -> list[dict[str, Any]]:
        return [dict(choice) for choice in self._choices]

    def _can_control_choices(self, owner: str | None) -> bool:
        if not self._visible or not self._choices:
            return False
        if self._choice_locked:
            return False
        if self._owner is None:
            return False
        if owner is None:
            owner = self._owner
        return owner == self._owner

    def _coerce_entry(self, value: object) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        text = str(value.get("text", "")).strip()
        if not text:
            return None
        speaker = str(value.get("speaker", "")).strip()
        entry: dict[str, Any] = dict(value)
        entry["speaker"] = speaker
        entry["text"] = text
        choices = self._coerce_choices(entry.get("choices"))
        if choices:
            entry["choices"] = choices
        elif "choices" in entry:
            entry.pop("choices", None)
        return entry

    def _coerce_choices(self, value: object) -> list[dict[str, Any]]:
        if not isinstance(value, (list, tuple)):
            return []
        normalized: list[dict[str, Any]] = []
        auto_id = 0
        for raw in value:
            if isinstance(raw, str):
                text = raw.strip()
                if not text:
                    continue
                choice: dict[str, Any] = {"text": text}
            elif isinstance(raw, dict):
                text = str(raw.get("text", "")).strip()
                if not text:
                    continue
                choice = dict(raw)
                choice["text"] = text
            else:
                continue
            if "id" not in choice:
                choice["id"] = f"choice_{auto_id}"
            normalized.append(choice)
            auto_id += 1
        return normalized

    def _apply_entry(self, entry: dict[str, Any]) -> None:
        self._current_entry = dict(entry)
        if "choices" in entry:
            self._current_entry["choices"] = [dict(choice) for choice in entry["choices"]]
        self._speaker_text.text = entry.get("speaker", "")
        self._body_text.text = entry.get("text", "")
        choices = entry.get("choices") or []
        if isinstance(choices, list):
            self._choices = [dict(choice) for choice in choices]
        else:
            self._choices = []
        self._choice_locked = False
        self._choice_index = self._compute_initial_choice_index()

    def draw(self) -> None:
        if not self._visible:
            return
        width = max(320.0, self.window.width - 48.0)
        height = 150.0
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = 24.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=self.window.width / 2.0,
            center_y=bottom + height / 2.0,
            width=width,
            height=height,
            color=(10, 12, 20, 220),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        padding = 24.0
        self._speaker_text.x = left + padding
        self._speaker_text.y = top - padding / 2.0
        self._speaker_text.draw()

        self._body_text.x = left + padding
        self._body_text.y = top - padding - 16.0
        self._body_text.width = int(width - padding * 2.0)
        self._body_text.draw()

        if self._choices:
            choice_x = left + padding + 4.0
            choice_y = bottom + padding + 8.0
            line_height = 20.0
            max_choice_width = width - padding * 2.0 - 8.0
            for index, choice in enumerate(self._choices):
                text = choice.get("text", "")
                disabled = bool(choice.get("disabled"))
                is_selected = index == self._choice_index
                bg_alpha = 120 if is_selected else 0
                if bg_alpha:
                    _draw_rectangle_filled(
                        center_x=choice_x + max_choice_width / 2.0,
                        center_y=choice_y + line_height / 2.0,
                        width=max_choice_width,
                        height=line_height,
                        color=(80, 120, 200, bg_alpha),
                    )
                prefix = "➤" if is_selected else "·"
                color = optional_arcade.arcade.color.SKY_BLUE if is_selected else optional_arcade.arcade.color.LIGHT_GRAY
                if disabled:
                    color = optional_arcade.arcade.color.DARK_GRAY
                draw_text_cached(
                    f"{prefix} {text}",
                    choice_x,
                    choice_y,
                    color=color,
                    font_size=13,
                    anchor_y="bottom",
                    width=int(max_choice_width),
                    cache=self._text_cache,
                )
                choice_y += line_height

    def _compute_initial_choice_index(self) -> int:
        if not self._choices:
            return -1
        for idx, choice in enumerate(self._choices):
            if not bool(choice.get("disabled")):
                return idx
        return -1


class ShopPanel(UIElement):
    """Simple shop overlay listing vendor stock and handling purchases."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self.vendor: Any = None
        self._items: list[dict[str, Any]] = []
        self._cursor_index: int = 0
        self._mode: str = "buy"  # or "sell"
        self._text_cache = TextCache()

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def open(self, vendor: Any, items: list[dict[str, Any]], mode: str = "buy") -> None:
        self.vendor = vendor
        self._items = list(items)
        self._cursor_index = 0
        self._mode = "buy" if mode not in {"buy", "sell"} else mode
        self.visible = True
        if self._mode == "sell":
            self._refresh_items()

    def close(self) -> None:
        self.visible = False
        self.vendor = None
        self._items = []
        self._cursor_index = 0
        self._mode = "buy"

    def set_mode(self, mode: str) -> None:
        if mode not in {"buy", "sell"}:
            return
        if self._mode == mode:
            return
        self._mode = mode
        self._cursor_index = 0
        self._refresh_items()

    def toggle_mode(self) -> None:
        self.set_mode("sell" if self._mode == "buy" else "buy")

    def _refresh_items(self) -> None:
        vendor = self.vendor
        if vendor is None:
            self._items = []
            return
        if self._mode == "sell":
            gs = getattr(self.window, "game_state_controller", None)
            values = gs.state.values if gs is not None else {}
            getter = getattr(vendor, "get_sellable_items", None)
            if callable(getter):
                self._items = getter(values)
        else:
            self._items = getattr(vendor, "stock", [])
        if not self._items:
            self._cursor_index = 0

    def move_cursor(self, direction: int) -> None:
        if not self._items:
            return
        self._cursor_index = (self._cursor_index + direction) % len(self._items)

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        """No cached geometry; exists for consistency with UIController."""
        return

    def confirm_purchase(self) -> None:
        if not (self.visible and self.vendor and self._items):
            return
        item = self._items[self._cursor_index]
        if self._mode == "sell":
            handler = getattr(self.vendor, "handle_sell_request", None)
        else:
            handler = getattr(self.vendor, "handle_buy_request", None)
        if callable(handler):
            result = handler(item)
            message = None
            if isinstance(result, dict):
                message = result.get("message")
            elif hasattr(result, "message"):
                message = getattr(result, "message", None)
            if message:
                hud = getattr(self.window, "player_hud", None)
                enqueue = getattr(hud, "enqueue_toast", None)
                if callable(enqueue):
                    enqueue(str(message))
        if self._mode == "sell":
            self._refresh_items()

    def on_key_press(self, key: int, modifiers: int) -> bool:
        if not self.visible:
            return False
        if key == optional_arcade.arcade.key.UP:
            self.move_cursor(-1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.move_cursor(1)
            return True
        if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.TAB):
            self.toggle_mode()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            self.confirm_purchase()
            return True
        if key == optional_arcade.arcade.key.ESCAPE:
            self.close()
            return True
        return False

    def _currency_amount(self) -> int:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return 0
        try:
            return int(gs.get_counter("gold", 0))
        except Exception as exc:
            if "ui_currency_amount" not in _LOG_ONCE:
                logger.error("Error reading currency counter: %s", exc, exc_info=True)
                _LOG_ONCE.add("ui_currency_amount")
            return 0

    def draw(self) -> None:
        if not self.visible:
            return
        width = min(480.0, self.window.width * 0.7)
        height = min(360.0, self.window.height * 0.8)
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(10, 10, 10, 230),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.GOLD, 2)

        currency = self._currency_amount()
        draw_text_cached(f"Shop [{self._mode.upper()}]", left + 16, top - 24, color=optional_arcade.arcade.color.WHITE, font_size=18, anchor_y="top", cache=self._text_cache)
        draw_text_cached(f"Gold: {currency}", right - 16, top - 24, color=optional_arcade.arcade.color.GOLD, font_size=14, anchor_y="top", anchor_x="right", cache=self._text_cache)

        y = top - 56
        line_height = 22
        if not self._items:
            draw_text_cached("No items for sale.", left + 16, y, color=optional_arcade.arcade.color.LIGHT_GRAY, font_size=14, anchor_y="top", cache=self._text_cache)
            return
        for idx, entry in enumerate(self._items):
            if y < bottom + 32:
                break
            name = entry.get("name") or entry.get("item_id") or "<item>"
            price = entry.get("price", 0)
            if self._mode == "buy" and self.vendor is not None and hasattr(self.vendor, "get_buy_price"):
                try:
                    price = self.vendor.get_buy_price(entry)
                except Exception as exc:
                    if "ui_vendor_price" not in _LOG_ONCE:
                        logger.warning("Vendor get_buy_price failed: %s", exc, exc_info=True)
                        _LOG_ONCE.add("ui_vendor_price")
                    price = entry.get("price", 0)
            qty = entry.get("quantity", -1)
            qty_label = "∞" if qty is None or int(qty) < 0 else str(int(qty))
            color = optional_arcade.arcade.color.WHITE if idx != self._cursor_index else optional_arcade.arcade.color.YELLOW
            draw_text_cached(
                f"{'> ' if idx==self._cursor_index else '  '}{name}  ({qty_label})",
                left + 16,
                y,
                color=color,
                font_size=14,
                anchor_y="top",
                cache=self._text_cache,
            )
            draw_text_cached(
                f"{price}g",
                right - 24,
                y,
                color=optional_arcade.arcade.color.GOLD,
                font_size=14,
                anchor_y="top",
                anchor_x="right",
                cache=self._text_cache,
            )
            y -= line_height


class CharacterPanel(UIElement):
    """Overlay showing player level, XP, and derived stats."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._text_cache = TextCache()
        self._title = optional_arcade.arcade.Text(
            text="Character",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_y="top",
        )
        self._hint = optional_arcade.arcade.Text(
            text="Press ESC or C to close",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=11,
            anchor_y="top",
        )

    def toggle(self) -> bool:
        self.visible = not self.visible
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    def close(self) -> None:
        self.visible = False

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        return

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.C):
            self.set_visible(False)
            if hasattr(self.window, "audio"):
                self.window.audio.play_sound("assets/sounds/ui_close.wav")
            return True
        return True

    def _collect_stats(self) -> dict[str, Any]:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return {}
        stats = dict(gs.get_player_stats())
        xp = float(stats.get("xp", 0) or 0)
        xp_to_next = float(stats.get("xp_to_next", 0) or 0)
        xp_needed = max(1.0, xp + max(0.0, xp_to_next))
        stats["xp_needed"] = xp_needed
        try:
            stats["gold"] = getattr(self.window, "get_counter", lambda *a, **k: 0)("gold", 0)
        except Exception as exc:
            if "ui_stats_gold" not in _LOG_ONCE:
                logger.warning("Failed to get gold counter: %s", exc, exc_info=True)
                _LOG_ONCE.add("ui_stats_gold")
            stats["gold"] = 0
        equipment = stats.get("equipment", {}) or {}
        stats["equipment_labels"] = self._resolve_equipment_labels(equipment)
        return stats

    def _resolve_equipment_labels(self, equipment: dict[str, Any]) -> dict[str, str]:
        labels: dict[str, str] = {}
        try:
            from ..inventory import load_item_database

            db = load_item_database()
        except Exception as exc:
            if "ui_inventory_db" not in _LOG_ONCE:
                logger.warning("Failed to load item database: %s", exc, exc_info=True)
                _LOG_ONCE.add("ui_inventory_db")
            db = None
        for slot in ("weapon", "armor", "accessory"):
            item_id = equipment.get(slot) if isinstance(equipment, dict) else None
            if not item_id:
                labels[slot] = "<empty>"
                continue
            if db is not None:
                item_def = db.get(item_id)
                labels[slot] = item_def.name if item_def else str(item_id)
            else:
                labels[slot] = str(item_id)
        return labels

    def draw(self) -> None:
        if not self.visible:
            return

        stats = self._collect_stats()
        if not stats:
            return

        width = min(420.0, max(280.0, self.window.width * 0.35))
        height = 240.0
        left = self.window.width - width - 24.0
        right = left + width
        bottom = 72.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(8, 12, 22, 220),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        padding = 20.0
        self._title.x = left + padding
        self._title.y = top - 16.0
        self._title.draw()
        self._hint.x = left + padding
        self._hint.y = bottom + 14.0
        self._hint.draw()

        content_y = top - 50.0
        line_height = 20.0
        xp = stats.get("xp", 0)
        xp_needed = stats.get("xp_needed", 1)
        draw_text_cached(
            f"Level: {int(stats.get('level', 1))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"XP: {int(xp)} / {int(xp_needed)}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"HP: {int(stats.get('max_hp', 0))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Attack: {int(stats.get('attack', 0))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Defense: {int(stats.get('defense', 0))}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Speed: {stats.get('speed', 0):.2f}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        draw_text_cached(
            f"Gold: {int(stats.get('gold', 0) or 0)}",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.GOLD,
            font_size=13,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height * 1.5
        draw_text_cached(
            "Equipment:",
            left + padding,
            content_y,
            color=optional_arcade.arcade.color.SKY_BLUE,
            font_size=14,
            anchor_y="top",
            cache=self._text_cache,
        )
        content_y -= line_height
        labels = stats.get("equipment_labels", {}) or {}
        for slot in ("weapon", "armor", "accessory"):
            label = labels.get(slot, "<empty>")
            draw_text_cached(
                f"{slot.title()}: {label}",
                left + padding + 8.0,
                content_y,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=12,
                anchor_y="top",
                cache=self._text_cache,
            )
            content_y -= line_height


class GameOverScreen(UIElement):
    """Screen displayed when the player dies."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._title = optional_arcade.arcade.Text(
            text="YOU DIED",
            x=window.width / 2,
            y=window.height / 2 + 50,
            color=optional_arcade.arcade.color.RED,
            font_size=40,
            anchor_x="center",
            anchor_y="center",
            bold=True
        )
        self._subtitle = optional_arcade.arcade.Text(
            text="Press SPACE to Retry",
            x=window.width / 2,
            y=window.height / 2 - 20,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_x="center",
            anchor_y="center"
        )

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def draw(self) -> None:
        if not self.visible:
            return

        # Dim background
        _draw_rectangle_filled(
            center_x=self.window.width / 2,
            center_y=self.window.height / 2,
            width=self.window.width,
            height=self.window.height,
            color=(0, 0, 0, 200)
        )

        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 50
        self._title.draw()

        self._subtitle.x = self.window.width / 2
        self._subtitle.y = self.window.height / 2 - 20
        self._subtitle.draw()


class PauseMenu(UIElement):
    """Menu displayed when the game is paused."""

    _SETTINGS_ROWS: tuple[tuple[str, str, str], ...] = (
        ("music_volume", "Music Volume", "slider"),
        ("sfx_volume", "SFX Volume", "slider"),
        ("fog_enabled", "Fog", "toggle"),
        ("soft_shadows_enabled", "Soft Shadows", "toggle"),
        ("back", "Back", "action"),
    )

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self.options = ["Resume", "Settings", "Save Game", "Load Game", "Quit"]
        self.selected_index = 0
        self.state = "main"  # main, save, load, settings
        self.save_slots: list[str] = []
        self.selected_save_index = 0
        self._settings_index = 0
        self._text_cache = TextCache()

        self._title = optional_arcade.arcade.Text(
            text="PAUSED",
            x=window.width / 2,
            y=window.height / 2 + 80,
            color=optional_arcade.arcade.color.WHITE,
            font_size=30,
            anchor_x="center",
            anchor_y="center",
            bold=True
        )

    def toggle(self) -> bool:
        self.visible = not self.visible
        if self.visible:
            self.selected_index = 0
            self.state = "main"
            self._settings_index = 0
        return self.visible

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def _play_ui_sound(self, path: str) -> None:
        if hasattr(self.window, "audio"):
            self.window.audio.play_sound(path)

    def _runtime_settings(self):
        from ..runtime_settings import ensure_runtime_settings  # noqa: PLC0415

        return ensure_runtime_settings(self.window)

    def _apply_runtime_settings(self) -> None:
        settings = self._runtime_settings()
        settings.apply(self.window)
        saver = getattr(self, "_save_runtime_settings", None)
        if callable(saver):
            saver()

    def _save_runtime_settings(self) -> None:
        from ..runtime_settings_storage import save_runtime_settings  # noqa: PLC0415
        from ..i18n import tr  # noqa: PLC0415

        path = getattr(self.window, "runtime_settings_path", None)
        settings = self._runtime_settings()
        save_runtime_settings(path, settings)
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue):
            enqueue(tr("UI_SETTINGS_SAVED"), seconds=2.0)

    def update(self, dt: float) -> None:  # noqa: ARG002
        if not self.visible:
            return
        manager = getattr(self.window, "input", None)
        if manager is None:
            return
        if getattr(manager, "input_source", "keyboard_mouse") != "gamepad":
            return
        if manager.was_action_pressed("move_up"):
            self._handle_action("up")
        if manager.was_action_pressed("move_down"):
            self._handle_action("down")
        if manager.was_action_pressed("move_left"):
            self._handle_action("left")
        if manager.was_action_pressed("move_right"):
            self._handle_action("right")
        if manager.was_action_pressed("interact"):
            self._handle_action("confirm")
        if manager.was_action_pressed("toggle_help"):
            self._handle_action("back")

    def draw(self) -> None:
        if not self.visible:
            return

        # Dim background
        _draw_rectangle_filled(
            center_x=self.window.width / 2,
            center_y=self.window.height / 2,
            width=self.window.width,
            height=self.window.height,
            color=(0, 0, 0, 150)
        )

        if self.state == "main":
            self._draw_main_menu()
        elif self.state == "save":
            self._draw_save_menu()
        elif self.state == "load":
            self._draw_load_menu()
        elif self.state == "settings":
            self._draw_settings_menu()

    def _draw_main_menu(self) -> None:
        self._title.text = "PAUSED"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 100
        self._title.draw()

        start_y = self.window.height / 2 + 20
        for i, option in enumerate(self.options):
            color = optional_arcade.arcade.color.YELLOW if i == self.selected_index else optional_arcade.arcade.color.GRAY
            draw_text_cached(
                option,
                self.window.width / 2,
                start_y - i * 40,
                color=color,
                font_size=20,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

    def _draw_save_menu(self) -> None:
        self._title.text = "SAVE GAME"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 100
        self._title.draw()

        start_y = self.window.height / 2 + 20

        # Show slots (e.g. Slot 1, Slot 2, Slot 3)
        # For simplicity, let's just show 3 fixed slots + "New Save" if we supported dynamic naming
        # But SaveManager uses filenames. Let's list existing saves + "New Save"

        slots_to_show = self.save_slots + ["<New Save>"]

        for i, slot in enumerate(slots_to_show):
            color = optional_arcade.arcade.color.YELLOW if i == self.selected_save_index else optional_arcade.arcade.color.GRAY
            draw_text_cached(
                slot,
                self.window.width / 2,
                start_y - i * 40,
                color=color,
                font_size=20,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

        draw_text_cached("Press ESC to return", self.window.width / 2, 50, color=optional_arcade.arcade.color.GRAY, font_size=14, anchor_x="center", cache=self._text_cache)

    def _draw_load_menu(self) -> None:
        self._title.text = "LOAD GAME"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 100
        self._title.draw()

        if not self.save_slots:
            draw_text_cached("No saves found", self.window.width / 2, self.window.height / 2, color=optional_arcade.arcade.color.GRAY, font_size=20, anchor_x="center", cache=self._text_cache)
            draw_text_cached("Press ESC to return", self.window.width / 2, 50, color=optional_arcade.arcade.color.GRAY, font_size=14, anchor_x="center", cache=self._text_cache)
            return

        start_y = self.window.height / 2 + 20
        for i, slot in enumerate(self.save_slots):
            color = optional_arcade.arcade.color.YELLOW if i == self.selected_save_index else optional_arcade.arcade.color.GRAY
            draw_text_cached(
                slot,
                self.window.width / 2,
                start_y - i * 40,
                color=color,
                font_size=20,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

        draw_text_cached("Press ESC to return", self.window.width / 2, 50, color=optional_arcade.arcade.color.GRAY, font_size=14, anchor_x="center", cache=self._text_cache)

    def _draw_settings_menu(self) -> None:
        self._title.text = "SETTINGS"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 120
        self._title.draw()

        settings = self._runtime_settings()
        start_y = self.window.height / 2 + 40
        for i, (key, label, kind) in enumerate(self._SETTINGS_ROWS):
            color = optional_arcade.arcade.color.YELLOW if i == self._settings_index else optional_arcade.arcade.color.GRAY
            value = ""
            if kind == "slider":
                if key == "music_volume":
                    value = f"{int(round(settings.music_volume * 100.0))}%"
                elif key == "sfx_volume":
                    value = f"{int(round(settings.sfx_volume * 100.0))}%"
            elif kind == "toggle":
                enabled = bool(getattr(settings, key, False))
                value = "ON" if enabled else "OFF"
            text = f"{label}: {value}" if value else label
            draw_text_cached(
                text,
                self.window.width / 2,
                start_y - i * 36,
                color=color,
                font_size=18,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

        draw_text_cached(
            "Enter/A: Toggle   Left/Right: Adjust   Esc/B: Back",
            self.window.width / 2,
            50,
            color=optional_arcade.arcade.color.GRAY,
            font_size=14,
            anchor_x="center",
            cache=self._text_cache,
        )

    def _handle_action(self, action: str, *, large_step: bool = False) -> bool:
        action = str(action)
        if self.state == "main":
            if action == "up":
                self.selected_index = (self.selected_index - 1) % len(self.options)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self.selected_index = (self.selected_index + 1) % len(self.options)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "confirm":
                return self._confirm_main()
            if action == "back":
                self._play_ui_sound("assets/sounds/ui_close.wav")
                self.window.paused = False
                self.visible = False
                return True
            return False

        if self.state == "save":
            slots_to_show = self.save_slots + ["<New Save>"]
            if action == "up":
                self.selected_save_index = (self.selected_save_index - 1) % len(slots_to_show)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self.selected_save_index = (self.selected_save_index + 1) % len(slots_to_show)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "confirm":
                self._play_ui_sound("assets/sounds/ui_click.wav")
                return self._confirm_save(slots_to_show)
            if action == "back":
                self.state = "main"
                return True
            return False

        if self.state == "load":
            if not self.save_slots:
                if action in ("back", "confirm"):
                    self.state = "main"
                return True
            if action == "up":
                self.selected_save_index = (self.selected_save_index - 1) % len(self.save_slots)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self.selected_save_index = (self.selected_save_index + 1) % len(self.save_slots)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "confirm":
                self._play_ui_sound("assets/sounds/ui_click.wav")
                slot_name = self.save_slots[self.selected_save_index]
                if self._confirm_unsaved_action("Load Game", lambda: self.window.save_manager.load_game(slot_name)):
                    return True
                self.window.save_manager.load_game(slot_name)
                self.window.paused = False
                self.visible = False
                return True
            if action == "back":
                self.state = "main"
                return True
            return False

        if self.state == "settings":
            if action == "up":
                self._settings_index = (self._settings_index - 1) % len(self._SETTINGS_ROWS)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self._settings_index = (self._settings_index + 1) % len(self._SETTINGS_ROWS)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action in ("left", "right"):
                delta = 0.1 if large_step else 0.05
                if action == "left":
                    delta = -delta
                return self._adjust_setting(delta)
            if action == "confirm":
                return self._confirm_setting()
            if action == "back":
                self.state = "main"
                return True
            return False

        return False

    def _confirm_unsaved_action(self, reason: str, action) -> bool:
        editor = getattr(self.window, "editor_controller", None)
        if editor is None or not getattr(editor, "active", False):
            return False
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker(reason, action)
            return isinstance(blocked, bool) and blocked
        return False

    def _confirm_main(self) -> bool:
        self._play_ui_sound("assets/sounds/ui_click.wav")
        option = self.options[self.selected_index]
        if option == "Resume":
            self.window.paused = False
            self.visible = False
            return True
        if option == "Settings":
            self.state = "settings"
            self._settings_index = 0
            return True
        if option == "Save Game":
            self.state = "save"
            self.save_slots = self.window.save_manager.list_saves()
            self.selected_save_index = 0
            return True
        if option == "Load Game":
            self.state = "load"
            self.save_slots = self.window.save_manager.list_saves()
            self.selected_save_index = 0
            return True
        if option == "Quit":
            optional_arcade.arcade.close_window()
            return True
        return True

    def _confirm_save(self, slots_to_show: list[str]) -> bool:
        slot_name = slots_to_show[self.selected_save_index]
        if slot_name == "<New Save>":
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            slot_name = f"save_{timestamp}"

        self.window.save_manager.save_game(slot_name)
        print(f"[Mesh][PauseMenu] Saved game to '{slot_name}'")
        self.state = "main"
        return True

    def _adjust_setting(self, delta: float) -> bool:
        key, _label, kind = self._SETTINGS_ROWS[self._settings_index]
        settings = self._runtime_settings()
        if kind != "slider":
            return False
        if key == "music_volume":
            settings.music_volume = max(0.0, min(1.0, float(settings.music_volume) + delta))
        elif key == "sfx_volume":
            settings.sfx_volume = max(0.0, min(1.0, float(settings.sfx_volume) + delta))
        else:
            return False
        self._apply_runtime_settings()
        return True

    def _confirm_setting(self) -> bool:
        key, _label, kind = self._SETTINGS_ROWS[self._settings_index]
        settings = self._runtime_settings()
        if kind == "toggle":
            current = bool(getattr(settings, key, False))
            setattr(settings, key, not current)
            self._apply_runtime_settings()
            return True
        if kind == "action" and key == "back":
            self.state = "main"
            return True
        return False

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:
        if not self.visible:
            return False

        if self.state == "main":
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        elif self.state == "save":
            slots_to_show = self.save_slots + ["<New Save>"]
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        elif self.state == "load":
            if not self.save_slots:
                if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.ENTER):
                    self.state = "main"
                return True

            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        elif self.state == "settings":
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.MINUS):
                return self._handle_action("left", large_step=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT))
            if key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.EQUAL):
                return self._handle_action("right", large_step=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT))
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        return True # Block other input while paused
