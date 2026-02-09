from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import engine.optional_arcade as optional_arcade
from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_PROJECT_EXPLORER,
    SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
)

SCOPE_COMMAND_PALETTE = "command_palette"
SCOPE_KEYBINDS = "keybinds"


@dataclass(frozen=True)
class KeyCombo:
    key: int
    mods: int


@dataclass(frozen=True)
class RouteSpec:
    scope: str
    combo: KeyCombo
    action_id: str
    when: str


def build_route_table() -> tuple[RouteSpec, ...]:
    k = optional_arcade.arcade.key
    mod_ctrl = int(getattr(k, "MOD_CTRL", 0) or 0)
    mod_shift = int(getattr(k, "MOD_SHIFT", 0) or 0)
    mod_alt = int(getattr(k, "MOD_ALT", 0) or 0)

    routes: list[RouteSpec] = []
    seen: dict[tuple[str, int, int], RouteSpec] = {}

    def add(route: RouteSpec) -> None:
        key = (route.scope, route.combo.key, route.combo.mods)
        existing = seen.get(key)
        if existing is not None:
            if existing.action_id == route.action_id:
                return
            raise ValueError(f"Duplicate route for scope/key/mods: {key}")
        seen[key] = route
        routes.append(route)

    # Command palette navigation (command_palette scope)
    add(RouteSpec(SCOPE_COMMAND_PALETTE, KeyCombo(k.ESCAPE, 0), "editor.command_palette.close", "when_command_palette"))
    add(RouteSpec(SCOPE_COMMAND_PALETTE, KeyCombo(k.BACKSPACE, 0), "editor.command_palette.backspace", "when_command_palette"))
    add(RouteSpec(SCOPE_COMMAND_PALETTE, KeyCombo(k.UP, 0), "editor.command_palette.up", "when_command_palette"))
    add(RouteSpec(SCOPE_COMMAND_PALETTE, KeyCombo(k.DOWN, 0), "editor.command_palette.down", "when_command_palette"))
    add(RouteSpec(SCOPE_COMMAND_PALETTE, KeyCombo(k.ENTER, 0), "editor.command_palette.activate", "when_command_palette"))
    add(RouteSpec(SCOPE_COMMAND_PALETTE, KeyCombo(k.RETURN, 0), "editor.command_palette.activate", "when_command_palette"))

    # Project Explorer context menu (scoped)
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
            KeyCombo(k.ESCAPE, 0),
            "editor.project_explorer.context_menu.close",
            "always",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
            KeyCombo(k.UP, 0),
            "editor.project_explorer.context_menu.up",
            "always",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
            KeyCombo(k.DOWN, 0),
            "editor.project_explorer.context_menu.down",
            "always",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
            KeyCombo(k.ENTER, 0),
            "editor.project_explorer.context_menu.activate",
            "always",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
            KeyCombo(k.RETURN, 0),
            "editor.project_explorer.context_menu.activate",
            "always",
        )
    )

    # Project Explorer scoped actions
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.F2, 0),
            "editor.project_explorer.safe_rename_asset",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.DELETE, 0),
            "editor.project_explorer.refactor_delete_selected",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.M, mod_ctrl | mod_shift),
            "editor.project_explorer.refactor_move_selected",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.F10, mod_shift),
            "editor.project_explorer.context_menu.open",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.A, mod_ctrl),
            "editor.project_explorer.select_all",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.I, mod_ctrl),
            "editor.project_explorer.invert_selection",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_PROJECT_EXPLORER,
            KeyCombo(k.ESCAPE, 0),
            "editor.project_explorer.clear_selection",
            "when_not_text_input",
        )
    )

    # Keybinds modal input dispatch
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.ESCAPE, 0), "editor.keybinds.modal.input", "when_keybinds"))
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.UP, 0), "editor.keybinds.modal.input", "when_keybinds"))
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.DOWN, 0), "editor.keybinds.modal.input", "when_keybinds"))
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.ENTER, 0), "editor.keybinds.modal.input", "when_keybinds"))
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.BACKSPACE, 0), "editor.keybinds.modal.input", "when_keybinds"))
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.DELETE, 0), "editor.keybinds.modal.input", "when_keybinds"))
    add(RouteSpec(SCOPE_KEYBINDS, KeyCombo(k.S, mod_ctrl), "editor.keybinds.modal.input", "when_keybinds"))

    # Global editor actions
    add(
        RouteSpec(
            SHORTCUT_SCOPE_GLOBAL,
            KeyCombo(k.P, mod_ctrl),
            "editor.command_palette.toggle",
            "when_command_palette_toggle_allowed",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_GLOBAL,
            KeyCombo(k.Z, mod_ctrl),
            "editor.history.undo",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_GLOBAL,
            KeyCombo(k.Y, mod_ctrl),
            "editor.history.redo",
            "when_not_text_input",
        )
    )
    add(
        RouteSpec(
            SHORTCUT_SCOPE_GLOBAL,
            KeyCombo(k.K, mod_ctrl | mod_alt),
            "editor.keybinds.open",
            "when_not_text_input",
        )
    )

    return tuple(routes)


def _validate_routes(routes: Iterable[RouteSpec]) -> None:
    seen: set[tuple[str, int, int]] = set()
    for route in routes:
        key = (route.scope, route.combo.key, route.combo.mods)
        if key in seen:
            raise ValueError(f"Duplicate route for scope/key/mods: {key}")
        seen.add(key)


def resolve_route(
    active_scopes: Sequence[str],
    combo: KeyCombo,
    routes: Sequence[RouteSpec],
    predicate_results: Mapping[str, bool],
) -> str | None:
    for scope in active_scopes:
        for route in routes:
            if route.scope != scope:
                continue
            if route.combo != combo:
                continue
            if not predicate_results.get(route.when, True):
                continue
            return route.action_id
    return None
