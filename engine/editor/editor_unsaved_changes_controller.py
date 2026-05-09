from __future__ import annotations

from typing import Any, Callable

import engine.optional_arcade as optional_arcade
from engine.i18n import tr
from engine.ui_overlays.common import _draw_rectangle_filled, draw_outline_centered, draw_panel_bg


class EditorUnsavedChangesController:
    """Owns the unsaved-changes confirmation state and rendering."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self.is_open: bool = False
        self.reason: str = ""
        self.selection_index: int = 0
        self.pending_action: Callable[[], None] | None = None
        self.labels: tuple[str, str, str] | None = None
        self.choice_actions: tuple[Callable[[], None] | None, Callable[[], None] | None, Callable[[], None] | None] | None = None
        self._confirm_bypass: bool = False

    def set_open(self, value: bool) -> None:
        self.is_open = bool(value)

    def confirm_unsaved_changes(
        self,
        reason: str,
        action: Callable[[], None],
        *,
        labels: tuple[str, str, str] | None = None,
        choice_actions: tuple[Callable[[], None] | None, Callable[[], None] | None, Callable[[], None] | None] | None = None,
    ) -> bool:
        """Return True if the action is blocked by the confirm dialog."""
        if not getattr(self._editor, "active", False):
            return False
        dirty_state = getattr(self._editor, "dirty_state", None)
        if dirty_state is None or not getattr(dirty_state, "is_dirty", False):
            return False
        if self._confirm_bypass:
            return False
        if self.is_open:
            return True
        self.is_open = True
        self.reason = str(reason or "").strip()
        self.selection_index = 0
        self.pending_action = action
        self.labels = labels
        self.choice_actions = choice_actions
        return True

    def close(self, *, clear_pending: bool = False) -> None:
        self.is_open = False
        self.reason = ""
        self.selection_index = 0
        self.labels = None
        self.choice_actions = None
        if clear_pending:
            self.pending_action = None

    def _run_pending_confirm_action(self) -> None:
        action = self.pending_action
        if action is None:
            return
        self.pending_action = None
        self._confirm_bypass = True
        try:
            action()
        finally:
            self._confirm_bypass = False

    def apply_choice(self, choice_index: int) -> None:
        custom_actions = self.choice_actions
        if custom_actions is not None:
            if 0 <= choice_index < len(custom_actions):
                action = custom_actions[choice_index]
                self.close(clear_pending=action is None)
                if action is not None:
                    action()
                return
            self.close(clear_pending=True)
            return

        if choice_index == 0:
            saver = getattr(self._editor, "save_current_scene", None)
            if callable(saver):
                saver()
            self.close()
            self._run_pending_confirm_action()
            return
        if choice_index == 1:
            marker = getattr(self._editor, "_mark_clean", None)
            if callable(marker):
                marker()
            else:
                setattr(self._editor, "scene_dirty", False)
                dirty_state = getattr(self._editor, "dirty_state", None)
                if dirty_state is not None and hasattr(dirty_state, "is_dirty"):
                    dirty_state.is_dirty = False
            self.close()
            self._run_pending_confirm_action()
            return
        self.close(clear_pending=True)

    def handle_input(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.is_open:
            return False

        if key == optional_arcade.arcade.key.LEFT:
            self.selection_index = max(0, self.selection_index - 1)
            return True
        if key == optional_arcade.arcade.key.RIGHT:
            self.selection_index = min(2, self.selection_index + 1)
            return True
        if key in (
            optional_arcade.arcade.key.ENTER,
            optional_arcade.arcade.key.RETURN,
            optional_arcade.arcade.key.SPACE,
            optional_arcade.arcade.key.A,
        ):
            self.apply_choice(self.selection_index)
            return True
        if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.B):
            self.apply_choice(2)
            return True

        return True

    def draw(self) -> None:
        if not self.is_open:
            return
        window = getattr(self._editor, "window", None)
        if window is None:
            return

        title = tr("UI_UNSAVED_CHANGES")
        reason = self.reason
        labels = list(self.labels or (tr("UI_SAVE"), tr("UI_DISCARD"), tr("UI_CANCEL")))
        rendered: list[str] = []
        for idx, label in enumerate(labels):
            if idx == self.selection_index:
                rendered.append(f"[{label}]")
            else:
                rendered.append(label)
        buttons_line = "   ".join(rendered)

        lines = [title]
        if reason:
            lines.append(reason)
        lines.append("")
        lines.append(buttons_line)

        dim_color = (0, 0, 0, 140)
        _draw_rectangle_filled(
            window.width / 2,
            window.height / 2,
            window.width,
            window.height,
            dim_color,
        )

        width = min(520.0, max(360.0, window.width * 0.6))
        height = 140.0 + (len(lines) - 2) * 18.0
        left = (window.width - width) / 2.0
        right = left + width
        bottom = (window.height - height) / 2.0
        top = bottom + height

        draw_panel_bg(left, right, bottom, top, color=(0, 0, 0, 220))
        draw_outline_centered(
            (left + right) / 2.0,
            (top + bottom) / 2.0,
            width,
            height,
            optional_arcade.arcade.color.SKY_BLUE,
            2,
        )

        start_x = left + 24.0
        start_y = top - 24.0
        for idx, line in enumerate(lines):
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - idx * 18.0,
                optional_arcade.arcade.color.WHITE,
                14,
                anchor_y="top",
                font_name=("Consolas", "Courier New", "Courier"),
            )
