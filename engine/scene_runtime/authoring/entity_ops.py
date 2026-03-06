"""Compatibility facade for authoring entity operations implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sys
from importlib import import_module

if TYPE_CHECKING:
    from .entity_ops_core import *  # noqa: F401,F403
    from .entity_ops_core import (
        _debug_config_entity_has_behaviour as _debug_config_entity_has_behaviour,
    )
    from .entity_ops_core import _debug_config_mutate_for_behaviour as _debug_config_mutate_for_behaviour
    from .entity_ops_core import (
        _debug_config_set_field_for_behaviour as _debug_config_set_field_for_behaviour,
    )
    from .entity_ops_core import _debug_iter_authoring_payloads as _debug_iter_authoring_payloads
    from .entity_ops_core import _debug_remove_sprite as _debug_remove_sprite

_impl = import_module("engine.scene_runtime.authoring.entity_ops_impl")
sys.modules[__name__] = _impl
