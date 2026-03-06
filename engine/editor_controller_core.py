"""Compatibility facade for editor controller implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sys
from importlib import import_module

if TYPE_CHECKING:
    from engine.editor_controller import *  # noqa: F401,F403

_impl = import_module("engine.editor_controller")
sys.modules[__name__] = _impl
