"""Registry: EditorAction dataclass, builder, resolver, and public API entry-points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, cast

from engine.editor.editor_actions_registry import ActionDef, DEFAULT_ACTION_DEFS

from engine.editor.editor_actions_parts._shared import SHORTCUT_SCOPE_GLOBAL

__all__ = [
    "EditorAction",
    "_resolve_action_callable",
    "_build_actions_from_defs",
    "get_editor_actions",
    "get_palette_actions",
    "get_menu_actions",
    "find_action",
    "run_editor_action",
]


@dataclass(frozen=True, slots=True)
class EditorAction:
    id: str
    title: str
    keywords: tuple[str, ...]
    group: str | None
    shortcut: str
    enabled: Callable[[Any, Any], bool]
    run: Callable[[Any], None]
    in_palette: bool = True
    in_menu: bool = True
    menu_label: str | None = None
    shortcut_scope: str = SHORTCUT_SCOPE_GLOBAL


def _resolve_action_callable(
    name: str, namespace: dict[str, Any] | None = None
) -> Callable[..., Any]:
    """Resolve an action callable by name from *namespace*.

    The caller (the shim module ``editor_actions_impl``) passes its own
    ``globals()`` so that every re-exported symbol is visible.
    """
    ns = namespace or {}
    fn = ns.get(str(name))
    if not callable(fn):
        raise KeyError(f"Unknown action callable: {name}")
    return cast(Callable[..., Any], fn)


def _build_actions_from_defs(
    defs: Iterable[ActionDef], namespace: dict[str, Any] | None = None
) -> list[EditorAction]:
    actions: list[EditorAction] = []
    for spec in defs:
        enabled_fn = cast(
            Callable[[Any, Any], bool],
            _resolve_action_callable(spec.enabled, namespace),
        )
        run_fn = cast(
            Callable[[Any], None],
            _resolve_action_callable(spec.run, namespace),
        )
        actions.append(
            EditorAction(
                id=spec.id,
                title=spec.title,
                keywords=spec.keywords,
                group=spec.group,
                shortcut=spec.shortcut,
                enabled=enabled_fn,
                run=run_fn,
                in_palette=spec.in_palette,
                in_menu=spec.in_menu,
                menu_label=spec.menu_label,
                shortcut_scope=spec.shortcut_scope,
            )
        )
    return actions


def get_editor_actions(
    controller: Any | None,
    _window: Any | None,
    *,
    namespace: dict[str, Any] | None = None,
) -> list[EditorAction]:
    actions = _build_actions_from_defs(DEFAULT_ACTION_DEFS, namespace)
    overrides = getattr(controller, "_keymap_overrides", None) if controller is not None else None
    if isinstance(overrides, dict) and overrides:
        from engine.editor.keymap_override_model import apply_keymap_overrides  # noqa: PLC0415

        updated, _, _ = apply_keymap_overrides(actions, overrides)
        return [action for action in updated if isinstance(action, EditorAction)]
    return actions


def get_palette_actions(
    controller: Any | None,
    window: Any | None,
    *,
    namespace: dict[str, Any] | None = None,
) -> list[EditorAction]:
    return [action for action in get_editor_actions(controller, window, namespace=namespace) if action.in_palette]


def get_menu_actions(
    controller: Any | None,
    window: Any | None,
    *,
    namespace: dict[str, Any] | None = None,
) -> list[EditorAction]:
    return [action for action in get_editor_actions(controller, window, namespace=namespace) if action.in_menu and action.group]


def find_action(actions: Iterable[EditorAction], action_id: str) -> EditorAction | None:
    wanted = str(action_id or "").strip()
    if not wanted:
        return None
    for action in actions:
        if action.id == wanted:
            return action
    return None


def run_editor_action(
    action_id: str,
    controller: Any,
    window: Any,
    *,
    namespace: dict[str, Any] | None = None,
) -> bool:
    actions = get_editor_actions(controller, window, namespace=namespace)
    action = find_action(actions, action_id)
    if action is None:
        return False
    if not action.enabled(controller, window):
        return False
    action.run(window)
    return True
