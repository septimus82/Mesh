# mypy: disable-error-code=no-any-return

from __future__ import annotations

import time
from typing import Any, Callable

from engine.logging_tools import get_logger
from engine.swallowed_exceptions import format_swallowed_summary, read_counts
from engine.swallowed_exceptions import reset as reset_swallowed_exceptions

_EDITOR_LOGGER = get_logger("engine.editor_controller")
_SWALLOWED_OVERLAY_REFRESH_SECONDS = 0.5


def confirm_open_get(self: Any) -> bool:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return False
    return confirm.is_open


def confirm_open_set(self: Any, value: bool) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm.set_open(bool(value))


def confirm_reason_get(self: Any) -> str:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return ""
    return confirm.reason


def confirm_reason_set(self: Any, value: str) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm.reason = str(value or "")


def confirm_selection_index_get(self: Any) -> int:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return 0
    return confirm.selection_index


def confirm_selection_index_set(self: Any, value: int) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm.selection_index = int(value)


def pending_action_get(self: Any) -> Callable[[], None] | None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return None
    return confirm.pending_action


def pending_action_set(self: Any, value: Callable[[], None] | None) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm.pending_action = value


def toggle(self: Any) -> None:
    if self.play_session.is_playing:
        self.stop_playing()
        return
    if self.active:
        if self.confirm_unsaved_changes("Exit Editor Mode", self._disable_editor_mode):
            return
        self._disable_editor_mode()
        return
    self._enable_editor_mode()


def _enable_editor_mode(self: Any) -> None:
    self.active = True
    _EDITOR_LOGGER.info("[Editor] Mode ENABLED")
    self.window.paused = True
    self.inspector.set_inspector_active(False)
    self.palette_active = False
    self.palette_filter_active = False


def _disable_editor_mode(self: Any) -> None:
    self._flush_workspace_autosave()
    self.active = False
    _EDITOR_LOGGER.info("[Editor] Mode DISABLED")
    self.selected_entity = None
    self.shape.reset_zone_selection_state()
    self.window.paused = False
    self.inspector.set_inspector_active(False)
    self.palette_active = False
    self.palette_filter_active = False
    self.panels.close_command_palette()
    self.search.clear_command_palette_state()
    self.scene_browser_active = False
    self.scene_browser_query = ""
    self.scene_browser_index = 0
    self._cancel_hierarchy_rename()
    self._close_dialogue_panel()
    self._close_animation_panel()
    self._close_tile_panel()
    self.scene_switcher_active = False
    self.scene_switcher_query = ""
    self.scene_switcher_index = 0
    self._toggle_lights_mode(False)
    self._toggle_occluder_mode(False)
    self.shape.cancel_shape_edit()


def draw_overlay(self: Any) -> None:
    self.overlay.draw_overlay()


def set_status(self: Any, message: str, *, seconds: float = 1.5) -> None:
    self._status_message = str(message)
    self._status_until = float(time.time()) + float(seconds)


def _update_status(self: Any) -> None:
    if not self._status_message:
        return
    if float(time.time()) >= float(self._status_until):
        self._status_message = None
        self._status_until = 0.0


def confirm_unsaved_changes(
    self: Any,
    reason: str,
    action: Callable[[], None],
    *,
    labels: tuple[str, str, str] | None = None,
    choice_actions: tuple[Callable[[], None] | None, Callable[[], None] | None, Callable[[], None] | None] | None = None,
) -> bool:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return False
    return confirm.confirm_unsaved_changes(
        reason,
        action,
        labels=labels,
        choice_actions=choice_actions,
    )


def _close_unsaved_confirm(self: Any, *, clear_pending: bool = False) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm.close(clear_pending=clear_pending)


def _run_pending_confirm_action(self: Any) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm._run_pending_confirm_action()


def _apply_unsaved_confirm_choice(self: Any, choice_index: int) -> None:
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return
    confirm.apply_choice(choice_index)


def toggle_hierarchy(self: Any) -> None:
    self.hierarchy.toggle_hierarchy()


def toggle_entity_panels(self: Any) -> bool:
    return self.entity_panels_controller.toggle_entity_panels()


def toggle_scene_switcher(self: Any) -> bool:
    return self.scene_browse.toggle_scene_switcher()


def toggle_scene_browser(self: Any) -> bool:
    return self.scene_browse.toggle_scene_browser()


def toggle_command_palette(self: Any) -> bool:
    return self.search.toggle_command_palette()


def toggle_find_everything(self: Any) -> bool:
    return self.search.toggle_find_everything()


def close_find_everything(self: Any) -> None:
    self.search.close_find_everything()


def toggle_asset_browser(self: Any) -> bool:
    return self.asset_browser.toggle_asset_browser()


def toggle_dialogue_panel(self: Any) -> None:
    self.dialogue.toggle_dialogue_panel()


def _close_dialogue_panel(self: Any) -> None:
    self.dialogue.close_dialogue_panel()


def toggle_animation_panel(self: Any) -> None:
    self.animation.toggle_animation_panel()


def _close_animation_panel(self: Any) -> None:
    self.animation.close_animation_panel()


def toggle_tile_panel(self: Any) -> None:
    self.tile.toggle_tile_panel()


def _close_tile_panel(self: Any) -> None:
    self.tile.close_tile_panel()


def toggle_palette(self: Any) -> None:
    self.palette.toggle_palette()


def move_palette_selection(self: Any, delta: int) -> None:
    self.palette.move_palette_selection(delta)


def select_palette_index(self: Any, index: int) -> None:
    self.palette.select_palette_index(index)


def palette_selected_prefab_get(self: Any) -> str | None:
    return self.palette.palette_selected_prefab()


def open_project_explorer_context_menu(self: Any, x: int, y: int) -> None:
    self.project_explorer_actions.open_context_menu(x, y)


def open_project_explorer_context_menu_at_selection(self: Any) -> None:
    self.project_explorer_actions.open_context_menu_at_selection()


def problems_jump_to_selected(self: Any) -> bool:
    return self.problems_actions.jump_to_selected()


def problems_copy_location(self: Any) -> bool:
    return self.problems_actions.copy_location()


def _toast_problems(self: Any, message: str, seconds: float = 2.5) -> None:
    self.problems_actions._toast(message, seconds=seconds)


def _open_problems_preview(self: Any) -> bool:
    return self.problems.open_preview(self)


def _close_problems_preview(self: Any) -> None:
    self.problems.close_preview(self)


def _toggle_problems_preview(self: Any) -> bool:
    return self.problems.toggle_preview(self)


def _problems_toast_no_fix(self: Any) -> None:
    self.problems._toast_no_fix(self)


def _debug_handle_mouse_click(self: Any, x: float, y: float, button: int) -> bool:
    return self.debug_panels.handle_mouse_click(x, y, button)


def _is_debug_mode_enabled(self: Any) -> bool:
    window = getattr(self, "window", None)
    return bool(getattr(window, "show_debug", False))


def toggle_swallowed_exceptions_overlay(self: Any) -> bool:
    if not _is_debug_mode_enabled(self):
        return False
    current = bool(getattr(self, "_show_swallowed_exceptions_overlay", False))
    updated = not current
    self._show_swallowed_exceptions_overlay = updated
    self._swallowed_exceptions_overlay_next_refresh_ts = 0.0
    if updated:
        refresh_swallowed_exceptions_overlay_summary(self, force=True)
    return updated


def refresh_swallowed_exceptions_overlay_summary(self: Any, *, force: bool = False) -> str:
    if not bool(getattr(self, "_show_swallowed_exceptions_overlay", False)):
        return str(getattr(self, "_swallowed_exceptions_overlay_summary", ""))
    now = float(time.time())
    next_refresh_ts = float(getattr(self, "_swallowed_exceptions_overlay_next_refresh_ts", 0.0))
    if not force and now < next_refresh_ts:
        return str(getattr(self, "_swallowed_exceptions_overlay_summary", ""))
    counts = read_counts()
    self._swallowed_exceptions_overlay_distinct_sites = len(counts)
    self._swallowed_exceptions_overlay_total_count = int(sum(counts.values()))
    summary = format_swallowed_summary(limit=20)
    self._swallowed_exceptions_overlay_summary = summary
    self._swallowed_exceptions_overlay_next_refresh_ts = now + _SWALLOWED_OVERLAY_REFRESH_SECONDS
    return summary


def reset_swallowed_exceptions_overlay_counts(self: Any) -> None:
    reset_swallowed_exceptions()
    self._swallowed_exceptions_overlay_summary = "no swallowed exceptions recorded"
    self._swallowed_exceptions_overlay_distinct_sites = 0
    self._swallowed_exceptions_overlay_total_count = 0
    self._swallowed_exceptions_overlay_next_refresh_ts = 0.0


def bind_overlays_modals_methods(controller_cls: Any) -> None:
    controller_cls.confirm_open = property(confirm_open_get, confirm_open_set)
    controller_cls.confirm_reason = property(confirm_reason_get, confirm_reason_set)
    controller_cls.confirm_selection_index = property(
        confirm_selection_index_get,
        confirm_selection_index_set,
    )
    controller_cls.pending_action = property(pending_action_get, pending_action_set)
    controller_cls.palette_selected_prefab = property(palette_selected_prefab_get)

    method_map = {
        "toggle": toggle,
        "_enable_editor_mode": _enable_editor_mode,
        "_disable_editor_mode": _disable_editor_mode,
        "draw_overlay": draw_overlay,
        "set_status": set_status,
        "_update_status": _update_status,
        "confirm_unsaved_changes": confirm_unsaved_changes,
        "_close_unsaved_confirm": _close_unsaved_confirm,
        "_run_pending_confirm_action": _run_pending_confirm_action,
        "_apply_unsaved_confirm_choice": _apply_unsaved_confirm_choice,
        "toggle_hierarchy": toggle_hierarchy,
        "toggle_entity_panels": toggle_entity_panels,
        "toggle_scene_switcher": toggle_scene_switcher,
        "toggle_scene_browser": toggle_scene_browser,
        "toggle_command_palette": toggle_command_palette,
        "toggle_find_everything": toggle_find_everything,
        "close_find_everything": close_find_everything,
        "toggle_asset_browser": toggle_asset_browser,
        "toggle_dialogue_panel": toggle_dialogue_panel,
        "_close_dialogue_panel": _close_dialogue_panel,
        "toggle_animation_panel": toggle_animation_panel,
        "_close_animation_panel": _close_animation_panel,
        "toggle_tile_panel": toggle_tile_panel,
        "_close_tile_panel": _close_tile_panel,
        "toggle_palette": toggle_palette,
        "move_palette_selection": move_palette_selection,
        "select_palette_index": select_palette_index,
        "open_project_explorer_context_menu": open_project_explorer_context_menu,
        "open_project_explorer_context_menu_at_selection": open_project_explorer_context_menu_at_selection,
        "problems_jump_to_selected": problems_jump_to_selected,
        "problems_copy_location": problems_copy_location,
        "_toast_problems": _toast_problems,
        "_open_problems_preview": _open_problems_preview,
        "_close_problems_preview": _close_problems_preview,
        "_toggle_problems_preview": _toggle_problems_preview,
        "_problems_toast_no_fix": _problems_toast_no_fix,
        "_debug_handle_mouse_click": _debug_handle_mouse_click,
        "toggle_swallowed_exceptions_overlay": toggle_swallowed_exceptions_overlay,
        "refresh_swallowed_exceptions_overlay_summary": refresh_swallowed_exceptions_overlay_summary,
        "reset_swallowed_exceptions_overlay_counts": reset_swallowed_exceptions_overlay_counts,
    }
    for name, fn in method_map.items():
        setattr(controller_cls, name, fn)
