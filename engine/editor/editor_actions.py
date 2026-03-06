"""Thin compatibility facade for editor actions.

Runtime implementation lives in :mod:`engine.editor.editor_actions_impl`.
This module intentionally preserves the public import surface.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, cast

_impl = import_module("engine.editor.editor_actions_impl")


def get_editor_actions(controller: Any, window: Any) -> list[Any]:
    return cast(list[Any], _impl.get_editor_actions(controller, window))


def run_editor_action(action_id: str, controller: Any, window: Any) -> bool:
    return cast(bool, _impl.run_editor_action(action_id, controller, window))


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))


__all__ = ["get_editor_actions", "run_editor_action", *list(getattr(_impl, "__all__", []))]
