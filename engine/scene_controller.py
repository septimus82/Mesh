"""Compatibility facade for SceneController implementation.

Runtime implementation lives in :mod:`engine.scene_controller_impl`.
"""

from __future__ import annotations

import logging
import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.scene_controller_impl import *  # noqa: F401,F403

logger = logging.getLogger(__name__)
_impl = import_module("engine.scene_controller_impl")
sys.modules[__name__] = _impl
