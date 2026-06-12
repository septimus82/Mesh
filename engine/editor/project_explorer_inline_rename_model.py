# Backward-compat shim -- canonical module is engine.editor.project_explorer.project_explorer_inline_rename_model
import importlib as _importlib
import sys as _sys

from engine.editor.project_explorer.project_explorer_inline_rename_model import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.editor.project_explorer.project_explorer_inline_rename_model")
