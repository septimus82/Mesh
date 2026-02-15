# Backward-compat shim -- canonical module is engine.editor.project_explorer.project_explorer_power_tools_model
from engine.editor.project_explorer.project_explorer_power_tools_model import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.project_explorer.project_explorer_power_tools_model")
