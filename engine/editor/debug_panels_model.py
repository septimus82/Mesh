# Backward-compat shim -- canonical module is engine.editor.debug.debug_panels_model
from engine.editor.debug.debug_panels_model import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.debug.debug_panels_model")
