from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DatabaseFormRoute:
    controller_attr: str
    tab_name: str
    text_handler: str
    key_handler: str
    click_handler: str


DATABASE_FORM_ROUTES: tuple[DatabaseFormRoute, ...] = (
    DatabaseFormRoute(
        controller_attr="item_editor",
        tab_name="Items",
        text_handler="handle_item_editor_text_input",
        key_handler="handle_item_editor_key",
        click_handler="handle_item_editor_mouse_click",
    ),
    DatabaseFormRoute(
        controller_attr="prefab_editor",
        tab_name="Prefabs",
        text_handler="handle_prefab_editor_text_input",
        key_handler="handle_prefab_editor_key",
        click_handler="handle_prefab_editor_mouse_click",
    ),
    DatabaseFormRoute(controller_attr="quest_editor",
        tab_name="Quests",
        text_handler="handle_quest_editor_text_input",
        key_handler="handle_quest_editor_key",
        click_handler="handle_quest_editor_mouse_click",
    ),
)


def _form_should_route(controller: Any, form: Any, tab_name: str) -> bool:
    is_active = getattr(form, "is_edit_mode_active", lambda: False)
    if not bool(is_active()):
        return False
    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    return (getattr(snapshot, "right_tab", "Inspector") or "Inspector") == tab_name


def active_database_form(controller: Any) -> tuple[DatabaseFormRoute, Any] | None:
    for route in DATABASE_FORM_ROUTES:
        form = getattr(controller, route.controller_attr, None)
        if form is not None and _form_should_route(controller, form, route.tab_name):
            return route, form
    return None


def active_database_form_for_click(controller: Any) -> tuple[DatabaseFormRoute, Any] | None:
    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
    for route in DATABASE_FORM_ROUTES:
        form = getattr(controller, route.controller_attr, None)
        if form is not None and right_tab == route.tab_name:
            return route, form
    return None


def dispatch_database_form_text(controller: Any, text: str) -> bool:
    active = active_database_form(controller)
    if active is None:
        return False
    route, form = active
    handler = getattr(form, route.text_handler, None)
    if callable(handler) and handler(text):
        return True
    return False


def dispatch_database_form_key(controller: Any, key: int, modifiers: int) -> bool:
    active = active_database_form(controller)
    if active is None:
        return False
    route, form = active
    import engine.optional_arcade as optional_arcade  # noqa: PLC0415

    if key == optional_arcade.arcade.key.TAB:
        if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
            cycler = getattr(form, "cycle_focus_backward", None)
        else:
            cycler = getattr(form, "cycle_focus_forward", None)
        if callable(cycler):
            cycler()
        return True
    handler = getattr(form, route.key_handler, None)
    if callable(handler):
        return bool(handler(key, modifiers))
    return True


def dispatch_database_form_click(controller: Any, x: float, y: float) -> bool:
    active = active_database_form_for_click(controller)
    if active is None:
        return False
    route, form = active
    handler = getattr(form, route.click_handler, None)
    if callable(handler):
        return bool(handler(x, y))
    return True
