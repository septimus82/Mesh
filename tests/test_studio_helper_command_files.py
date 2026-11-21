"""T-01: the Studio test helper (tests/studio_owner_process.py) reads its numbered command files through a bounded
retry of Windows sharing violations, and a helper that dies tells the test why (the tail of its stderr)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests.studio_owner_process import read_command
from tests.test_studio_project_ownership import StudioProcess

pytestmark = pytest.mark.integration
windows_only = pytest.mark.skipif(os.name != "nt", reason="sharing violations are Windows-only; the Windows lane runs this on Windows")


def _hold(path: Path) -> Any:
    """Open ``path`` with no sharing, as another process's scan does; ``release()`` lets go."""
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                              wintypes.DWORD, wintypes.HANDLE]
    handle = k.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)  # read access, share mode none
    assert handle not in (None, wintypes.HANDLE(-1).value)
    return type("Held", (), {"release": staticmethod(lambda: k.CloseHandle(handle))})


@windows_only
def test_a_sharing_violation_that_clears_is_retried(tmp_path: Path) -> None:
    command = tmp_path / "0002.cmd"
    command.write_text("state", encoding="utf-8")
    held = _hold(command)
    with pytest.raises(PermissionError):  # (the violation is real: a plain read fails)
        command.read_text(encoding="utf-8")
    threading.Timer(0.1, held.release).start()
    assert read_command(command) == "state"


@windows_only
def test_a_sharing_violation_that_stays_is_raised_as_it_was(tmp_path: Path) -> None:
    command = tmp_path / "0002.cmd"
    command.write_text("state", encoding="utf-8")
    held = _hold(command)
    try:
        started = time.perf_counter()
        with pytest.raises(PermissionError):
            read_command(command, attempts=5, pause=0.01)
        assert time.perf_counter() - started < 2
    finally:
        held.release()


def test_only_a_permission_error_is_retried(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_command(tmp_path / "0001.cmd", attempts=5, pause=5.0)  # (a retry would sleep 20 s)


def test_a_helper_that_crashes_has_its_exception_in_the_failure(tmp_path: Path) -> None:
    with pytest.raises(AssertionError) as caught:
        StudioProcess(tmp_path / "no such project", log=tmp_path / "studio.log")
    message = str(caught.value)
    assert "ended without answering" in message and "stderr" in message
    assert "Traceback" in message and "Error" in message.rsplit("Traceback", 1)[1]
