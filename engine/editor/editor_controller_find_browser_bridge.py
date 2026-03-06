"""Binder: Find Everything, Search, Find-Actions & Asset Browser delegation shims.

Extracted from ``engine.editor_controller`` to reduce god-class bloat.
Every function takes ``self`` (an ``EditorModeController``) as first arg.
``bind_find_browser_bridge_methods`` monkey-patches them onto the class.
"""
from __future__ import annotations

from typing import Any, Dict, List


# -- Search shims -----------------------------------------------------------

def set_find_query(self, text: str) -> None:
    self.search.set_find_query(text)


def append_find_query_text(self, text: str) -> bool:
    return self.search.append_find_query_text(text)


def backspace_find_query(self) -> bool:
    return self.search.backspace_find_query()


def move_find_selection(self, delta: int) -> None:
    self.search.move_find_selection(delta)


def activate_find_selection(self) -> bool:
    return self.search.activate_find_selection()


def _refresh_find_everything_results(self) -> None:
    """DEPRECATED: delegated to EditorUIFlowController."""
    self.search.refresh_find_everything_results()


def _build_find_everything_items(self) -> list[Any]:
    """DEPRECATED: delegated to EditorUIFlowController."""
    return self.search.build_find_everything_items()


def _get_find_everything_problems(self) -> list[Any]:
    """DEPRECATED: delegated to EditorUIFlowController."""
    return self.search.get_find_everything_problems()


# -- Find-Actions dispatch shims -------------------------------------------

def _activate_find_command(self, command_id: str) -> bool:
    """Activate a command from find-everything or command palette.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.activate_find_command(command_id)


def _activate_find_scene(self, scene_id: str) -> bool:
    """Activate a scene from find-everything.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.activate_find_scene(scene_id)


def _activate_find_entity(self, entity_id: str) -> bool:
    """Activate an entity from find-everything.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.activate_find_entity(entity_id)


def _activate_find_asset(self, asset_path: str) -> bool:
    """Activate an asset from find-everything.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.activate_find_asset(asset_path)


def _spawn_find_asset(self, asset_path: str) -> bool:
    """Spawn an asset from find-everything.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.spawn_find_asset(asset_path)


def _copy_find_asset_path(self, asset_path: str) -> bool:
    """Copy asset path to clipboard from find-everything.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.copy_find_asset_path(asset_path)


def _activate_find_problem(self, issue_id: str) -> bool:
    """Activate a problem from find-everything.

    DELEGATED to EditorFindActionsController.
    """
    return self.find_actions.activate_find_problem(issue_id)


# -- Asset browser shims ---------------------------------------------------

def refresh_asset_browser(self) -> None:
    self.asset_browser.refresh_asset_browser()


def set_asset_browser_filter(self, text: str) -> None:
    self.asset_browser.set_asset_browser_filter(text)


def cycle_asset_browser_kind(self) -> None:
    self.asset_browser.cycle_asset_browser_kind()


def _filter_asset_browser(self) -> None:
    self.asset_browser._filter_asset_browser()


def asset_browser_move_selection(self, delta: int) -> None:
    self.asset_browser.asset_browser_move_selection(delta)


def _activate_selected_asset(self) -> None:
    self.asset_browser._activate_selected_asset()


def place_asset_at(self, x: float, y: float) -> None:
    self.asset_browser.place_asset_at(x, y)


# ---------------------------------------------------------------------------
# Binder
# ---------------------------------------------------------------------------

def bind_find_browser_bridge_methods(cls: Any) -> None:
    # Search
    cls.set_find_query = set_find_query
    cls.append_find_query_text = append_find_query_text
    cls.backspace_find_query = backspace_find_query
    cls.move_find_selection = move_find_selection
    cls.activate_find_selection = activate_find_selection
    cls._refresh_find_everything_results = _refresh_find_everything_results
    cls._build_find_everything_items = _build_find_everything_items
    cls._get_find_everything_problems = _get_find_everything_problems
    # Find-actions
    cls._activate_find_command = _activate_find_command
    cls._activate_find_scene = _activate_find_scene
    cls._activate_find_entity = _activate_find_entity
    cls._activate_find_asset = _activate_find_asset
    cls._spawn_find_asset = _spawn_find_asset
    cls._copy_find_asset_path = _copy_find_asset_path
    cls._activate_find_problem = _activate_find_problem
    # Asset browser
    cls.refresh_asset_browser = refresh_asset_browser
    cls.set_asset_browser_filter = set_asset_browser_filter
    cls.cycle_asset_browser_kind = cycle_asset_browser_kind
    cls._filter_asset_browser = _filter_asset_browser
    cls.asset_browser_move_selection = asset_browser_move_selection
    cls._activate_selected_asset = _activate_selected_asset
    cls.place_asset_at = place_asset_at
