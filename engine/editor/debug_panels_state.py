# Backward-compat shim -- canonical module is engine.editor.debug.debug_panels_state
from engine.editor.debug.debug_panels_state import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.debug.debug_panels_state")
