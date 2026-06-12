# Backward-compat shim -- canonical module is engine.editor.project_explorer.editor_project_explorer_controller
import importlib as _importlib
import sys as _sys

from engine.editor.project_explorer.editor_project_explorer_controller import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.editor.project_explorer.editor_project_explorer_controller")
