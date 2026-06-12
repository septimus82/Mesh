# Backward-compat shim -- canonical module is engine.editor.hd2d.editor_hd2d_controller
import importlib as _importlib
import sys as _sys

from engine.editor.hd2d.editor_hd2d_controller import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.editor.hd2d.editor_hd2d_controller")
