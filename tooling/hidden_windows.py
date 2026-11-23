"""Hidden test and tooling windows never activate on Windows: no focus, no keystrokes taken from the person.

pyglet's win32 window places every new window with SetWindowPos without SWP_NOACTIVATE, and set_size and set_location
do the same. That activates even a window created with ``visible=False`` and brings it to the front when Windows
allows: a hidden GPU-test window took the keyboard from the owner's full-screen game for about a second, and a hidden
probe window caught a real key press whose release never came (the key stuck). ``no_activate()`` makes those calls
non-activating while the window is hidden and stays hidden, and refuses SetForegroundWindow for a hidden window.
Showing a window (``set_visible()``: SWP_SHOWWINDOW, then activate) is left exactly as pyglet does it.

Call it in a test or tooling process before its first window (tests/conftest.py does, at import, for the test run).
Never in the game or Mesh Studio as a person runs them. Does nothing outside Windows. Self-contained, with no imports
from Mesh and no ``__future__`` import: the installed-product checks put this source in front of the scripts they run
outside the repository.
"""

import sys
from typing import Any, cast

SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x0010, 0x0040


class _NoActivateUser32:
    """pyglet's user32 library, with SetWindowPos and SetForegroundWindow unable to activate a hidden window."""

    mesh_no_activate = True

    def __init__(self, user32: Any) -> None:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        self._user32 = user32
        self._is_visible = cast(Any, ctypes).WinDLL("user32").IsWindowVisible  # (its own copy: argtypes set here only)
        self._is_visible.argtypes, self._is_visible.restype = [wintypes.HWND], wintypes.BOOL

    def __getattr__(self, name: str) -> Any:
        return getattr(self._user32, name)

    def SetWindowPos(self, hwnd: object, after: object, x: int, y: int, cx: int, cy: int, flags: int) -> Any:  # noqa: N802
        if not flags & SWP_SHOWWINDOW and not self._is_visible(hwnd):
            flags |= SWP_NOACTIVATE
        return self._user32.SetWindowPos(hwnd, after, x, y, cx, cy, flags)

    def SetForegroundWindow(self, hwnd: object) -> Any:  # noqa: N802
        if not self._is_visible(hwnd):
            return False
        return self._user32.SetForegroundWindow(hwnd)


def no_activate() -> None:
    """From now on, no pyglet window in this process activates while it is hidden (Windows; elsewhere nothing).
    Safe to call more than once, and before or after pyglet.window is imported."""
    if sys.platform != "win32":
        return
    import pyglet.libs.win32 as libs  # noqa: PLC0415  # (opens no window, and leaves DPI awareness alone)

    if not getattr(libs._user32, "mesh_no_activate", False):  # noqa: SLF001
        # (pyglet.window.win32 imports it from here; through the module's dict: the wrapper stands in for its WinDLL)
        vars(libs)["_user32"] = _NoActivateUser32(libs._user32)  # noqa: SLF001
    window_module = sys.modules.get("pyglet.window.win32")
    if window_module is not None:  # (already imported: it holds its own reference)
        vars(window_module)["_user32"] = libs._user32  # noqa: SLF001
