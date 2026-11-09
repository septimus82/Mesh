"""Import first: makes this process's OpenGL Mesa's llvmpipe (software), as CI's Windows jobs have it, by loading
Mesa's opengl32.dll from ./mesa/x64 (extracted from CI's pinned mesa3d-26.0.3-release-msvc.7z, SHA-256 de1ec45c...6755; not committed) before pyglet asks Windows for 'opengl32' (Windows reuses a loaded module of
that name). Nothing is installed or registered."""
import ctypes
import os
from pathlib import Path

MESA = Path(__file__).parent / "mesa" / "x64"
os.environ["GALLIUM_DRIVER"] = "llvmpipe"
os.add_dll_directory(str(MESA))
ctypes.WinDLL(str(MESA / "opengl32.dll"))
