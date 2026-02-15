# Backward-compat shim -- canonical module is engine.editor.project_explorer.editor_project_explorer_actions_controller
from engine.editor.project_explorer.editor_project_explorer_actions_controller import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.project_explorer.editor_project_explorer_actions_controller")
