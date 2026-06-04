"""Main-menu / title-screen overlay and project browser."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.logging_tools import get_logger
from engine.swallowed_exceptions import _log_swallow

from .common import (
    UIElement,
    _draw_tb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..input_hints import get_action_hint, set_keyboard_hints
from ._settings_data import SETTINGS_ROWS

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProjectBrowserRect:
    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.bottom + self.top) / 2.0


@dataclass(frozen=True)
class ProjectBrowserLayout:
    panel: ProjectBrowserRect
    title_x: float
    title_y: float
    subtitle_x: float
    subtitle_y: float
    cards: list[ProjectBrowserRect]
    selected_card: ProjectBrowserRect | None
    footer_x: float
    footer_y: float


def compute_menu_panel_layout(
    width: float,
    height: float,
    item_count: int,
    selected_index: int,
) -> ProjectBrowserLayout:
    panel_width = min(720.0, max(420.0, float(width) - 96.0))
    panel_height = min(520.0, max(360.0, float(height) - 112.0))
    left = (float(width) - panel_width) / 2.0
    bottom = (float(height) - panel_height) / 2.0
    panel = ProjectBrowserRect(left=left, right=left + panel_width, bottom=bottom, top=bottom + panel_height)

    card_left = panel.left + 34.0
    card_width = panel.width - 68.0
    row_height = 52.0
    gap = 10.0
    cards: list[ProjectBrowserRect] = []
    for index in range(max(0, int(item_count))):
        row_top = panel.top - 120.0 - index * (row_height + gap)
        cards.append(
            ProjectBrowserRect(
                left=card_left,
                right=card_left + card_width,
                bottom=row_top - row_height,
                top=row_top,
            )
        )

    selected_card = cards[selected_index] if 0 <= selected_index < len(cards) else None
    return ProjectBrowserLayout(
        panel=panel,
        title_x=panel.center_x,
        title_y=panel.top - 34.0,
        subtitle_x=panel.center_x,
        subtitle_y=panel.top - 76.0,
        cards=cards,
        selected_card=selected_card,
        footer_x=panel.center_x,
        footer_y=panel.bottom + 28.0,
    )


def compute_project_browser_menu_layout(
    width: float,
    height: float,
    item_count: int,
    selected_index: int,
) -> ProjectBrowserLayout:
    return compute_menu_panel_layout(width, height, item_count, selected_index)


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def get_menu_legend(input_source: str) -> str:
    source = str(input_source or "").strip().lower()
    if source == "gamepad":
        return "A Select  B Back  D-pad Navigate"
    return "Enter Select  Esc Back  Up/Down Navigate"


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
        from ..repo_root import get_repo_root  # noqa: PLC0415

        items: list[dict[str, str]] = []
        editor = getattr(self.window, "editor", None)
        if editor is not None and hasattr(editor, "workspace"):
            roots = editor.workspace.get_recent_projects()
        else:
            from ..projects import get_recent_projects  # noqa: PLC0415

            roots = get_recent_projects()
        for root in roots:
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

        root_text = str(root or "").strip()
        if not root_text:
            return
        editor = getattr(self.window, "editor_controller", None)
        flusher = getattr(editor, "_flush_workspace_autosave", None) if editor is not None else None
        if callable(flusher):
            flusher()
        os.environ["MESH_REPO_ROOT"] = root_text
        reset_path_caches()
        workspace_owner = getattr(self.window, "editor", None)
        if workspace_owner is not None and hasattr(workspace_owner, "workspace"):
            workspace_owner.workspace.record_project_open(root_text)
        else:
            from ..projects import add_recent_project, set_last_project  # noqa: PLC0415

            add_recent_project(root_text)
            set_last_project(root_text)

        # Reload config and world from the new project root
        self._reload_project_config()

        # Reload workspace settings if editor is present
        if hasattr(self.window, "editor") and callable(getattr(self.window.editor, "load_workspace", None)):
            self.window.editor.load_workspace()

    def _reload_project_config(self) -> None:
        """Reload the engine config and world controller from the current project root."""
        import json
        from ..config import load_config  # noqa: PLC0415
        from ..paths import resolve_path  # noqa: PLC0415
        from ..migrations import migrate_payload  # noqa: PLC0415
        from ..world_controller import WorldController  # noqa: PLC0415

        new_config = load_config()
        self.window.engine_config = new_config

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
            filtered = "".join(ch for ch in text if ch.isprintable() and ch not in "\\/:*?\"<>|")
            self._create_name += filtered
            self._cache_valid = False
            return

        if self.state == "create_project_path":
            filtered = "".join(ch for ch in text if ch.isprintable())
            self._create_path += filtered
            self._cache_valid = False
            return

        if self.state == "open_project_path":
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
        from ..projects import remove_recent_project, get_repo_root  # noqa: PLC0415

        items = self._project_items()
        if not items:
            return

        self._project_index = max(0, min(self._project_index, len(items) - 1))
        selected = items[self._project_index]

        if selected.get("kind") == "recent":
            remove_recent_project(selected["root"])
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
                _log_swallow("MAIN-001", "engine/ui_overlays/main_menu_overlay.py pass-only blanket swallow")
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
                    _log_swallow("MAIN-002", "engine/ui_overlays/main_menu_overlay.py pass-only blanket swallow")
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

    def _draw_menu_text(
        self,
        text: str,
        x: float,
        y: float,
        *,
        color: tuple[int, int, int, int],
        font_size: float,
        anchor_x: str = "left",
        anchor_y: str = "top",
        bold: bool = False,
    ) -> None:
        optional_arcade.arcade.Text(
            text=text,
            x=x,
            y=y,
            color=color,
            font_size=font_size,
            font_name=("Calibri", "Arial"),
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            bold=bold,
        ).draw()

    def _draw_menu_panel(self, layout: ProjectBrowserLayout) -> None:
        panel = layout.panel

        gradient_colors = [
            (22, 28, 36, 245),
            (20, 25, 33, 245),
            (18, 22, 29, 245),
            (15, 19, 25, 245),
            (12, 16, 22, 245),
        ]
        band_height = panel.height / len(gradient_colors)
        for index, color in enumerate(gradient_colors):
            top = panel.top - index * band_height
            bottom = panel.top - (index + 1) * band_height
            _draw_rectangle_filled(
                center_x=panel.center_x,
                center_y=(top + bottom) / 2.0,
                width=panel.width,
                height=band_height + 1.0,
                color=color,
            )
        _draw_tb_rectangle_outline(panel.left, panel.right, panel.top, panel.bottom, (72, 180, 205, 220), 2)
        _draw_tb_rectangle_outline(
            panel.left + 6.0,
            panel.right - 6.0,
            panel.top - 6.0,
            panel.bottom + 6.0,
            (120, 220, 210, 90),
            1,
        )

    def _draw_menu_title(self, layout: ProjectBrowserLayout, subtitle: str) -> None:
        self._draw_menu_text(
            "MESH",
            layout.title_x,
            layout.title_y,
            color=(232, 248, 246, 255),
            font_size=34,
            anchor_x="center",
            bold=True,
        )
        self._draw_menu_text(
            subtitle,
            layout.subtitle_x,
            layout.subtitle_y,
            color=(142, 178, 190, 255),
            font_size=15,
            anchor_x="center",
        )

    def _draw_menu_cards(
        self,
        layout: ProjectBrowserLayout,
        rows: list[tuple[str, str]],
        selected_index: int,
    ) -> None:
        selected_index = selected_index if 0 <= selected_index < len(rows) else -1
        for index, ((label, subtitle), card) in enumerate(zip(rows, layout.cards)):
            selected = index == selected_index
            bg = (35, 58, 70, 245) if selected else (24, 32, 42, 230)
            border = (108, 224, 210, 255) if selected else (80, 110, 125, 150)
            _draw_rectangle_filled(
                center_x=card.center_x,
                center_y=card.center_y,
                width=card.width,
                height=card.height,
                color=bg,
            )
            if selected:
                _draw_rectangle_filled(
                    center_x=card.left + 2.5,
                    center_y=card.center_y,
                    width=5.0,
                    height=card.height,
                    color=(116, 241, 218, 255),
                )
            _draw_tb_rectangle_outline(card.left, card.right, card.top, card.bottom, border, 2 if selected else 1)

            text_left = card.left + 18.0
            self._draw_menu_text(
                str(label),
                text_left,
                card.top - 12.0,
                color=(232, 242, 244, 255),
                font_size=16,
                bold=selected,
            )
            if subtitle:
                self._draw_menu_text(
                    str(subtitle),
                    text_left,
                    card.top - 32.0,
                    color=(150, 164, 174, 230),
                    font_size=11,
                )

    def _draw_menu_footer(self, layout: ProjectBrowserLayout, text: str) -> None:
        panel = layout.panel
        _draw_rectangle_filled(
            center_x=panel.center_x,
            center_y=layout.footer_y,
            width=panel.width - 68.0,
            height=24.0,
            color=(255, 255, 255, 18),
        )
        self._draw_menu_text(
            text,
            layout.footer_x,
            layout.footer_y + 7.0,
            color=(166, 187, 196, 230),
            font_size=12,
            anchor_x="center",
        )

    def _input_legend(self) -> str:
        input_source = "keyboard_mouse"
        manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
        if manager is not None:
            input_source = str(getattr(manager, "input_source", input_source))
        return get_menu_legend(input_source)

    def _draw_card_menu(
        self,
        *,
        rows: list[tuple[str, str]],
        selected_index: int,
        subtitle: str,
        footer: str,
    ) -> None:
        layout = compute_menu_panel_layout(self.window.width, self.window.height, len(rows), selected_index)
        self._draw_menu_panel(layout)
        self._draw_menu_title(layout, subtitle)
        self._draw_menu_cards(layout, rows, selected_index)
        self._draw_menu_footer(layout, footer)

    def _draw_project_browser(self) -> None:
        rows = [(str(item.get("label", "")), str(item.get("root", "") or "")) for item in self._project_items()]
        self._draw_card_menu(
            rows=rows,
            selected_index=self._project_index,
            subtitle="Project Browser",
            footer=self._input_legend(),
        )

    def _draw_title_screen(self) -> None:
        self._draw_card_menu(
            rows=[(label, "") for label, _action in self._items()],
            selected_index=self._selection_index,
            subtitle="Title Screen",
            footer=self._input_legend(),
        )

    def _draw_template_menu(self) -> None:
        from ..project_templates import list_templates  # noqa: PLC0415

        templates = list_templates()
        self._draw_card_menu(
            rows=[(str(template.title), str(template.description)) for template in templates],
            selected_index=self._template_index,
            subtitle="New Project",
            footer="[Enter] Next  [Esc] Cancel",
        )

    def _settings_value_text(self, key: str, kind: str) -> str:
        settings = self._runtime_settings()
        if kind == "slider":
            if key == "music_volume":
                return f"{int(round(settings.music_volume * 100.0))}%"
            if key == "sfx_volume":
                return f"{int(round(settings.sfx_volume * 100.0))}%"
        if kind == "toggle":
            return "ON" if bool(getattr(settings, key, False)) else "OFF"
        return ""

    def _draw_settings_cards(self) -> None:
        self._draw_card_menu(
            rows=[(label, self._settings_value_text(key, kind)) for key, label, kind in SETTINGS_ROWS],
            selected_index=self._settings_index,
            subtitle="Settings",
            footer="Enter/A: Toggle   Left/Right: Adjust   Esc/B: Back",
        )

    def _draw_input_menu(self, *, subtitle: str, value: str, error: str, footer: str) -> None:
        layout = compute_menu_panel_layout(self.window.width, self.window.height, 1, -1)
        self._draw_menu_panel(layout)
        self._draw_menu_title(layout, subtitle)

        field = layout.cards[0]
        _draw_rectangle_filled(
            center_x=field.center_x,
            center_y=field.center_y,
            width=field.width,
            height=field.height,
            color=(24, 32, 42, 230),
        )
        _draw_tb_rectangle_outline(field.left, field.right, field.top, field.bottom, (80, 110, 125, 150), 1)
        self._draw_menu_text(
            f"{value}_",
            field.left + 18.0,
            field.center_y + 8.0,
            color=(232, 242, 244, 255),
            font_size=16,
            anchor_y="center",
        )
        if error:
            self._draw_menu_text(
                str(error),
                field.left + 18.0,
                field.bottom - 18.0,
                color=(255, 220, 120, 255),
                font_size=12,
            )
        self._draw_menu_footer(layout, footer)

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
            center_x=self.window.width / 2,
            center_y=self.window.height / 2,
            width=self.window.width,
            height=self.window.height,
            color=(8, 10, 14, 255),
        )
        if self.state == "project_browser":
            self._draw_project_browser()
            return
        if self.state == "main":
            self._draw_title_screen()
            return
        if self.state == "create_project_template":
            self._draw_template_menu()
            return
        if self.state == "settings":
            self._draw_settings_cards()
            return
        if self.state == "create_project_name":
            self._draw_input_menu(
                subtitle="Project Name",
                value=self._create_name,
                error="",
                footer="[Enter] Next  [Esc] Cancel",
            )
            return
        if self.state == "create_project_path":
            self._draw_input_menu(
                subtitle="Project Location",
                value=self._create_path,
                error=self._create_error,
                footer="[Enter] Create  [Esc] Cancel",
            )
            return
        if self.state == "open_project_path":
            self._draw_input_menu(
                subtitle="Open Project",
                value=self._open_path,
                error=self._open_error,
                footer="[Enter] Open  [Esc] Cancel",
            )
            return

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 220),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

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
                _log_swallow("MAIN-003", "engine/ui_overlays/main_menu_overlay.py pass-only blanket swallow")
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
        from ..i18n import tr  # noqa: PLC0415

        editor = getattr(self.window, "editor", None)
        if editor is not None and hasattr(editor, "workspace"):
            editor.workspace.save_user_settings()
        else:
            from ..runtime_settings_storage import save_runtime_settings  # noqa: PLC0415

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
            self._settings_index = (self._settings_index - 1) % len(SETTINGS_ROWS)
            return True
        if action == "down":
            self._settings_index = (self._settings_index + 1) % len(SETTINGS_ROWS)
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
        key, _label, kind = SETTINGS_ROWS[self._settings_index]
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
        key, _label, kind = SETTINGS_ROWS[self._settings_index]
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

