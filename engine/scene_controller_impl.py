"""Compatibility facade for SceneController implementation."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.scene_controller_parts import *  # noqa: F401,F403

# Import parts to keep the extracted module tree initialized.
import_module("engine.scene_controller_parts")
_impl = import_module("engine.scene_controller_core")
sys.modules[__name__] = _impl
