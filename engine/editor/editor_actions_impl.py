"""Unified editor action registry used by menus and find/command palettes.

This module is a thin shim.  Actual implementations live in sub-modules
under :mod:`engine.editor.editor_actions_parts`.  Star-imports pull every
symbol into **this** module's ``globals()`` so that the registry's
``_resolve_action_callable`` look-up continues to work unchanged.
"""

from __future__ import annotations

from typing import Any, Iterable

# Re-export action callables from bucket modules so globals() finds them all.
from engine.editor.editor_actions_parts._shared import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.planes_actions import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.alignment_actions import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.hd2d_actions import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.ui_actions import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.project_explorer_actions import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.debug_actions import *  # noqa: F401, F403
from engine.editor.editor_actions_parts.core_actions import *  # noqa: F401, F403

# Import registry symbols that we do NOT override, for direct re-export.
from engine.editor.editor_actions_parts.registry import EditorAction  # noqa: F401
from engine.editor.editor_actions_parts.registry import find_action  # noqa: F401

# Import the registry module for namespace-injecting wrappers.
from engine.editor.editor_actions_parts import registry as _registry


# --- Thin wrappers that inject this module's globals() into the registry ---

def _resolve_action_callable(name: str) -> Any:
    return _registry._resolve_action_callable(name, namespace=globals())


def _build_actions_from_defs(defs: Iterable[Any]) -> list[Any]:
    return _registry._build_actions_from_defs(defs, namespace=globals())


def get_editor_actions(controller: Any | None, _window: Any | None) -> list[Any]:
    return _registry.get_editor_actions(controller, _window, namespace=globals())


def get_palette_actions(controller: Any | None, window: Any | None) -> list[Any]:
    return _registry.get_palette_actions(controller, window, namespace=globals())


def get_menu_actions(controller: Any | None, window: Any | None) -> list[Any]:
    return _registry.get_menu_actions(controller, window, namespace=globals())


def run_editor_action(action_id: str, controller: Any, window: Any) -> bool:
    return _registry.run_editor_action(action_id, controller, window, namespace=globals())
