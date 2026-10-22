"""The look and the small widgets Mesh Studio and the Mesh launcher share.

Colours, button styles, a single-line text field with clipboard keys, the operating
system's file and folder pickers, and a start-up click logger. Both windows use
arcade.gui (through ``optional_arcade``), so they look and behave the same.
"""

from __future__ import annotations

import time
from typing import Any

import engine.optional_arcade as optional_arcade

gui = optional_arcade.gui()

C_BG = (30, 32, 38)
C_PANEL = (38, 41, 49)
C_TEXT = (220, 224, 232)
C_MUTED = (140, 146, 160)
C_ERROR = (255, 120, 110)
C_OK = (130, 210, 150)
C_SELECT = (90, 200, 255)
C_SPAWN = (120, 230, 140)


def button_style(bg: tuple[int, int, int], fg: tuple[int, int, int] = C_TEXT) -> dict[str, Any]:
    base = gui.UIFlatButton.UIStyle(font_size=11, font_color=fg, bg=bg, border=None, border_width=0)
    return {
        "normal": base,
        "hover": gui.UIFlatButton.UIStyle(font_size=11, font_color=fg, bg=tuple(min(255, c + 22) for c in bg), border=None, border_width=0),
        "press": gui.UIFlatButton.UIStyle(font_size=11, font_color=fg, bg=tuple(max(0, c - 18) for c in bg), border=None, border_width=0),
        "disabled": gui.UIFlatButton.UIStyle(font_size=11, font_color=C_MUTED, bg=(48, 50, 58), border=None, border_width=0),
    }


S_BUTTON = button_style((58, 63, 76))
S_ACTIVE = button_style((48, 110, 170))
S_DANGER = button_style((120, 52, 52))
S_PLAY = button_style((44, 120, 70))
S_MENU = button_style((52, 56, 68))


class TextField(gui.UIInputText):
    """Single-line text field whose caret lands at the end when you click into it.

    arcade.gui's own click handling leaves the caret at position 0, so clicking a
    field and typing would put the new text in front of the old.
    """

    def on_event(self, event: Any) -> bool | None:
        if isinstance(event, gui.UITextInputEvent) and any(ord(ch) < 32 for ch in event.text):
            return True  # Enter, Tab and Ctrl+letter arrive as control characters; never type them
        was_active = self.active
        handled = super().on_event(event)
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
