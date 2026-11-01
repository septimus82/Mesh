# Backward-compat shim -- canonical module is engine.sprite_outline_model (a render model, not editor code)
import importlib as _importlib
import sys as _sys

from engine.sprite_outline_model import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.sprite_outline_model")
