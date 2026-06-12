# Backward-compat shim -- canonical module is engine.editor.debug.debug_bundle
import importlib as _importlib
import sys as _sys

from engine.editor.debug.debug_bundle import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.editor.debug.debug_bundle")
