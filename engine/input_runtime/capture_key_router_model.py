"""Route table model for capture key routing.

This module defines the key binding routes for the capture runtime.
Routes are organized by scope and resolved in priority order.

The route table is deterministic and pure - no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import engine.optional_arcade as optional_arcade
from engine.input_runtime.capture_runtime_focus_model import (
    SCOPE_AUTHORING_SELECTED,
    SCOPE_CAPTURE_MODE,
    SCOPE_COMMAND_PALETTE,
    SCOPE_CONFIRM_MODAL,
    SCOPE_CONSOLE,
    SCOPE_CONTEXT_MENU,
    SCOPE_ENTITY_PAINT,
    SCOPE_ENTITY_SELECT,
    SCOPE_GLOBAL,
    SCOPE_INLINE_RENAME,
    SCOPE_KEYBINDS,
    SCOPE_PALETTE_MODE,
    SCOPE_PRIORITY,
    SCOPE_PROBLEMS,
    SCOPE_PROJECT_EXPLORER,
    SCOPE_TILE_PAINT,
    CaptureFocusSnapshot,
)


@dataclass(frozen=True, slots=True)
class KeyCombo:
    """Immutable key combination (key code + modifier flags)."""
    key: int
    mods: int


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Legacy state snapshot for backward compatibility."""
    show_debug: bool
    command_palette_enabled: bool
    command_palette_prompt_active: bool
    editor_active: bool
    ui_blocked: bool
    ctrl: bool
    alt: bool
    shift: bool


@dataclass(frozen=True, slots=True)
class RouteSpec:
    """Specification for a key route.
    
    Attributes:
        scope: The scope this route is active in.
        combo: The key combination that triggers this route.
        action_id: The action to dispatch when triggered.
        when: Optional predicate for additional filtering.
    """
    scope: str
    combo: KeyCombo
    action_id: str
    when: Callable[[CaptureFocusSnapshot], bool] | None = None


@dataclass(frozen=True, slots=True)
class RouteAlias:
    scope: str
    action_id: str
    mods: int


@dataclass(frozen=True, slots=True)
class RouteDuplicate:
    scope: str
    key: int
    mods: int
    action_id: str


@dataclass(frozen=True, slots=True)
class RouteConflict:
    scope: str
    key: int
    mods: int
    action_ids: tuple[str, ...]
    when_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditResult:
    aliases: tuple[RouteAlias, ...]
    duplicates: tuple[RouteDuplicate, ...]
    conflicts: tuple[RouteConflict, ...]


# ---------------------------------------------------------------------------
# When predicates - used to filter routes based on state
# ---------------------------------------------------------------------------

def _when_always(_snapshot: CaptureFocusSnapshot) -> bool:
    """Always enabled."""
    return True


def _when_not_ctrl(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when CTRL is not held."""
    return not snapshot.ctrl


def _when_ctrl(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when CTRL is held."""
    return snapshot.ctrl


def _when_shift(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when SHIFT is held."""
    return snapshot.shift


def _when_alt(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when ALT is held."""
    return snapshot.alt


def _when_ctrl_shift(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when CTRL+SHIFT is held."""
    return snapshot.ctrl and snapshot.shift


def _when_debug(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on."""
    return snapshot.show_debug


def _when_not_debug(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is off."""
    return not snapshot.show_debug


def _when_editor_active(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when editor is active."""
    return snapshot.editor_active


def _when_not_editor_active(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when editor is not active."""
    return not snapshot.editor_active


def _when_debug_not_ui_blocked(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on and UI is not blocked."""
    return snapshot.show_debug and not snapshot.ui_blocked


def _when_debug_ctrl(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on and CTRL is held."""
    return snapshot.show_debug and snapshot.ctrl


def _when_debug_ctrl_shift(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on and CTRL+SHIFT is held."""
    return snapshot.show_debug and snapshot.ctrl and snapshot.shift


def _when_debug_editor_not_active(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on and editor is not active."""
    return snapshot.show_debug and not snapshot.editor_active


def _when_debug_editor_active(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on and editor is active."""
    return snapshot.show_debug and snapshot.editor_active


def _when_editor_ctrl(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled for editor undo/redo when editor is active and CTRL is held."""
    return snapshot.editor_active and snapshot.ctrl

def _when_debug_undo(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled for undo/redo when debug, not editor, not UI blocked, and CTRL."""
    return (
        snapshot.show_debug
        and not snapshot.editor_active
        and not snapshot.ui_blocked
        and snapshot.ctrl
    )


def _when_persist_armed(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when scene persist is armed."""
    return snapshot.scene_persist_armed


def _when_debug_persist_armed(snapshot: CaptureFocusSnapshot) -> bool:
    """Enabled when debug mode is on and scene persist is armed."""
    return snapshot.show_debug and snapshot.scene_persist_armed


# ---------------------------------------------------------------------------
# Route audit helpers
# ---------------------------------------------------------------------------

_MUTUALLY_EXCLUSIVE_WHEN: set[tuple[str, str]] = {
    ("_when_debug", "_when_not_debug"),
    ("_when_debug_undo", "_when_editor_ctrl"),  # sorted alphabetically
    ("_when_editor_active", "_when_not_editor_active"),
}


def _when_name(when: Callable[[CaptureFocusSnapshot], bool] | None) -> str:
    if when is None:
        return ""
    return when.__name__


def _predicates_mutually_exclusive(
    left: Callable[[CaptureFocusSnapshot], bool] | None,
    right: Callable[[CaptureFocusSnapshot], bool] | None,
) -> bool:
    if left is None or right is None:
        return False
    name_left = left.__name__
    name_right = right.__name__
    if name_left == name_right:
        return False
    pair = tuple(sorted((name_left, name_right)))
    return pair in _MUTUALLY_EXCLUSIVE_WHEN


def _route_identity(route: RouteSpec) -> tuple[str, int, int, str, str]:
    return (
        route.scope,
        int(route.combo.key),
        int(route.combo.mods),
        route.action_id,
        _when_name(route.when),
    )


def _dedupe_routes(routes: Sequence[RouteSpec]) -> list[RouteSpec]:
    seen: set[tuple[str, int, int, str, str]] = set()
    deduped: list[RouteSpec] = []
    for route in routes:
        ident = _route_identity(route)
        if ident in seen:
            continue
        seen.add(ident)
        deduped.append(route)
    return deduped


def audit_routes(routes: Sequence[RouteSpec]) -> AuditResult:
    key = optional_arcade.arcade.key
    by_scope_action_mods: dict[tuple[str, str, int], set[int]] = {}
    by_scope_combo: dict[tuple[str, int, int], list[RouteSpec]] = {}

    for route in routes:
        scope_combo = (route.scope, int(route.combo.key), int(route.combo.mods))
        by_scope_combo.setdefault(scope_combo, []).append(route)
        scope_action_mods = (route.scope, route.action_id, int(route.combo.mods))
        by_scope_action_mods.setdefault(scope_action_mods, set()).add(int(route.combo.key))

    aliases: list[RouteAlias] = []
    for (scope, action_id, mods), keys in by_scope_action_mods.items():
        if key.ENTER in keys and key.RETURN in keys:
            aliases.append(RouteAlias(scope=scope, action_id=action_id, mods=mods))

    duplicates: list[RouteDuplicate] = []
    conflicts: list[RouteConflict] = []
    for (scope, key_code, mods), group in by_scope_combo.items():
        action_ids = {route.action_id for route in group}
        when_names = {_when_name(route.when) for route in group}
        if len(action_ids) == 1:
            if len(group) > 1 and len(when_names) == 1:
                duplicates.append(
                    RouteDuplicate(
                        scope=scope,
                        key=key_code,
                        mods=mods,
                        action_id=next(iter(action_ids)),
                    )
                )
            elif len(group) > 1:
                conflicts.append(
                    RouteConflict(
                        scope=scope,
                        key=key_code,
                        mods=mods,
                        action_ids=tuple(sorted(action_ids)),
                        when_names=tuple(sorted(when_names)),
                    )
                )
            continue

        has_conflict = False
        for idx, left in enumerate(group):
            for right in group[idx + 1 :]:
                if left.action_id == right.action_id:
                    continue
                if not _predicates_mutually_exclusive(left.when, right.when):
                    has_conflict = True
                    break
            if has_conflict:
                break
        if has_conflict:
            conflicts.append(
                RouteConflict(
                    scope=scope,
                    key=key_code,
                    mods=mods,
                    action_ids=tuple(sorted(action_ids)),
                    when_names=tuple(sorted(when_names)),
                )
            )

    aliases.sort(key=lambda item: (item.scope, item.action_id, item.mods))
    duplicates.sort(key=lambda item: (item.scope, item.key, item.mods, item.action_id))
    conflicts.sort(key=lambda item: (item.scope, item.key, item.mods))

    return AuditResult(
        aliases=tuple(aliases),
        duplicates=tuple(duplicates),
        conflicts=tuple(conflicts),
    )


# ---------------------------------------------------------------------------
# Route table builder
# ---------------------------------------------------------------------------

def build_route_table() -> tuple[RouteSpec, ...]:
    """Build the complete route table.
    
    Routes are organized by scope and will be resolved in scope priority order.
    Within a scope, routes are matched by key combo.
    
    Returns:
        Tuple of RouteSpec objects defining all key routes.
    """
    key = optional_arcade.arcade.key
    routes: list[RouteSpec] = []

    # -------------------------------------------------------------------------
    # CONFIRM MODAL scope - highest priority, blocks everything
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.confirm_modal.cancel",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.confirm_modal.confirm",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.confirm_modal.confirm",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.D, mods=0),
            action_id="capture.confirm_modal.deny",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.confirm_modal.scroll_up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.confirm_modal.scroll_down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.PAGEUP, mods=0),
            action_id="capture.confirm_modal.page_up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.PAGEDOWN, mods=0),
            action_id="capture.confirm_modal.page_down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.HOME, mods=0),
            action_id="capture.confirm_modal.scroll_top",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONFIRM_MODAL,
            combo=KeyCombo(key=key.END, mods=0),
            action_id="capture.confirm_modal.scroll_bottom",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # CONTEXT MENU scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_CONTEXT_MENU,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.context_menu.close",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONTEXT_MENU,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.context_menu.up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONTEXT_MENU,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.context_menu.down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONTEXT_MENU,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.context_menu.activate",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CONTEXT_MENU,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.context_menu.activate",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # KEYBINDS scope - keybind editor
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.keybinds.close_or_cancel",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.keybinds.up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.keybinds.down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.keybinds.record_or_apply",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.keybinds.record_or_apply",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.DELETE, mods=0),
            action_id="capture.keybinds.unbind",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_KEYBINDS,
            combo=KeyCombo(key=key.BACKSPACE, mods=0),
            action_id="capture.keybinds.unbind",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # INLINE RENAME scope - text input during rename
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_INLINE_RENAME,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.inline_rename.cancel",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_INLINE_RENAME,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.inline_rename.confirm",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_INLINE_RENAME,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.inline_rename.confirm",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # COMMAND PALETTE scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.command_palette.cancel_or_close",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.command_palette.up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.command_palette.down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.UP, mods=key.MOD_CTRL),
            action_id="capture.command_palette.history_prev",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.DOWN, mods=key.MOD_CTRL),
            action_id="capture.command_palette.history_next",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.F1, mods=0),
            action_id="capture.command_palette.help_toggle",
            when=_when_not_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.command_palette.activate",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.command_palette.activate",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.ENTER, mods=key.MOD_CTRL),
            action_id="capture.command_palette.activate_repeat",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_COMMAND_PALETTE,
            combo=KeyCombo(key=key.RETURN, mods=key.MOD_CTRL),
            action_id="capture.command_palette.activate_repeat",
            when=_when_ctrl,
        ),
    ])

    # -------------------------------------------------------------------------
    # CONSOLE scope
    # -------------------------------------------------------------------------
    # Console handles its own key processing via process_key
    # We just need routes to toggle/close it
    routes.extend([
        RouteSpec(
            scope=SCOPE_CONSOLE,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.console.close",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # PROJECT EXPLORER scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.project_explorer.up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.project_explorer.down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.LEFT, mods=0),
            action_id="capture.project_explorer.collapse",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.RIGHT, mods=0),
            action_id="capture.project_explorer.expand",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.project_explorer.open",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.project_explorer.open",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.F2, mods=0),
            action_id="capture.project_explorer.rename",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.DELETE, mods=0),
            action_id="capture.project_explorer.delete",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.HOME, mods=0),
            action_id="capture.project_explorer.home",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.END, mods=0),
            action_id="capture.project_explorer.end",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.PAGEUP, mods=0),
            action_id="capture.project_explorer.page_up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.PAGEDOWN, mods=0),
            action_id="capture.project_explorer.page_down",
            when=_when_always,
        ),
        # Context menu key
        RouteSpec(
            scope=SCOPE_PROJECT_EXPLORER,
            combo=KeyCombo(key=key.MENU, mods=0),
            action_id="capture.project_explorer.context_menu",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # PROBLEMS scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_PROBLEMS,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.problems.up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROBLEMS,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.problems.down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROBLEMS,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.problems.jump",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROBLEMS,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.problems.jump",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PROBLEMS,
            combo=KeyCombo(key=key.C, mods=key.MOD_CTRL),
            action_id="capture.problems.copy_location",
            when=_when_ctrl,
        ),
    ])

    # -------------------------------------------------------------------------
    # PALETTE MODE scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.TAB, mods=0),
            action_id="capture.palette_mode.toggle_mode",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.palette_mode.up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.palette_mode.down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.P, mods=0),
            action_id="capture.palette_mode.toggle_preview",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.palette_mode.apply",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.palette_mode.apply",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.ENTER, mods=key.MOD_CTRL),
            action_id="capture.palette_mode.apply_last",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.RETURN, mods=key.MOD_CTRL),
            action_id="capture.palette_mode.apply_last",
            when=_when_ctrl,
        ),
        # Block gameplay keys in palette mode
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.E, mods=0),
            action_id="capture.palette_mode.block_gameplay",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_PALETTE_MODE,
            combo=KeyCombo(key=key.SPACE, mods=0),
            action_id="capture.palette_mode.block_gameplay",
            when=_when_always,
        ),
    ])

    # -------------------------------------------------------------------------
    # CAPTURE MODE scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.capture_mode.close",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.F2, mods=0),
            action_id="capture.capture_mode.close",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.F4, mods=0),
            action_id="capture.capture_mode.toggle_persist_armed",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.TAB, mods=0),
            action_id="capture.capture_mode.toggle_stamp_brush",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.LSHIFT, mods=0),
            action_id="capture.capture_mode.toggle_entities",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.RSHIFT, mods=0),
            action_id="capture.capture_mode.toggle_entities",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.capture_mode.capture",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.capture_mode.capture",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.ENTER, mods=key.MOD_SHIFT),
            action_id="capture.capture_mode.validate",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_CAPTURE_MODE,
            combo=KeyCombo(key=key.ENTER, mods=key.MOD_CTRL),
            action_id="capture.capture_mode.validate",
            when=_when_ctrl,
        ),
    ])

    # -------------------------------------------------------------------------
    # TILE PAINT scope
    # -------------------------------------------------------------------------
    # Number keys 1-9 for quick slot selection, Alt+1-9 for assignment
    for i in range(1, 10):
        key_code = getattr(key, f"KEY_{i}", 48 + i)  # KEY_1=49, KEY_2=50, etc.
        routes.append(RouteSpec(
            scope=SCOPE_TILE_PAINT,
            combo=KeyCombo(key=key_code, mods=0),
            action_id=f"capture.tile_paint.slot_select_{i}",
            when=_when_not_ctrl,
        ))
        routes.append(RouteSpec(
            scope=SCOPE_TILE_PAINT,
            combo=KeyCombo(key=key_code, mods=key.MOD_ALT),
            action_id=f"capture.tile_paint.slot_assign_{i}",
            when=_when_alt,
        ))

    # -------------------------------------------------------------------------
    # ENTITY PAINT scope
    # -------------------------------------------------------------------------
    # Number keys 1-9 for quick slot selection, Alt+1-9 for assignment
    for i in range(1, 10):
        key_code = getattr(key, f"KEY_{i}", 48 + i)
        routes.append(RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key_code, mods=0),
            action_id=f"capture.entity_paint.slot_select_{i}",
            when=_when_not_ctrl,
        ))
        routes.append(RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key_code, mods=key.MOD_ALT),
            action_id=f"capture.entity_paint.slot_assign_{i}",
            when=_when_alt,
        ))
    routes.extend([
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.F4, mods=0),
            action_id="capture.entity_paint.toggle_persist_armed",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.ENTER, mods=0),
            action_id="capture.entity_paint.persist",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.RETURN, mods=0),
            action_id="capture.entity_paint.persist",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.ENTER, mods=key.MOD_SHIFT),
            action_id="capture.entity_paint.validate",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.ENTER, mods=key.MOD_CTRL),
            action_id="capture.entity_paint.validate",
            when=_when_ctrl,
        ),
        # Hover nudge - arrow keys to nudge hovered entity
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.entity_paint.hover_nudge_up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.entity_paint.hover_nudge_down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.LEFT, mods=0),
            action_id="capture.entity_paint.hover_nudge_left",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.RIGHT, mods=0),
            action_id="capture.entity_paint.hover_nudge_right",
            when=_when_always,
        ),
        # Hover nudge with Shift - larger step (8px)
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.UP, mods=key.MOD_SHIFT),
            action_id="capture.entity_paint.hover_nudge_up_fast",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.DOWN, mods=key.MOD_SHIFT),
            action_id="capture.entity_paint.hover_nudge_down_fast",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.LEFT, mods=key.MOD_SHIFT),
            action_id="capture.entity_paint.hover_nudge_left_fast",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_PAINT,
            combo=KeyCombo(key=key.RIGHT, mods=key.MOD_SHIFT),
            action_id="capture.entity_paint.hover_nudge_right_fast",
            when=_when_shift,
        ),
    ])

    # -------------------------------------------------------------------------
    # ENTITY SELECT scope
    # -------------------------------------------------------------------------
    routes.extend([
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.DELETE, mods=0),
            action_id="capture.entity_select.delete",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.BACKSPACE, mods=0),
            action_id="capture.entity_select.delete",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.entity_select.nudge_up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.entity_select.nudge_down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.LEFT, mods=0),
            action_id="capture.entity_select.nudge_left",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.RIGHT, mods=0),
            action_id="capture.entity_select.nudge_right",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.UP, mods=key.MOD_SHIFT),
            action_id="capture.entity_select.nudge_up_large",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.DOWN, mods=key.MOD_SHIFT),
            action_id="capture.entity_select.nudge_down_large",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.LEFT, mods=key.MOD_SHIFT),
            action_id="capture.entity_select.nudge_left_large",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.RIGHT, mods=key.MOD_SHIFT),
            action_id="capture.entity_select.nudge_right_large",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.D, mods=key.MOD_CTRL),
            action_id="capture.entity_select.duplicate",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.C, mods=key.MOD_CTRL),
            action_id="capture.entity_select.copy",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.V, mods=key.MOD_CTRL),
            action_id="capture.entity_select.paste",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.E, mods=key.MOD_CTRL),
            action_id="capture.entity_select.rotate",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.H, mods=key.MOD_CTRL),
            action_id="capture.entity_select.flip_x",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_ENTITY_SELECT,
            combo=KeyCombo(key=key.J, mods=key.MOD_CTRL),
            action_id="capture.entity_select.flip_y",
            when=_when_ctrl,
        ),
    ])

    # -------------------------------------------------------------------------
    # AUTHORING SELECTED scope - F12 selection nudge
    # Step sizes: 1px (Shift), 8px (default), 32px (Ctrl)
    # -------------------------------------------------------------------------
    routes.extend([
        # Default nudge (8px step)
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.UP, mods=0),
            action_id="capture.authoring.nudge_up",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.DOWN, mods=0),
            action_id="capture.authoring.nudge_down",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.LEFT, mods=0),
            action_id="capture.authoring.nudge_left",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.RIGHT, mods=0),
            action_id="capture.authoring.nudge_right",
            when=_when_always,
        ),
        # Fine nudge with Shift (1px step)
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.UP, mods=key.MOD_SHIFT),
            action_id="capture.authoring.nudge_up_fine",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.DOWN, mods=key.MOD_SHIFT),
            action_id="capture.authoring.nudge_down_fine",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.LEFT, mods=key.MOD_SHIFT),
            action_id="capture.authoring.nudge_left_fine",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.RIGHT, mods=key.MOD_SHIFT),
            action_id="capture.authoring.nudge_right_fine",
            when=_when_shift,
        ),
        # Large nudge with Ctrl (32px step)
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.UP, mods=key.MOD_CTRL),
            action_id="capture.authoring.nudge_up_large",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.DOWN, mods=key.MOD_CTRL),
            action_id="capture.authoring.nudge_down_large",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.LEFT, mods=key.MOD_CTRL),
            action_id="capture.authoring.nudge_left_large",
            when=_when_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_AUTHORING_SELECTED,
            combo=KeyCombo(key=key.RIGHT, mods=key.MOD_CTRL),
            action_id="capture.authoring.nudge_right_large",
            when=_when_ctrl,
        ),
    ])

    # -------------------------------------------------------------------------
    # GLOBAL scope - lowest priority, always available
    # -------------------------------------------------------------------------
    routes.extend([
        # Editor undo/redo when editor is active (legacy _handle_editor_input)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.Z, mods=key.MOD_CTRL),
            action_id="capture.editor.undo",
            when=_when_editor_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.Y, mods=key.MOD_CTRL),
            action_id="capture.editor.redo",
            when=_when_editor_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.Z, mods=key.MOD_CTRL | key.MOD_SHIFT),
            action_id="capture.editor.redo",
            when=_when_editor_ctrl,
        ),
        # Interact (E) - actual gating handled in router action
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.E, mods=0),
            action_id="capture.interact.primary",
            when=_when_always,
        ),
        # Performance overlay toggle (P without ctrl)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.P, mods=0),
            action_id="capture.perf.toggle",
            when=_when_not_ctrl,
        ),
        # Console toggle
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.GRAVE, mods=0),
            action_id="capture.console.toggle",
            when=_when_not_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.INSERT, mods=0),
            action_id="capture.console.toggle",
            when=_when_not_ctrl,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F1, mods=0),
            action_id="capture.console.toggle",
            when=_when_not_ctrl,
        ),
        # Command palette toggle (Ctrl+F1)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F1, mods=key.MOD_CTRL),
            action_id="capture.command_palette.toggle",
            when=_when_debug,
        ),
        # Debug undo/redo
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.Z, mods=key.MOD_CTRL),
            action_id="capture.debug.undo",
            when=_when_debug_undo,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.Y, mods=key.MOD_CTRL),
            action_id="capture.debug.redo",
            when=_when_debug_undo,
        ),
        # Palette mode toggle (F3)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F3, mods=0),
            action_id="capture.palette.toggle",
            when=_when_editor_active,
        ),
        # Debug toggle
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F3, mods=0),
            action_id="capture.debug.toggle",
            when=_when_not_editor_active,
        ),
        # Capture mode toggle (F2 when debug)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F2, mods=0),
            action_id="capture.capture_mode.toggle",
            when=_when_debug,
        ),
        # Tile paint toggle (F11)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F11, mods=0),
            action_id="capture.tile_paint.toggle",
            when=_when_debug,
        ),
        # Entity paint toggle (HOME)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.HOME, mods=0),
            action_id="capture.entity_paint.toggle",
            when=_when_debug,
        ),
        # Scene reload (Ctrl+R)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.R, mods=key.MOD_CTRL),
            action_id="capture.scene.reload",
            when=_when_debug_not_ui_blocked,
        ),
        # Scene persist toggle (Ctrl+Shift+S)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.S, mods=key.MOD_CTRL | key.MOD_SHIFT),
            action_id="capture.scene.persist_toggle",
            when=_when_debug_not_ui_blocked,
        ),
        # Scene persist (Ctrl+S)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.S, mods=key.MOD_CTRL),
            action_id="capture.scene.persist",
            when=_when_debug_not_ui_blocked,
        ),
        # Save as (Ctrl+Shift+A)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.A, mods=key.MOD_CTRL | key.MOD_SHIFT),
            action_id="capture.scene.save_as",
            when=_when_debug_not_ui_blocked,
        ),
        # F4 - Editor toggle
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F4, mods=0),
            action_id="capture.editor.toggle",
            when=_when_always,
        ),
        # F5 - Quick save
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F5, mods=0),
            action_id="capture.savegame.save",
            when=_when_always,
        ),
        # F6 - Quick load / Play from here
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F6, mods=0),
            action_id="capture.savegame.load_or_play",
            when=_when_always,
        ),
        # Shift+F6 - Profiler overlay
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F6, mods=key.MOD_SHIFT),
            action_id="capture.profiler.toggle",
            when=_when_debug,
        ),
        # F7 - Stop playing / AI debug toggle
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F7, mods=0),
            action_id="capture.debug.ai_toggle_or_stop",
            when=_when_always,
        ),
        # F8 - Encounter debug overlay toggle (falls through if overlay unavailable)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F8, mods=0),
            action_id="capture.overlay.encounter_debug.toggle",
            when=_when_always,
        ),
        # F9 - Copy coords (debug/inspector) or pause (normal path)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F9, mods=0),
            action_id="capture.debug.copy_coords_or_pause",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F9, mods=key.MOD_SHIFT),
            action_id="capture.debug.copy_hover_coords",
            when=_when_shift,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F9, mods=key.MOD_CTRL),
            action_id="capture.debug.copy_hover_coords",
            when=_when_ctrl,
        ),
        # F10 - Scene inspector overlay toggle (falls through if overlay unavailable)
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F10, mods=0),
            action_id="capture.overlay.scene_inspector.toggle",
            when=_when_always,
        ),
        # Gameplay save/load actions that remain reachable even with routed F8/F9/F10 debug keys.
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F5, mods=key.MOD_CTRL),
            action_id="capture.action.save_game",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F6, mods=key.MOD_CTRL),
            action_id="capture.action.quick_load",
            when=_when_always,
        ),
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F7, mods=key.MOD_CTRL),
            action_id="capture.action.quickload_last_save",
            when=_when_always,
        ),
        # F12 - Toggle selection lock
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.F12, mods=0),
            action_id="capture.debug.toggle_selection_lock",
            when=_when_debug,
        ),
        # Escape - Settings overlay toggle
        RouteSpec(
            scope=SCOPE_GLOBAL,
            combo=KeyCombo(key=key.ESCAPE, mods=0),
            action_id="capture.settings.toggle",
            when=_when_always,
        ),
    ])

    return tuple(_dedupe_routes(routes))


def resolve_route(
    active_scopes: list[str],
    combo: KeyCombo,
    routes: Sequence[RouteSpec],
    snapshot: CaptureFocusSnapshot,
) -> str | None:
    """Resolve a key combo to an action ID based on active scopes.
    
    Routes are checked in scope priority order. Within a scope,
    the first matching route (by combo) is returned.
    
    Args:
        active_scopes: List of currently active scopes in priority order.
        combo: The key combination pressed.
        routes: The available routes.
        snapshot: The current focus snapshot for when-predicate evaluation.
        
    Returns:
        The action ID to dispatch, or None if no route matches.
    """
    # Ensure scopes are in priority order
    ordered_scopes = [s for s in SCOPE_PRIORITY if s in active_scopes]

    # Always include global if not present
    if SCOPE_GLOBAL not in ordered_scopes:
        ordered_scopes.append(SCOPE_GLOBAL)

    for scope in ordered_scopes:
        matches = [
            r for r in routes
            if r.scope == scope
            and r.combo.key == combo.key
            and r.combo.mods == combo.mods
            and (r.when is None or r.when(snapshot))
        ]
        if not matches:
            continue
        # Deterministic tie-breaker: sort by action_id
        matches.sort(key=lambda r: r.action_id)
        return matches[0].action_id

    return None


# Re-export KeyCombo and RouteSpec for backward compatibility
__all__ = [
    "KeyCombo",
    "RouteSpec",
    "RouteAlias",
    "RouteDuplicate",
    "RouteConflict",
    "AuditResult",
    "StateSnapshot",
    "CaptureFocusSnapshot",
    "build_route_table",
    "audit_routes",
    "resolve_route",
]
