# Backward-compat shim -- canonical module is engine.editor.hd2d.hd2d_override_batch_apply_model
import importlib as _importlib
import sys as _sys

from engine.editor.hd2d.hd2d_override_batch_apply_model import *  # noqa: F401,F403

_sys.modules[__name__] = _importlib.import_module("engine.editor.hd2d.hd2d_override_batch_apply_model")
