"""Runtime party menu built on the shared menu toolkit."""

from __future__ import annotations

from typing import Any

from engine.ui.menu_toolkit import MenuStackOverlay, SelectableItem, SelectableListScreen

from .collection import MONSTER_INSTANCES_KEY, MONSTER_PARTY_KEY, ensure_monster_collection


class MonsterPartyScreen(SelectableListScreen):
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values
        super().__init__(
            title="Monster Party",
            items=_party_items(values),
            empty_detail="No caught monsters yet.",
        )


def open_monster_party_view(window: Any) -> MenuStackOverlay:
    """Open the player's party view through the runtime UI stack."""

    overlay = getattr(window, "monster_menu_stack", None)
    if not isinstance(overlay, MenuStackOverlay):
        overlay = MenuStackOverlay(window)
        setattr(window, "monster_menu_stack", overlay)
        ui_controller = getattr(window, "ui_controller", None)
        register = getattr(ui_controller, "register_ui_element", None)
        if callable(register):
            register(overlay)
    overlay.push(MonsterPartyScreen(_state_values(window)))
    return overlay


def _state_values(window: Any) -> dict[str, Any]:
    controller = getattr(window, "game_state_controller", None)
    state = getattr(controller, "state", None)
    values = getattr(state, "values", None)
    if not isinstance(values, dict):
        values = {}
        if state is not None:
            state.values = values
            state.variables = values
    ensure_monster_collection(values)
    return values


def _party_items(values: dict[str, Any]) -> list[SelectableItem]:
    ensure_monster_collection(values)
    party = values[MONSTER_PARTY_KEY]
    instances = values[MONSTER_INSTANCES_KEY]
    items: list[SelectableItem] = []
    for instance_id in party:
        row = instances.get(str(instance_id))
        if not isinstance(row, dict):
            continue
        species_id = str(row.get("species_id", "unknown"))
        level = int(row.get("level", 1) or 1)
        hp = int(row.get("current_hp", 0) or 0)
        xp = int(row.get("xp", row.get("experience", 0)) or 0)
        label = f"{species_id}  Lv.{level}"
        items.append(
            SelectableItem(
                id=str(instance_id),
                label=label,
                detail_lines=(
                    f"Species: {species_id}",
                    f"Level: {level}",
                    f"HP: {hp}",
                    f"XP: {xp}",
                ),
            )
        )
    return items
