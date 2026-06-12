"""Pure focus model for capture runtime key routing.

This module defines a read-only snapshot of the application's focus state
and computes the active scopes for key routing. The scope priority order
determines which modal/panel gets first crack at handling key presses.

Scope priority (highest to lowest):
1. confirm_modal - Confirmation dialogs block everything
2. context_menu - Context menus block most input
3. keybinds - Keybind editor blocks input while recording
4. inline_rename - Text input during rename
5. command_palette - Command palette prompt
6. project_explorer - Project explorer panel
7. problems - Problems panel navigation
8. palette_mode - Tile/Entity palette
9. capture_mode - Capture/stamp mode
10. tile_paint - Tile painting
11. entity_paint - Entity painting
12. entity_select - Entity selection/movement
13. global - Default scope
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaptureFocusSnapshot:
    """Immutable snapshot of the application's focus state.
    
    This captures all the boolean conditions that handle_key_press
    branches on, allowing pure scope resolution without side effects.
    """
    # Modal states (highest priority)
    is_confirm_modal_open: bool
    is_context_menu_open: bool
    is_keybinds_recording: bool
    is_keybinds_open: bool
    is_inline_rename_active: bool

    # Overlay/panel states
    is_command_palette_open: bool
    is_command_palette_prompt_active: bool
    is_console_active: bool
    is_project_explorer_focused: bool
    is_problems_focused: bool

    # Authoring mode states
    is_palette_mode_enabled: bool
    is_capture_mode_enabled: bool
    is_tile_paint_enabled: bool
    is_entity_paint_enabled: bool
    is_entity_select_active: bool
    is_authoring_selected: bool  # F12 selection active

    # Global states
    show_debug: bool
    editor_active: bool
    ui_blocked: bool
    scene_persist_armed: bool

    # Modifier keys
    ctrl: bool
    alt: bool
    shift: bool


# Scope names as constants for consistency
SCOPE_CONFIRM_MODAL = "confirm_modal"
SCOPE_CONTEXT_MENU = "context_menu"
SCOPE_KEYBINDS = "keybinds"
SCOPE_INLINE_RENAME = "inline_rename"
SCOPE_COMMAND_PALETTE = "command_palette"
SCOPE_PROJECT_EXPLORER = "project_explorer"
SCOPE_PROBLEMS = "problems"
SCOPE_PALETTE_MODE = "palette_mode"
SCOPE_CAPTURE_MODE = "capture_mode"
SCOPE_TILE_PAINT = "tile_paint"
SCOPE_ENTITY_PAINT = "entity_paint"
SCOPE_ENTITY_SELECT = "entity_select"
SCOPE_AUTHORING_SELECTED = "authoring_selected"
SCOPE_CONSOLE = "console"
SCOPE_GLOBAL = "global"


# Scope priority order (first in list = highest priority)
SCOPE_PRIORITY: tuple[str, ...] = (
    SCOPE_CONFIRM_MODAL,
    SCOPE_CONTEXT_MENU,
    SCOPE_KEYBINDS,
    SCOPE_INLINE_RENAME,
    SCOPE_COMMAND_PALETTE,
    SCOPE_CONSOLE,
    SCOPE_PROJECT_EXPLORER,
    SCOPE_PROBLEMS,
    SCOPE_PALETTE_MODE,
    SCOPE_CAPTURE_MODE,
    SCOPE_TILE_PAINT,
    SCOPE_ENTITY_PAINT,
    SCOPE_ENTITY_SELECT,
    SCOPE_AUTHORING_SELECTED,
    SCOPE_GLOBAL,
)


def compute_active_scopes(snapshot: CaptureFocusSnapshot) -> list[str]:
    """Compute the ordered list of active scopes from a focus snapshot.
    
    Returns scopes in priority order (highest priority first).
    The 'global' scope is always included at the end.
    
    Args:
        snapshot: The current focus state snapshot.
        
    Returns:
        List of active scope names in priority order.
    """
    scopes: list[str] = []

    # Modal scopes (highest priority, mutually exclusive in practice)
    if snapshot.is_confirm_modal_open:
        scopes.append(SCOPE_CONFIRM_MODAL)

    if snapshot.is_context_menu_open:
        scopes.append(SCOPE_CONTEXT_MENU)

    if snapshot.is_keybinds_recording or snapshot.is_keybinds_open:
        scopes.append(SCOPE_KEYBINDS)

    if snapshot.is_inline_rename_active:
        scopes.append(SCOPE_INLINE_RENAME)

    # Overlay scopes
    if snapshot.is_command_palette_open and snapshot.show_debug:
        scopes.append(SCOPE_COMMAND_PALETTE)

    if snapshot.is_console_active:
        scopes.append(SCOPE_CONSOLE)

    # Panel scopes (when editor is active)
    if snapshot.editor_active:
        if snapshot.is_project_explorer_focused:
            scopes.append(SCOPE_PROJECT_EXPLORER)
        if snapshot.is_problems_focused:
            scopes.append(SCOPE_PROBLEMS)

    # Authoring mode scopes (debug only)
    if snapshot.show_debug:
        if snapshot.is_palette_mode_enabled:
            scopes.append(SCOPE_PALETTE_MODE)
        if snapshot.is_capture_mode_enabled:
            scopes.append(SCOPE_CAPTURE_MODE)
        if snapshot.is_tile_paint_enabled:
            scopes.append(SCOPE_TILE_PAINT)
        if snapshot.is_entity_paint_enabled:
            scopes.append(SCOPE_ENTITY_PAINT)
        if snapshot.is_entity_select_active:
            scopes.append(SCOPE_ENTITY_SELECT)
        if snapshot.is_authoring_selected:
            scopes.append(SCOPE_AUTHORING_SELECTED)

    # Global scope is always active (lowest priority)
    if SCOPE_GLOBAL not in scopes:
        scopes.append(SCOPE_GLOBAL)

    return scopes
