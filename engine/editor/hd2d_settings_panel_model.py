# Backward-compat shim -- canonical module is engine.editor.hd2d.hd2d_settings_panel_model
from engine.editor.hd2d.hd2d_settings_panel_model import *  # noqa: F401,F403

import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("engine.editor.hd2d.hd2d_settings_panel_model")
