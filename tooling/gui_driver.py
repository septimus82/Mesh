"""Drive a real Mesh window with OS-level mouse/keyboard input and capture screenshots.

Windows only. Used for whole-workflow acceptance checks: the input goes through the OS,
pyglet and the engine's real dispatch, exactly as a person's would.

Coordinates passed to click()/drag() are in the game's logical client space with the
origin at the TOP-LEFT (as in a screenshot), so a 1280x720 window always takes 0..1280,
0..720 regardless of monitor DPI scaling.
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
# Physical coordinates everywhere: the game is DPI-unaware, this driver is per-monitor aware.
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
# Pointer-sized handles: without these, HWND_TOPMOST (-1) went out as a 32-bit int and
# SetWindowPos failed with "invalid window handle", silently.
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
HWND_TOPMOST = wintypes.HWND(-1)

_INPUT_MOUSE, _INPUT_KEYBOARD = 0, 1
_KEYUP, _UNICODE = 0x0002, 0x0004
_MOVE, _ABSOLUTE, _VIRTUALDESK = 0x0001, 0x8000, 0x4000
_LDOWN, _LUP, _RDOWN, _RUP = 0x0002, 0x0004, 0x0008, 0x0010
_MDOWN, _MUP, _WHEEL = 0x0020, 0x0040, 0x0800
_BUTTONS = {"left": (_LDOWN, _LUP), "right": (_RDOWN, _RUP), "middle": (_MDOWN, _MUP)}

VK = {
    "ENTER": 0x0D, "ESC": 0x1B, "BACKSPACE": 0x08, "TAB": 0x09, "SPACE": 0x20, "DELETE": 0x2E,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28, "HOME": 0x24, "END": 0x23, "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
}


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _send(*inputs: _INPUT) -> None:
    arr = (_INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))


def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
    return _INPUT(type=_INPUT_KEYBOARD, u=_INPUTUNION(ki=_KEYBDINPUT(vk, scan, flags, 0, 0)))


def _find_window(pid: int) -> int:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return found[0] if found else 0


def _window_title(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def find_windows_by_title(prefix: str) -> list[int]:
    """Every visible top-level window whose title starts with ``prefix``."""
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and _window_title(hwnd).startswith(prefix):
            found.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return found


def find_window_by_title(prefix: str) -> int:
    """A visible top-level window whose title starts with ``prefix`` (0 if none)."""
    found = find_windows_by_title(prefix)
    return found[0] if found else 0


class _Process:
    """Enough of subprocess.Popen to drive (and stop) a process this script didn't start."""

    _QUERY, _TERMINATE, _STILL_ACTIVE = 0x1000, 0x0001, 259

    def __init__(self, pid: int) -> None:
        self.pid, self.returncode = pid, None

    def poll(self) -> int | None:
        handle = ctypes.windll.kernel32.OpenProcess(self._QUERY, False, self.pid)
        if not handle:
            self.returncode = self.returncode if self.returncode is not None else 0
            return self.returncode
        code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        if code.value != self._STILL_ACTIVE:
            self.returncode = code.value
        return self.returncode

    def wait(self, timeout: float = 30.0) -> int:
        deadline = time.time() + timeout
        while self.poll() is None:
            if time.time() > deadline:
                raise subprocess.TimeoutExpired(str(self.pid), timeout)
            time.sleep(0.2)
        return int(self.returncode or 0)

    def terminate(self) -> None:
        handle = ctypes.windll.kernel32.OpenProcess(self._TERMINATE, False, self.pid)
        if handle:
            ctypes.windll.kernel32.TerminateProcess(handle, 1)
            ctypes.windll.kernel32.CloseHandle(handle)

    kill = terminate


class Driver:
    @classmethod
    def attach(cls, title_prefix: str, shots: Path, logical_size: tuple[int, int] = (1280, 720),
               timeout: float = 60.0) -> "Driver":
        """Drive a window started some other way (e.g. by double-clicking a .bat), found by its title."""
        deadline, hwnd = time.time() + timeout, 0
        while not hwnd:
            found = find_windows_by_title(title_prefix)
            if len(found) > 1:
                # Driving the wrong one of two same-titled windows once looked exactly like lost clicks.
                raise RuntimeError(f"{len(found)} windows titled '{title_prefix}...' are open; close the others first")
            hwnd = found[0] if found else 0
            if not hwnd:
                if time.time() > deadline:
                    raise RuntimeError(f"no window titled '{title_prefix}...' appeared within {timeout:.0f}s")
                time.sleep(0.3)
        self = cls.__new__(cls)
        self.shots = Path(shots)
        self.shots.mkdir(parents=True, exist_ok=True)
        self.logical_w, self.logical_h = logical_size
        self.log_path = self.shots / "attached.log"  # the app logs elsewhere; see its own log files
        self._log = open(self.log_path, "w", encoding="utf-8")
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        self.proc = _Process(pid.value)  # type: ignore[assignment]
        self.hwnd = hwnd
        self._cursor = None
        time.sleep(2.0)  # first frames
        self.focus()
        return self

    def move_window(self, x: int, y: int) -> None:
        """Move the window's top-left corner to screen point (x, y) (physical pixels), e.g. onto another monitor."""
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, int(x), int(y), 0, 0, 0x0001)  # TOPMOST, NOSIZE
        time.sleep(0.8)  # a DPI-unaware window is rescaled when it changes monitor
        self._cursor = None
        self.focus()

    def title(self) -> str:
        return _window_title(self.hwnd)

    def click_close_button(self, timeout: float = 20.0) -> None:
        """Click the window's own close (X) button, as a person would, and wait for the window to go."""
        self._require_foreground()
        target = self._frame_point("close")
        if target is None:
            raise RuntimeError("couldn't find the window's close button")
        self._require_untouched_mouse()
        self._screen_click(*target)
        deadline = time.time() + timeout
        while user32.IsWindow(self.hwnd) and user32.IsWindowVisible(self.hwnd):
            if time.time() > deadline:
                raise RuntimeError("the window didn't close")
            time.sleep(0.2)

    def __init__(self, cmd: list[str], cwd: Path, shots: Path, logical_size: tuple[int, int] = (1280, 720)) -> None:
        self.shots = Path(shots)
        self.shots.mkdir(parents=True, exist_ok=True)
        self.logical_w, self.logical_h = logical_size
        self.log_path = self.shots / "app.log"
        self._log = open(self.log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=self._log, stderr=subprocess.STDOUT,
                                     env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"})
        self.hwnd = 0
        self._cursor: tuple[int, int] | None = None  # where this driver last put the mouse
        deadline = time.time() + 60
        while not self.hwnd and time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"app exited early ({self.proc.returncode}); see {self.log_path}")
            time.sleep(0.5)
            self.hwnd = _find_window(self.proc.pid)
        if not self.hwnd:
            raise RuntimeError("no window appeared within 60s")
        time.sleep(2.0)  # first frames
        self.focus()

    # --- window ---------------------------------------------------------------------------
    def note(self, text: str) -> None:
        """Timestamped line in this driver's log (what it did, to line up with the app's own log)."""
        if not self._log.closed:
            self._log.write(f"[driver] {time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {text}\n")
            self._log.flush()

    def focus(self) -> None:
        """Bring the window to the front the way a person does: click its title bar.

        Windows only lets a process bring a window forward after user input, so this used
        to minimise and restore the window instead. That left the window deactivated and
        deaf to the next click: the "first clicks ignored at start-up" seen in GUI runs.
        A click on the title bar is ordinary input to the window's own frame.
        """
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002)  # TOPMOST (kept visible), NOSIZE|NOMOVE
        for _ in range(5):
            if user32.GetForegroundWindow() == self.hwnd:
                return
            point = self._frame_point("caption")
            if point is None:
                raise RuntimeError("couldn't find the window's title bar to bring it to the front")
            self.note(f"focus: click the title bar at {point}")
            self._screen_click(*point)
            time.sleep(0.4)

    def _frame_point(self, part: str) -> tuple[int, int] | None:
        """A screen point (physical pixels) on the title bar: ``"caption"`` or ``"close"`` (the X).

        Worked out from the window and client rectangles, both physical for this DPI-aware
        driver. (WM_NCHITTEST would answer in the DPI-unaware window's own scaled coordinates.)
        """
        rect = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        left, client_top, width, _height = self._client_box()
        if client_top - rect.top < 10:
            return None  # no title bar
        y = (rect.top + client_top) // 2 + 2
        if part == "close":
            return left + width - 18, y
        for x in range(left + width // 2, left + width - 160, 16):  # the middle first; clear of the buttons
            if user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x, y)), 2) == self.hwnd:
                return x, y  # not covered by another window
        return None

    def _screen_click(self, x: int, y: int) -> None:
        """Move to a screen point (physical pixels) and click it."""
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        nx, ny = int((x - vx) * 65535 / max(1, vw - 1)), int((y - vy) * 65535 / max(1, vh - 1))
        _send(_INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(nx, ny, 0, _MOVE | _ABSOLUTE | _VIRTUALDESK, 0, 0))))
        time.sleep(0.15)
        _send(_INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, _LDOWN, 0, 0))))
        time.sleep(0.06)
        _send(_INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, _LUP, 0, 0))))
        self._cursor = None  # moved outside the client area on purpose

    def _require_foreground(self) -> None:
        # Synthetic input goes to whatever window has focus; never type into someone else's app.
        if user32.GetForegroundWindow() != self.hwnd:
            self.focus()
        if user32.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("game window is not in the foreground; refusing to send input")

    def _require_hit(self, sx: int, sy: int) -> None:
        hit = user32.WindowFromPoint(wintypes.POINT(sx, sy))
        if user32.GetAncestor(hit, 2) != self.hwnd:  # GA_ROOT
            raise RuntimeError(f"point ({sx},{sy}) is not over the game window; refusing to click")

    def _client_box(self) -> tuple[int, int, int, int]:
        rect = wintypes.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(rect))
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(origin))
        return origin.x, origin.y, rect.right, rect.bottom

    def _to_screen(self, x: float, y: float) -> tuple[int, int]:
        ox, oy, w, h = self._client_box()
        return int(ox + x * w / self.logical_w), int(oy + y * h / self.logical_h)

    # --- mouse ----------------------------------------------------------------------------
    def _require_untouched_mouse(self) -> None:
        """Stop if someone moved the real mouse: their input would mix with ours and the result mean nothing."""
        if self._cursor is None:
            return
        pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        if abs(pos.x - self._cursor[0]) > 16 or abs(pos.y - self._cursor[1]) > 16:  # beyond hand jitter
            raise RuntimeError(f"the mouse was moved by something other than this test (expected {self._cursor}, "
                               f"found {(pos.x, pos.y)}); keep hands off the mouse while a GUI test runs")

    def _mouse_to(self, x: float, y: float) -> None:
        self._require_untouched_mouse()
        self._require_foreground()
        sx, sy = self._to_screen(x, y)
        self._require_hit(sx, sy)
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        nx, ny = int((sx - vx) * 65535 / max(1, vw - 1)), int((sy - vy) * 65535 / max(1, vh - 1))
        _send(_INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(nx, ny, 0, _MOVE | _ABSOLUTE | _VIRTUALDESK, 0, 0))))
        time.sleep(0.05)
        pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        self._cursor = (pos.x, pos.y)  # where the move actually landed (normalised coordinates round)

    def _button(self, flags: int) -> None:
        self._require_untouched_mouse()
        _send(_INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, flags, 0, 0))))

    def click(self, x: float, y: float, *, right: bool = False, settle: float = 0.4) -> None:
        self._mouse_to(x, y)
        self.note(f"click at ({x:.0f}, {y:.0f}) cursor {self._cursor}")
        down, up = (_RDOWN, _RUP) if right else (_LDOWN, _LUP)
        self._button(down)
        time.sleep(0.06)
        self._button(up)
        time.sleep(settle)

    def drag(self, x0: float, y0: float, x1: float, y1: float, steps: int = 12, button: str = "left") -> None:
        down, up = _BUTTONS[button]
        self._mouse_to(x0, y0)
        self._button(down)
        for i in range(1, steps + 1):
            self._mouse_to(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        self._button(up)
        time.sleep(0.4)

    def scroll(self, x: float, y: float, notches: int) -> None:
        """Turn the mouse wheel at (x, y); positive is away from the user."""
        self._mouse_to(x, y)
        _send(_INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(0, 0, (120 * notches) & 0xFFFFFFFF, _WHEEL, 0, 0))))
        time.sleep(0.3)

    # --- keyboard -------------------------------------------------------------------------
    def key(self, combo: str, *, hold: float = 0.06, settle: float = 0.3) -> None:
        """Press a key or chord, e.g. "ENTER", "CTRL+S", "SHIFT+F5"."""
        self._require_foreground()
        names = combo.upper().split("+")
        codes = [VK[n] for n in names]
        for c in codes:
            _send(_key_input(vk=c))
        time.sleep(hold)
        for c in reversed(codes):
            _send(_key_input(vk=c, flags=_KEYUP))
        time.sleep(settle)

    def hold(self, name: str, seconds: float) -> None:
        self._require_foreground()
        code = VK[name.upper()]
        _send(_key_input(vk=code))
        time.sleep(seconds)
        _send(_key_input(vk=code, flags=_KEYUP))
        time.sleep(0.2)

    def type_text(self, text: str, settle: float = 0.3) -> None:
        """Type via Unicode input events (reaches the app's on_text exactly like a keyboard)."""
        for ch in text:
            self._require_foreground()
            _send(_key_input(scan=ord(ch), flags=_UNICODE), _key_input(scan=ord(ch), flags=_UNICODE | _KEYUP))
            time.sleep(0.03)
        time.sleep(settle)

    def file_dialog(self, path: str, timeout: float = 15.0) -> None:
        """Answer the app's own open-file dialog: type ``path`` into it and press Enter.

        Input only goes to a dialog window owned by the app's process.
        """
        deadline, dialog = time.time() + timeout, 0
        while not dialog:
            hwnd = user32.GetForegroundWindow()
            name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, name, 64)
            if self._owns(hwnd) and hwnd != self.hwnd and name.value == "#32770":
                dialog = hwnd
            elif time.time() > deadline:
                raise RuntimeError("the app's file dialog didn't appear")
            else:
                time.sleep(0.2)
        time.sleep(0.8)  # the file-name box has the keyboard focus once the dialog has settled
        for ch in path:
            if not self._owns(user32.GetForegroundWindow()):  # the dialog, or its autocomplete list
                raise RuntimeError("the file dialog lost the focus while typing into it")
            _send(_key_input(scan=ord(ch), flags=_UNICODE), _key_input(scan=ord(ch), flags=_UNICODE | _KEYUP))
            time.sleep(0.02)
        _send(_key_input(vk=VK["ENTER"]), _key_input(vk=VK["ENTER"], flags=_KEYUP))
        settle = time.time() + 1.5
        while user32.IsWindow(dialog) and time.time() < settle:
            time.sleep(0.2)
        if user32.IsWindow(dialog):
            # A folder picker opens the typed folder on Enter; its OK button ("Select Folder"
            # in any language: control id IDOK) then chooses it.
            ok_button = user32.GetDlgItem(dialog, 1)
            rect = wintypes.RECT()
            if not ok_button or not user32.GetWindowRect(ok_button, ctypes.byref(rect)):
                raise RuntimeError("the file dialog stayed open and has no OK button")
            self.note("file dialog: click its OK button")
            self._screen_click((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        while user32.IsWindow(dialog):
            if time.time() > deadline:
                raise RuntimeError("the file dialog didn't close")
            time.sleep(0.2)
        time.sleep(0.5)
        self.focus()
        self._cursor = None  # dialogs may move the pointer (Windows' "snap to default button")

    def _owns(self, hwnd: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        return owner.value == self.proc.pid

    def pixel(self, x: float, y: float) -> tuple[int, int, int]:
        """The colour at a point of the window (logical coordinates, top-left origin), from a fresh capture."""
        with Image.open(self.shot("_pixel")) as image:
            return image.convert("RGB").getpixel((int(x), int(y)))

    # --- evidence -------------------------------------------------------------------------
    def shot(self, name: str) -> Path:
        """Capture the window's own surface (PrintWindow): correct even if something overlaps it."""
        _, _, w, h = self._client_box()
        hdc = user32.GetDC(self.hwnd)
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem, bmp)
        user32.PrintWindow(self.hwnd, mem, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        info = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(info), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(self.hwnd, hdc)
        # A DPI-unaware window's surface is its logical size, drawn into the top-left corner.
        path = self.shots / f"{name}.png"
        Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).crop((0, 0, self.logical_w, self.logical_h)).save(path)
        return path

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def log_text(self) -> str:
        if not self._log.closed:
            self._log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._log.close()
