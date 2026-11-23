"""A hidden test window never activates (Windows): it never becomes the foreground or active window and never gets
WM_ACTIVATE, when created, resized or moved. pyglet's own SetWindowPos calls activated such windows and took the
keyboard from the person's full-screen game (tooling/hidden_windows.py; tests/conftest.py installs it for the run).
The window is made as the tests make theirs: pyglet's Window, hidden by tests/conftest.py. GL-gated: MESH_GL_SMOKE=1.
The wrapper's rule itself is checked fast, on every system, with stand-in user32 functions (no window)."""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

from engine import optional_arcade

WM_ACTIVATE = 0x0006
HWND_TOP, SWP_NOSIZE, SWP_NOMOVE = 0, 0x0001, 0x0002


def _wrapper(visible: set[int]) -> tuple[Any, list[tuple[str, tuple[Any, ...]]]]:
    """tooling/hidden_windows's wrapper around stand-in user32 functions, which record their calls; ``visible``: the
    windows shown (IsWindowVisible)."""
    from tooling.hidden_windows import _NoActivateUser32

    calls: list[tuple[str, tuple[Any, ...]]] = []

    class User32:
        def SetWindowPos(self, *args: Any) -> int:  # noqa: N802
            calls.append(("SetWindowPos", args))
            return 1

        def SetForegroundWindow(self, *args: Any) -> int:  # noqa: N802
            calls.append(("SetForegroundWindow", args))
            return 1

        def DefWindowProcW(self, *args: Any) -> int:  # noqa: N802
            calls.append(("DefWindowProcW", args))
            return 7

    wrapper = _NoActivateUser32.__new__(_NoActivateUser32)  # (without __init__: no real user32 here)
    wrapper._user32, wrapper._is_visible = User32(), lambda hwnd: hwnd in visible
    return wrapper, calls


@pytest.mark.fast
def test_the_wrapper_makes_only_hidden_windows_non_activating() -> None:
    from tooling.hidden_windows import SWP_NOACTIVATE, SWP_SHOWWINDOW

    shown, hidden = 1, 2
    wrapper, calls = _wrapper({shown})
    flags = SWP_NOMOVE | SWP_NOSIZE
    wrapper.SetWindowPos(shown, HWND_TOP, 0, 0, 10, 10, flags)  # a shown window: unchanged
    wrapper.SetForegroundWindow(shown)
    wrapper.SetWindowPos(hidden, HWND_TOP, 0, 0, 10, 10, flags)  # hidden, staying hidden: never activates
    assert wrapper.SetForegroundWindow(hidden) is False  # (not passed on)
    wrapper.SetWindowPos(hidden, HWND_TOP, 0, 0, 0, 0, flags | SWP_SHOWWINDOW)  # being shown: as pyglet does it
    assert wrapper.DefWindowProcW(hidden, 0, 0, 0) == 7  # everything else passes through
    assert calls == [
        ("SetWindowPos", (shown, HWND_TOP, 0, 0, 10, 10, flags)),
        ("SetForegroundWindow", (shown,)),
        ("SetWindowPos", (hidden, HWND_TOP, 0, 0, 10, 10, flags | SWP_NOACTIVATE)),
        ("SetWindowPos", (hidden, HWND_TOP, 0, 0, 0, 0, flags | SWP_SHOWWINDOW)),
        ("DefWindowProcW", (hidden, 0, 0, 0)),
    ]


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only (window activation): the Windows gpu lane runs this on Windows")
@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                    reason="real-window test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)")
def test_a_hidden_window_never_activates_when_created_resized_or_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    import ctypes
    from ctypes import wintypes

    optional_arcade.arcade  # noqa: B018  # (first: DPI-unaware and no shadow window, as the engine runs)
    import pyglet.window
    from pyglet.window.win32 import Win32Window

    activated: list[Any] = []
    original = Win32Window._get_window_proc

    def recording(window: Any, handlers: dict) -> Any:  # every message the window gets, WM_ACTIVATE noted
        proc = original(window, handlers)

        def f(hwnd: Any, msg: int, wparam: int, lparam: int) -> Any:
            if msg == WM_ACTIVATE and wparam & 0xFFFF:  # (WA_ACTIVE or WA_CLICKACTIVE; WA_INACTIVE is 0)
                activated.append(hwnd)
            return proc(hwnd, msg, wparam, lparam)

        return f

    monkeypatch.setattr(Win32Window, "_get_window_proc", recording)
    user32 = ctypes.WinDLL("user32")  # (its own copy: argtypes set here only)
    for name in ("GetForegroundWindow", "GetActiveWindow"):
        getattr(user32, name).argtypes, getattr(user32, name).restype = [], wintypes.HWND

    window = pyglet.window.Window(160, 120, caption="Mesh hidden-window activation check")
    try:
        hwnd = window._hwnd  # noqa: SLF001
        seen = {"created": (user32.GetForegroundWindow(), user32.GetActiveWindow())}
        window.set_size(200, 150)
        seen["resized"] = (user32.GetForegroundWindow(), user32.GetActiveWindow())
        window.set_location(40, 40)
        seen["moved"] = (user32.GetForegroundWindow(), user32.GetActiveWindow())
        window.dispatch_events()
        assert not window.visible
        assert activated == [], f"the hidden window got WM_ACTIVATE {len(activated)} time(s)"
        assert {step: (fg == hwnd, active == hwnd) for step, (fg, active) in seen.items()} == \
            dict.fromkeys(seen, (False, False)), "the hidden window became the foreground or active window"
    finally:
        window.close()
