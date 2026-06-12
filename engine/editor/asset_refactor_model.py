# Backward-compat shim -- canonical module is engine.editor.asset_ops.asset_refactor_model
import importlib as _importlib
import sys as _sys

from engine.editor.asset_ops.asset_refactor_model import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.editor.asset_ops.asset_refactor_model")
