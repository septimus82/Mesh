"""Import first: makes this process's OpenGL Mesa's llvmpipe (software), as CI's Windows jobs have it, by loading
Mesa's opengl32.dll from the scratch copy before pyglet asks Windows for 'opengl32' (Windows reuses a loaded module of
that name). Nothing is installed or registered."""
import ctypes
import os
from pathlib import Path

MESA = Path(__file__).parent / "mesa" / "x64"
os.environ["GALLIUM_DRIVER"] = "llvmpipe"
os.add_dll_directory(str(MESA))
ctypes.WinDLL(str(MESA / "opengl32.dll"))
