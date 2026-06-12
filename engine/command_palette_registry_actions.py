"""Compatibility facade for command palette action registry implementation."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.command_palette_registry_actions_impl import *  # noqa: F401,F403

_impl = import_module("engine.command_palette_registry_actions_impl")
sys.modules[__name__] = _impl
