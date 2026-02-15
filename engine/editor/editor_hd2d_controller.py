# Backward-compat shim -- canonical module is engine.editor.hd2d.editor_hd2d_controller
from engine.editor.hd2d.editor_hd2d_controller import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.hd2d.editor_hd2d_controller")
