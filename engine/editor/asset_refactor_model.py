# Backward-compat shim -- canonical module is engine.editor.asset_ops.asset_refactor_model
from engine.editor.asset_ops.asset_refactor_model import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.asset_ops.asset_refactor_model")
