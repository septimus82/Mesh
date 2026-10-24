"""The Mesh Studio launcher: the first window you see when you open Mesh.

Create a game from a template, open one from disk or from the recent list, and it
opens in Mesh Studio. The launcher is a thin front on what already exists: projects
are made by ``engine.project_scaffold`` from ``engine.project_templates``, the recent
list is ``engine.projects``, and Mesh Studio runs in its own process (``mesh_cli edit``),
so a game never shares a process with the launcher.

Run it by double-clicking "Mesh Engine.bat" in the engine folder, or ``python -m engine.launcher``.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import textwrap
import time
from functools import partial
from pathlib import Path
from typing import Any, Callable

import engine.optional_arcade as optional_arcade
from engine import projects
from engine.project_templates import Template, list_templates
from engine.studio_ui import (
    C_ACCENT,
    C_BG,
    C_DANGER_TEXT,
    C_ERROR,
    C_FIELD,
    C_FIELD_EDGE,
    C_LINE,
    C_MUTED,
    C_OK,
    C_PANEL,
    C_TEXT,
    FONT,
    S_ACTIVE,
    S_BUTTON,
    S_CARD,
    S_CARD_MISSING,
    S_PLAY,
    CardButton,
    FirstClicks,
    TextField,
    TintedImage,
    ask_path,
    brand_texture,
    field_clipboard,
    gui,
    icon_texture,
    make_button,
    set_app_icon,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 960, 640
RECENT_X = 430  # where the recent list's surface starts
CARD_W, CARD_H = 288, 192
_BAD_CHARS = set('<>:"/\\|?*')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


# ==================================================================== checks (no disk changes)
def _inside(path: Path, folder: Path) -> bool:
    path, folder = path.resolve(), folder.resolve()
    return path == folder or folder in path.parents


def check_new_project(name: str, location: str) -> tuple[Path | None, str]:
    """Where a new game would be created, or why it can't be: ``(folder, "")`` or ``(None, reason)``."""
    name, location = name.strip(), location.strip().strip('"')
    if not name:
        return None, "Give your game a name."
    if any(ch in _BAD_CHARS or ord(ch) < 32 for ch in name):
        return None, 'A name can\'t contain any of these: < > : " / \\ | ? *'
    if name.rstrip(" .") != name or name.split(".")[0].upper() in _RESERVED:
        return None, "Windows doesn't allow that as a folder name. Try another name."
    if not location:
        return None, "Choose where to save your game."
    parent = Path(location).expanduser()
    if not parent.is_absolute():
        return None, "Choose a full folder path, for example C:\\Users\\you\\Documents\\Mesh Projects."
    if parent.exists() and not parent.is_dir():
        return None, f"{parent} is a file, not a folder."
    target = parent / name
    try:
        inside_engine = _inside(target, ENGINE_ROOT)
    except OSError as exc:
        return None, f"That location can't be used ({exc})."
    if inside_engine:
        return None, f"Choose a folder outside the Mesh engine folder ({ENGINE_ROOT}): your game and the engine stay separate."
    if target.exists():
        if (target / "config.json").is_file():
            return None, f"There is already a Mesh project at {target}. Use Open Project to open it, or pick another name."
        if not target.is_dir() or any(target.iterdir()):
            return None, f'There is already a folder called "{name}" in {parent}. Pick another name or location; nothing was changed.'
    return target, ""


def check_existing_project(folder: str) -> tuple[Path | None, str]:
    """A folder that can be opened as a Mesh project, or why it can't: ``(folder, "")`` or ``(None, reason)``."""
    text = str(folder).strip().strip('"')
    if not text:
        return None, "Choose a project folder."
    path = Path(text).expanduser()
    if not path.exists():
        return None, f"{path} isn't there any more. It may have been moved, renamed or deleted."
    if not path.is_dir():
        return None, f"{path} is a file. Choose the folder that contains config.json."
    config = path / "config.json"
    if not config.is_file():
        return None, f"There's no Mesh project in {path}: it has no config.json. Choose the folder that contains config.json."
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{config} can't be read ({exc})."
    if not isinstance(data, dict):
        return None, f"{config} isn't a Mesh project configuration."
    return path.resolve(), ""


def project_title(root: Path) -> str:
    try:
        title = json.loads((root / "config.json").read_text(encoding="utf-8")).get("title")
    except (OSError, ValueError, AttributeError):
        title = None
    return str(title or root.name)


def studio_command(root: Path) -> tuple[list[str], dict[str, str]]:
    """How to start Mesh Studio on ``root``: in its own process, with the engine importable."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(ENGINE_ROOT), env.get("PYTHONPATH", "")) if p)
    env["PYTHONIOENCODING"] = "utf-8"  # its log is a file; project names may be any language
    env["PYTHONUNBUFFERED"] = "1"
    return [sys.executable, "-m", "mesh_cli", "edit", str(root)], env


def _has_window(pid: int) -> bool:
    """Whether process ``pid`` shows a window yet (Windows; elsewhere assume so after a moment)."""
    if sys.platform != "win32":
        return True
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd: Any, _param: Any) -> bool:
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(1)
        return True

    user32.EnumWindows(visit, 0)
    return bool(found)


# ==================================================================== the window
class Launcher:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.screen = "home"  # home | new | opening
        self.message, self.message_ok = "", True
        self.templates = list_templates(launcher_only=True)
        self.template: Template = next((t for t in self.templates if t.id == "adventure"), self.templates[0])
        self.form = {"name": "My Game", "location": str(projects.default_projects_dir())}
        self.opening: dict[str, Any] | None = None  # {"proc", "name", "log", "started"}
        self._fields: dict[str, Any] = {}
        self._cards: dict[str, Any] = {}
        self._recent_rows: list[dict[str, Any]] = []
        self._previews: dict[str, Any] = {}
        self.ui = gui.UIManager(window)
        window.push_handlers(self)
        self.ui.enable()
        self._first_clicks = FirstClicks("Launcher")  # pyglet keeps only a weak reference to handlers
        window.push_handlers(self._first_clicks)
        self._rebuild()

    # ---------------------------------------------------------------- actions
    def say(self, text: str, ok: bool = True) -> None:
        self.message, self.message_ok = text, ok
        self._rebuild()

    def go(self, screen: str) -> None:
        self._read_fields()
        self.screen, self.message = screen, ""
        self._rebuild()

    def _card_clicked(self, template: Template, _event: Any) -> None:
        self.choose_template(template)

    def choose_template(self, template: Template) -> None:
        self._read_fields()
        self.template = template
        self._rebuild()

    def browse_location(self) -> None:
        self._read_fields()
        chosen = ask_path(folder=True, title="Where should your new game go?", initial=self.form["location"])
        if chosen:
            self.form["location"] = str(Path(chosen))
        self._rebuild()

    def create(self) -> None:
        self._read_fields()
        target, problem = check_new_project(self.form["name"], self.form["location"])
        if target is None:
            self.say(problem, ok=False)
            return
        from engine.project_scaffold import create_project  # noqa: PLC0415  # only needed when creating

        try:
            create_project(target, self.form["name"].strip(), template_id=self.template.id)
        except OSError as exc:
            self.say(f"Couldn't create the project in {target.parent} ({exc}).", ok=False)
            return
        self.open_project(str(target))

    def open_dialog(self) -> None:
        chosen = ask_path(folder=True, title="Open a Mesh project folder", initial=str(projects.default_projects_dir()))
        if chosen:
            self.open_project(chosen)

    def open_project(self, folder: str) -> None:
        root, problem = check_existing_project(folder)
        if root is None:
            self.say(problem, ok=False)
            return
        projects.add_recent_project(str(root))
        command, env = studio_command(root)
        log_path = fresh_log(projects.user_data_dir() / "logs" / "studio.log")
        env["MESH_CRASH_LOG"] = str(log_path)  # the Studio names it if it crashes
        log = open(log_path, "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(command, cwd=str(root), env=env, stdout=log, stderr=subprocess.STDOUT)
        except OSError as exc:
            log.close()
            self.say(f"Mesh Studio couldn't start ({exc}).", ok=False)
            return
        self.opening = {"proc": proc, "name": project_title(root), "log": log, "log_path": log_path, "started": time.time()}
        self.screen, self.message = "opening", ""
        self._rebuild()

    def remove_recent(self, folder: str) -> None:
        projects.remove_recent_project(folder)
        self.say("Removed it from the list. Nothing on disk was changed.")

    def recent_clicked(self, folder: str, missing: bool) -> None:
        if missing:
            self.say(f"{folder} isn't there any more. It may have been moved, renamed or deleted. "
                     "Use Open Project to find it, or Remove to take it off this list.", ok=False)
        else:
            self.open_project(folder)

    # ---------------------------------------------------------------- per frame
    def on_update(self, delta_time: float) -> None:
        if self.opening is None:
            return
        proc = self.opening["proc"]
        if proc.poll() is not None:  # Studio stopped before showing a window
            self.opening["log"].close()
            log_path, self.opening = self.opening["log_path"], None
            self.screen = "home"
            self.say(f"Mesh Studio closed straight away (exit code {proc.returncode}). Details: {log_path}", ok=False)
        elif _has_window(proc.pid) or time.time() - self.opening["started"] > 60:
            self.opening["log"].close()
            self.window.close()  # Studio is up; the launcher's job is done

    def on_draw(self) -> bool:
        a = optional_arcade.arcade
        self.window.clear(color=C_BG)
        if self.screen == "home":  # the recent list on its own surface
            a.draw_lrbt_rectangle_filled(RECENT_X, self.window.width, 0, self.window.height, C_PANEL)
            a.draw_line(RECENT_X, 0, RECENT_X, self.window.height, C_LINE, 1)
        self.ui.draw()
        card = self._cards.get(self.template.id) if self.screen == "new" else None
        if card is not None:
            a.draw_lrbt_rectangle_outline(card.left - 3, card.right + 3, card.bottom - 3, card.top + 3, C_ACCENT, 2)
        self._dump_layout()
        return True

    def on_key_press(self, symbol: int, modifiers: int) -> bool:
        k = optional_arcade.arcade.key
        active = next((f for f in self._fields.values() if f.active), None)
        if active is not None:
            if modifiers & k.MOD_CTRL and symbol in (k.A, k.C, k.X, k.V):
                field_clipboard(self.window, active, symbol)
            elif symbol in (k.ENTER, k.NUM_ENTER, k.TAB):
                active.deactivate()  # confirms the field; only the Create & Open button creates
                self._update_target()
            elif symbol == k.ESCAPE:
                active.deactivate()
            return True
        if symbol == k.ESCAPE and self.screen == "new":
            self.go("home")
        return True

    # ---------------------------------------------------------------- building the screens
    def _read_fields(self) -> None:
        for key, field in self._fields.items():
            self.form[key] = field.text

    def _button(self, text: str, action: Callable[[], None], *, width: int = 200, style: dict[str, Any] = S_BUTTON,
                height: int = 32) -> Any:
        button = make_button(text, width=width, height=height, style=style)
        button.on_click = lambda _e: action()
        return button

    def _label(self, text: str, *, size: int = 11, color: tuple[int, int, int] = C_TEXT, bold: bool = False) -> Any:
        return gui.UILabel(text=text, font_size=size, font_name=FONT, text_color=color, bold=bold)

    def _lines(self, box: Any, text: str, *, chars: int, size: int = 10, color: tuple[int, int, int] = C_MUTED) -> None:
        # One label per line: arcade's multi-line labels can split words.
        for line in textwrap.wrap(text, chars) or [""]:
            box.add(self._label(line, size=size, color=color))

    def _field(self, key: str, width: int) -> Any:
        field = TextField(text=self.form[key], width=width, height=28, font_size=11, font_name=FONT, text_color=C_TEXT,
                          caret_color=C_TEXT, border_color=C_FIELD_EDGE, border_width=1)
        field.with_background(color=C_FIELD)
        self._fields[key] = field
        return field

    def _preview(self, template: Template) -> Any:
        if template.id not in self._previews:
            path = ENGINE_ROOT / template.preview
            arcade = optional_arcade.arcade
            self._previews[template.id] = arcade.load_texture(path) if path.is_file() else arcade.Texture.create_empty(
                f"mesh-template-{template.id}", (CARD_W, CARD_H))
        return self._previews[template.id]

    def _rebuild(self) -> None:
        self.ui.clear()
        self._fields, self._cards, self._recent_rows = {}, {}, []
        root = self.ui.add(gui.UIAnchorLayout())
        {"home": self._home, "new": self._new, "opening": self._opening}[self.screen](root)
        if self.message:
            box = gui.UIBoxLayout(vertical=True, align="left")
            self._lines(box, self.message, chars=120, size=11, color=C_OK if self.message_ok else C_ERROR)
            root.add(box, anchor_x="left", anchor_y="bottom", align_x=40, align_y=18)

    def _home(self, root: Any) -> None:
        left = gui.UIBoxLayout(vertical=True, align="left", space_between=10)
        left.add(self._title())
        self._lines(left, "Make your own 2D games: maps, characters, stories.", chars=60, size=12)
        left.add(gui.UISpace(height=24))
        left.add(self._button("New Project", lambda: self.go("new"), width=300, height=44, style=S_ACTIVE))
        left.add(self._button("Open Project...", self.open_dialog, width=300, height=44))
        left.add(gui.UISpace(height=8))
        self._lines(left, "New games are saved in your Documents, in Mesh Projects, unless you choose "
                          "another folder.", chars=48)
        root.add(left, anchor_x="left", anchor_y="top", align_x=40, align_y=-48)

        right = gui.UIBoxLayout(vertical=True, align="left", space_between=8)
        heading = gui.UIBoxLayout(vertical=False, space_between=8, align="center")
        history = icon_texture("history")
        if history is not None:
            heading.add(TintedImage(texture=history, width=16, height=16, tint=C_MUTED))
        heading.add(self._label("Recent projects", size=13, bold=True))
        right.add(heading)
        recent = projects.get_recent_projects()
        if not recent:
            self._lines(right, "No recent projects yet. Create one, or open a project folder.", chars=50)
        for folder in recent:
            path = Path(folder)
            missing = not (path / "config.json").is_file()
            row = gui.UIBoxLayout(vertical=False, space_between=6)
            name = project_title(path) if not missing else path.name
            # One card per project: its name, and under it where it is (or that it's gone).
            button = CardButton(text=name, detail=folder, detail_prefix="Missing: " if missing else "", icon="folder",
                                detail_color=C_DANGER_TEXT if missing else C_MUTED, width=324 if missing else 420, height=46,
                                style=S_CARD_MISSING if missing else S_CARD)
            button.on_click = lambda _e, f=folder, m=missing: self.recent_clicked(f, m)
            row.add(button)
            if missing:
                row.add(self._button("Remove", partial(self.remove_recent, folder), width=90, height=46))
            right.add(row)
            self._recent_rows.append({"name": name, "path": folder, "missing": missing, "button": button})
        root.add(right, anchor_x="left", anchor_y="top", align_x=RECENT_X + 40, align_y=-56)
        wordmark = brand_texture("meshmind_studios_wordmark.png")
        if wordmark is not None and not self.message:  # the publisher's credit (a message takes its place)
            credit = gui.UIBoxLayout(vertical=False, space_between=8, align="center")
            credit.add(self._label("by", size=10, color=C_MUTED))
            credit.add(gui.UIImage(texture=wordmark, width=136, height=round(136 * wordmark.height / wordmark.width)))
            root.add(credit, anchor_x="left", anchor_y="bottom", align_x=40, align_y=22)

    def _title(self) -> Any:
        """Mesh Studio's mark and name, the launcher's heading."""
        row = gui.UIBoxLayout(vertical=False, space_between=12, align="center")
        mark = brand_texture("mesh_studio_mark_128.png")
        if mark is not None:
            row.add(gui.UIImage(texture=mark, width=56, height=round(56 * mark.height / mark.width)))
        row.add(self._label("Mesh Studio", size=26, bold=True))
        return row

    def _new(self, root: Any) -> None:
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=8)
        box.add(self._label("New Project", size=22, bold=True))
        box.add(self._label("Choose a starting point. You can change everything later.", color=C_MUTED))
        cards = gui.UIBoxLayout(vertical=False, space_between=24, align="top")
        for template in self.templates:
            column = gui.UIBoxLayout(vertical=True, align="left", space_between=4)
            card = gui.UITextureButton(texture=self._preview(template), width=CARD_W, height=CARD_H)
            card.on_click = partial(self._card_clicked, template)
            self._cards[template.id] = card
            column.add(card)
            column.add(self._button(template.title, partial(self.choose_template, template), width=CARD_W,
                                    style=S_ACTIVE if template is self.template else S_BUTTON))
            self._lines(column, template.description, chars=42, size=11)
            cards.add(column)
        box.add(cards)
        box.add(gui.UISpace(height=6))
        row = gui.UIBoxLayout(vertical=False, space_between=10, align="center")
        row.add(self._label("Name", color=C_MUTED))
        row.add(self._field("name", 240))
        row.add(gui.UISpace(width=12))
        row.add(self._label("Save in", color=C_MUTED))
        row.add(self._field("location", 300))
        row.add(self._button("Browse...", self.browse_location, width=96))
        box.add(row)
        self._target_label = self._label("", size=10)
        box.add(self._target_label)
        self._update_target()
        for field in self._fields.values():
            field.on_change = lambda _e: self._update_target()
        row = gui.UIBoxLayout(vertical=False, space_between=10)
        row.add(self._button("Create & Open", self.create, width=200, height=40, style=S_PLAY))
        row.add(self._button("Back", lambda: self.go("home"), width=100, height=40))
        box.add(row)
        root.add(box, anchor_x="left", anchor_y="top", align_x=40, align_y=-28)

    def _update_target(self) -> None:
        """Say where the game will go, or what's wrong, as you type."""
        self._read_fields()
        target, problem = check_new_project(self.form["name"], self.form["location"])
        text = f"Your game will be created in {target}" if target else problem
        self._target_label.text = text if len(text) <= 130 else text[:127] + "..."
        self._target_label.update_font(font_color=C_MUTED if target else C_ERROR)
        self._target_label.fit_content()

    def _opening(self, root: Any) -> None:
        box = gui.UIBoxLayout(vertical=True, align="left", space_between=10)
        box.add(self._title())
        name = self.opening["name"] if self.opening else ""
        box.add(self._label(f"Opening {name} in Mesh Studio...", size=14))
        root.add(box, anchor_x="left", anchor_y="top", align_x=40, align_y=-48)

    # ---------------------------------------------------------------- automated GUI tests
    def _dump_layout(self) -> None:
        """What is on screen, and where (only with MESH_LAUNCHER_LAYOUT=<path>, for GUI tests)."""
        path = os.environ.get("MESH_LAUNCHER_LAYOUT")
        if not path:
            return
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 10:
            return
        keys = {id(field): key for key, field in self._fields.items()}
        widgets = []
        for widget in self.ui.walk_widgets():
            rect = [widget.left, widget.bottom, widget.width, widget.height]
            if isinstance(widget, gui.UIFlatButton):
                widgets.append({"type": "button", "text": widget.text, "rect": rect, "disabled": widget.disabled})
            elif isinstance(widget, gui.UIInputText):
                widgets.append({"type": "field", "key": keys.get(id(widget)), "text": widget.text, "rect": rect,
                                "active": widget.active})
        for template_id, card in self._cards.items():
            widgets.append({"type": "card", "text": template_id, "rect": [card.left, card.bottom, card.width, card.height]})
        target, problem = check_new_project(self.form["name"], self.form["location"]) if self.screen == "new" else (None, "")
        state = {"screen": self.screen, "message": self.message, "ok": self.message_ok, "template": self.template.id,
                 "target": str(target) if target else None, "problem": problem,
                 "window": [self.window.width, self.window.height], "widgets": widgets,
                 "recent": [{k: v for k, v in r.items() if k != "button"} for r in self._recent_rows],
                 "studio_pid": self.opening["proc"].pid if self.opening else None}
        try:
            with open(f"{path}.tmp", "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            os.replace(f"{path}.tmp", path)
        except OSError:
            pass  # a test is reading it; the next dump will land


def fresh_log(path: Path) -> Path:
    """Make way for a new log at ``path``, keeping the last run's as ``<name>.previous.log``.

    A crash's log must survive the next launch, which is usually the first thing people try.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.replace(path.with_suffix(".previous.log"))
    except OSError:
        pass  # no earlier log (or it's still open somewhere): start fresh
    return path


def show_crash(what: str, log_path: Path | str) -> None:
    """Tell the person, in a message box, that ``what`` stopped and where the details are.

    Without a console (pythonw) a crash otherwise just makes the window vanish.
    """
    if sys.platform == "win32":
        text = f"{what} stopped because of an error.\n\nThe details are in:\n{log_path}"
        ctypes.windll.user32.MessageBoxW(None, text, "Mesh Studio", 0x10)  # MB_ICONERROR


def main() -> int:
    if sys.stdout is None:  # started without a console (pythonw): keep a log instead
        log_path = fresh_log(projects.user_data_dir() / "logs" / "launcher.log")
        sys.stdout = sys.stderr = open(log_path, "w", encoding="utf-8", buffering=1)

        def crashed(kind, value, tb) -> None:
            sys.__excepthook__(kind, value, tb)  # the traceback goes to the log
            show_crash("The Mesh launcher", log_path)

        sys.excepthook = crashed
    window = optional_arcade.arcade.Window(WIDTH, HEIGHT, "Mesh Studio")
    set_app_icon(window)
    window.center_window()  # Windows' default placement can push the bottom (and its buttons) off-screen
    Launcher(window)
    optional_arcade.arcade.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
