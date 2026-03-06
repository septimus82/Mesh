"""Compatibility facade for authoring entity operations implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sys
from importlib import import_module

if TYPE_CHECKING:
    from .entity_ops_core import *  # noqa: F401,F403

_impl = import_module("engine.scene_runtime.authoring.entity_ops_core")
sys.modules[__name__] = _impl
