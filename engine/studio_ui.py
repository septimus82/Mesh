"""The look and the small widgets Mesh Studio and the Mesh launcher share.

Colours, button styles, a single-line text field with clipboard keys, the operating
system's file and folder pickers, and a start-up click logger. Both windows use
arcade.gui (through ``optional_arcade``), so they look and behave the same.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import engine.optional_arcade as optional_arcade

gui = optional_arcade.gui()

# The theme, "Graphite + MeshMind cyan" (Milestone 15; docs/reviews/milestone15_stage1_visual_direction.md).
# Surfaces carry no colour; the one accent is the MeshMind logo's cyan and means selected / focused.
FONT = ("Segoe UI", "Calibri", "Arial")  # the Windows UI font, then what other systems have
C_CANVAS = (17, 19, 23)  # the workspace around the map
C_MAP_EDGE = (96, 104, 118)  # the map's border on it
C_BG = (21, 23, 28)  # the window, the status bar
C_PANEL = (27, 30, 36)  # the side panels
C_RAISED = (34, 38, 46)  # the top bar, menus, dialogs
C_LINE = (44, 49, 58)  # dividers and button outlines
C_BUTTON = (40, 45, 54)
C_FIELD = (17, 19, 23)  # text fields and picture wells
C_FIELD_EDGE = (62, 68, 80)
C_TEXT = (228, 232, 238)
C_MUTED = (138, 146, 160)
C_ACCENT = (0, 156, 240)  # MeshMind cyan
C_ACCENT_DIM = (16, 62, 92)  # a selected button's fill
C_ACCENT_TEXT = (190, 230, 255)
C_SELECT = (0, 176, 248)  # selection on the map: the logo's lighter cyan, to read over any tiles
C_OK = (110, 205, 150)
C_WARN = (240, 200, 120)
C_ERROR = (240, 110, 100)
C_PLAY = (28, 140, 96)
C_DANGER = (70, 34, 36)
C_DANGER_TEXT = (255, 190, 185)  # text on a danger surface
C_DANGER_EDGE = (130, 60, 60)
C_SPAWN = (120, 230, 140)


def button_style(bg: tuple[int, int, int], fg: tuple[int, int, int] = C_TEXT,
                 border: tuple[int, int, int] | None = None, size: int = 10) -> dict[str, Any]:
    def style(fill: tuple[int, int, int], colour: tuple[int, int, int], edge: tuple[int, int, int] | None) -> Any:
        return gui.UIFlatButton.UIStyle(font_size=size, font_name=FONT, font_color=colour, bg=fill, border=edge,
                                        border_width=1 if edge else 0)

    def shade(by: int) -> tuple[int, int, int]:
        r, g, b = (max(0, min(255, c + by)) for c in bg)
        return r, g, b

    return {
        "normal": style(bg, fg, border),
        "hover": style(shade(14), fg, border),
        "press": style(shade(-10), fg, border),
        "disabled": style(C_PANEL, C_MUTED, C_LINE),
    }


S_BUTTON = button_style(C_BUTTON, border=C_LINE)
S_ACTIVE = button_style(C_ACCENT_DIM, C_ACCENT_TEXT, border=C_ACCENT)  # selected: a cyan outline, a quiet fill
S_DANGER = button_style(C_DANGER, C_DANGER_TEXT, border=C_DANGER_EDGE)
S_PLAY = button_style(C_PLAY)
S_MENU = button_style(C_RAISED)
S_CARD = button_style(C_RAISED, border=C_LINE, size=11)  # a list entry: the launcher's recent projects
S_CARD_MISSING = button_style(C_DANGER, C_DANGER_TEXT, border=C_DANGER_EDGE, size=11)

# MeshMind Studios brand assets (assets/branding/NOTICE.md): the mark beside "Mesh Studio", the wordmark as the
# publisher's credit, and the app icon. A copy of Mesh without them still runs, unbranded.
BRANDING = Path(__file__).resolve().parents[1] / "assets" / "branding"
_BRAND_TEXTURES: dict[str, Any] = {}


def brand_texture(name: str) -> Any | None:
    """An image from assets/branding as a texture (loaded once), or None if it isn't there."""
    if name not in _BRAND_TEXTURES:
        path = BRANDING / name
        _BRAND_TEXTURES[name] = optional_arcade.arcade.load_texture(path) if path.is_file() else None
    return _BRAND_TEXTURES[name]


# Icons (Milestone 15 Stage 3): Lucide (ISC licence; assets/icons/lucide/LICENSE), drawn white by
# tooling/make_icons.py and tinted with the button's own text colour, so selected, disabled, hover and danger
# states need nothing of their own. A button's icon comes from its label, in this one table.
ICONS = Path(__file__).resolve().parents[1] / "assets" / "icons"
ICON_SIZE, ICON_GAP = 16, 6
BUTTON_ICONS = {
    "Play (F4)": "play", "Stop (F4)": "square", "Save": "save", "Undo": "undo-2", "Redo": "redo-2", "Flags": "flag",
    "Lighting": "lightbulb", "AI": "sparkles", "Menu (Esc)": "menu",
    # Ground / Walls / Above stay text-only: at 67 px, "Ground" and an icon don't fit, and the row stays alike.
    "Select": "mouse-pointer-2", "Eraser": "eraser",
    "Brush": "paintbrush", "Rect": "square", "Fill": "paint-bucket", "Import...": "image-plus", "Resize...": "scaling",
    "Person": "user", "Sign": "signpost", "Empty object": "box", "Trigger zone": "square-dashed",
    "Look": "eye", "Animation": "film", "Collision": "scan", "Dialogue": "message-square", "Conditions": "list-checks",
    "Behaviours": "sliders-horizontal", "Delete object": "trash-2", "Choose picture...": "image", "Import PNG...": "upload",
    "New Project": "folder-plus", "Open Project...": "folder-open", "Browse...": "folder", "Back": "arrow-left",
    "Create & Open": "check",
}
_ICON_TEXTURES: dict[tuple[str, int], Any] = {}


def icon_texture(name: str, size: int = ICON_SIZE) -> Any | None:
    """A white icon from assets/icons as a texture (loaded once), or None if it isn't there."""
    key = (name, size)
    if key not in _ICON_TEXTURES:
        path = ICONS / f"{name}_{size}.png"
        _ICON_TEXTURES[key] = optional_arcade.arcade.load_texture(path) if path.is_file() else None
    return _ICON_TEXTURES[key]


_Image: Any = gui.UIImage  # arcade.gui comes through optional_arcade, untyped
_FlatButton: Any = gui.UIFlatButton


class TintedImage(_Image):
    """An icon drawn in a colour: white artwork tinted to match the text beside it."""

    def __init__(self, *, texture: Any, tint: tuple[int, ...] = C_TEXT, **kwargs: Any) -> None:
        super().__init__(texture=texture, **kwargs)
        self._tint = tint

    @property
    def tint(self) -> tuple[int, ...]:
        return self._tint

    @tint.setter
    def tint(self, value: tuple[int, ...]) -> None:
        if tuple(value) != tuple(self._tint):
            self._tint = value
            self.trigger_render()

    def do_render(self, surface: Any) -> None:
        self.prepare_render(surface)
        a = optional_arcade.arcade
        a.draw_texture_rect(self.texture, a.LBWH(0, 0, self.content_width, self.content_height),
                            color=a.types.Color.from_iterable(self._tint))


class IconButton(_FlatButton):
    """A flat button with an icon left of its text, the pair centred. Same size, text and click target as a plain
    button; the icon is left out if it's missing or the text wouldn't fit beside it."""

    def __init__(self, *, icon: str | None = None, **kwargs: Any) -> None:
        self._icon: TintedImage | None = None
        super().__init__(**kwargs)
        texture = icon_texture(icon) if icon else None
        text_w = self.ui_label._label.content_width  # the text itself (the label widget's box adds padding)
        if texture is None or text_w + ICON_SIZE + ICON_GAP + 8 > self.width:
            return
        style = self.get_current_style()
        self._icon = TintedImage(texture=texture, width=ICON_SIZE, height=ICON_SIZE,
                                 tint=style.get("font_color", C_TEXT) if style else C_TEXT)
        self.place_text(anchor_x="center", align_x=(ICON_SIZE + ICON_GAP) / 2, anchor_y="center")
        self.add(self._icon, anchor_x="center", align_x=-text_w / 2 - ICON_GAP / 2, anchor_y="center")

    def _apply_style(self, style: Any) -> None:
        super()._apply_style(style)
        if self._icon is not None:
            self._icon.tint = style.get("font_color", C_TEXT)


class CardButton(_FlatButton):
    """A two-line list entry: an icon, the button's text as its title and a smaller line of detail under it. A
    button like any other (its text is the title; the whole card is the click target)."""

    def __init__(self, *, detail: str, detail_prefix: str = "", detail_color: tuple[int, int, int] = C_MUTED,
                 icon: str | None = None, **kwargs: Any) -> None:
        self._icon: TintedImage | None = None
        super().__init__(**kwargs)
        x = 14
        texture = icon_texture(icon, 32) if icon else None
        if texture is not None:
            style = self.get_current_style()
            self._icon = TintedImage(texture=texture, width=20, height=20, tint=style.get("font_color", C_TEXT) if style else C_TEXT)
            self.add(self._icon, anchor_x="left", align_x=x, anchor_y="center")
            x += 20 + 12
        self.place_text(anchor_x="left", align_x=x, anchor_y="top", align_y=-6)
        # The detail (a path) loses its start, not its end, when it's too long: "Missing: ...\Games\Old".
        line = gui.UILabel(text=detail_prefix + detail, font_size=9, font_name=FONT, text_color=detail_color)
        room, cut = self.width - x - 12, 0
        while line._label.content_width > room and cut < len(detail) - 4:
            cut += 2
            line.text = f"{detail_prefix}...{detail[cut:]}"
        line.fit_content()
        self.add(line, anchor_x="left", align_x=x, anchor_y="bottom", align_y=6)

    def _apply_style(self, style: Any) -> None:
        super()._apply_style(style)
        if self._icon is not None:
            self._icon.tint = style.get("font_color", C_TEXT)


def make_button(text: str, *, width: float, height: float, style: dict[str, Any], icon: str | None = None) -> Any:
    """Mesh Studio's button: ``icon`` (a name in assets/icons), else the one its label has in BUTTON_ICONS."""
    return IconButton(text=text, width=width, height=height, style=style, icon=icon or BUTTON_ICONS.get(text))


def set_app_icon(window: Any) -> None:
    """Mesh Studio's icon (the brain-and-network mark) on ``window``'s title bar and taskbar button."""
    import pyglet  # noqa: PLC0415

    images = [pyglet.image.load(str(path)) for size in (16, 24, 32, 48, 64, 256)
              if (path := BRANDING / f"mesh_studio_icon_{size}.png").is_file()]
    if images:
        window.set_icon(*images)


_InputText: Any = gui.UIInputText  # arcade.gui comes through optional_arcade, untyped


class TextField(_InputText):
    """Single-line text field whose caret lands at the end when you click into it.

    arcade.gui's own click handling leaves the caret at position 0, so clicking a
    field and typing would put the new text in front of the old.
    """

    def on_event(self, event: Any) -> bool | None:
        if isinstance(event, gui.UITextInputEvent) and any(ord(ch) < 32 for ch in event.text):
            return True  # Enter, Tab and Ctrl+letter arrive as control characters; never type them
        was_active = self.active
        handled: bool | None = super().on_event(event)
        if self.active and not was_active:
            self.caret.position = len(self.text)
        return handled


def field_clipboard(window: Any, field: Any, symbol: int) -> None:
    """Ctrl+A / C / X / V in a text field (arcade.gui fields have no clipboard of their own)."""
    k = optional_arcade.arcade.key
    layout = field.layout
    start, end = sorted((layout.selection_start, layout.selection_end))
    selected = field.text[start:end] if end > start else ""
    if symbol == k.A:
        field.caret.select_all()
    elif symbol in (k.C, k.X):
        window.set_clipboard_text(selected or field.text)
        if symbol == k.X:
            if selected:
                field.caret.on_text("")  # replaces the selection with nothing
            else:
                field.text = ""
    else:
        pasted = (window.get_clipboard_text() or "").replace("\r", "")
        field.caret.on_text(" ".join(pasted.split("\n")))  # fields are one line
    field.trigger_full_render()


def ask_path(*, folder: bool, title: str, initial: str = "", filetypes: list[tuple[str, str]] | None = None) -> str:
    """The operating system's own file or folder picker ("" if cancelled)."""
    import tkinter  # noqa: PLC0415
    from tkinter import filedialog  # noqa: PLC0415

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        if folder:
            return filedialog.askdirectory(parent=root, title=title, initialdir=initial or None, mustexist=False) or ""
        return filedialog.askopenfilename(parent=root, title=title, initialdir=initial or None,
                                          filetypes=filetypes or [("All files", "*.*")]) or ""
    finally:
        root.destroy()


class FirstClicks:
    """Logs a window's first input events (to diagnose clicks reported lost at start-up).

    The first mouse presses, the first mouse movements and every focus change, each with
    the time since the window opened. Keep a reference: pyglet holds event handlers weakly.
    """

    def __init__(self, name: str) -> None:
        self.name, self.started = name, time.perf_counter()
        self.counts: dict[str, int] = {}

    def _log(self, event: str, detail: str = "", limit: int = 3) -> None:
        count = self.counts[event] = self.counts.get(event, 0) + 1
        if count <= limit:
            now = time.time()
            clock = f"{time.strftime('%H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d}"
            print(f"[Mesh][{self.name}] {clock} {event} {count} at {time.perf_counter() - self.started:.1f}s {detail}".rstrip(),
                  flush=True)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        self._log("mouse press", f"({x:.0f}, {y:.0f})")

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        self._log("mouse move", f"({x:.0f}, {y:.0f})", limit=2)

    def on_activate(self) -> None:
        self._log("window activated", limit=5)

    def on_deactivate(self) -> None:
        self._log("window deactivated", limit=5)
