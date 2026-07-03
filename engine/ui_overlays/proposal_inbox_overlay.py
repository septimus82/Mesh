"""AI proposal inbox overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import TextCache, draw_text_cached
from .common import UIElement, _draw_tb_rectangle_filled, _draw_tb_rectangle_outline
from .theme import EDITOR_THEME

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


PADDING = 8.0
LINE_H = 18.0
ROW_H = 114.0
BUTTON_W = 58.0
BUTTON_H = 20.0


class ProposalInboxOverlay(UIElement):
    """Editor-only overlay that draws pending staged AI proposals."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=256)
        self._button_rects: dict[tuple[str, str], tuple[float, float, float, float]] = {}

    def draw(self) -> None:
        from ..editor.editor_dock_query import get_effective_dock_widths
        from ..editor.editor_shell_layout import TAB_HEADER_HEIGHT, compute_editor_shell_layout

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        dock_ctl = getattr(controller, "dock", None)
        snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        if right_tab != "AI Proposals":
            self._button_rects.clear()
            return

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock

        _draw_tb_rectangle_filled(dock.left, dock.right, dock.top, dock.bottom, EDITOR_THEME.panel_strong_bg)
        _draw_tb_rectangle_outline(
            dock.left,
            dock.right,
            dock.top,
            dock.bottom,
            EDITOR_THEME.panel_strong_border,
            1,
        )

        inbox = getattr(controller, "proposal_inbox", None)
        list_pending = getattr(inbox, "list_pending", None)
        proposals = list_pending() if callable(list_pending) else []
        proposals = proposals if isinstance(proposals, list) else []

        content_top = dock.top - TAB_HEADER_HEIGHT - PADDING
        draw_text_cached(
            f"AI Proposals ({len(proposals)})",
            dock.left + PADDING,
            content_top - LINE_H + 2,
            color=EDITOR_THEME.header_muted,
            font_size=11,
            cache=self._text_cache,
        )
        y = content_top - (LINE_H * 2)
        self._button_rects.clear()

        if not proposals:
            draw_text_cached(
                "No pending AI proposals",
                dock.left + PADDING,
                y,
                color=EDITOR_THEME.text_dim,
                font_size=11,
                cache=self._text_cache,
            )
            return

        for proposal in proposals:
            if y - ROW_H < dock.bottom + PADDING:
                draw_text_cached(
                    "...",
                    dock.left + PADDING,
                    max(dock.bottom + PADDING, y),
                    color=EDITOR_THEME.text_dim,
                    font_size=11,
                    cache=self._text_cache,
                )
                break
            proposal_id = str(proposal.get("proposal_id") or "")
            dry_run = proposal.get("dry_run") if isinstance(proposal.get("dry_run"), dict) else {}
            warnings = dry_run.get("warnings") if isinstance(dry_run, dict) else []
            warning_count = len(warnings) if isinstance(warnings, list) else 0
            affected_ids = proposal.get("affected_ids") if isinstance(proposal.get("affected_ids"), list) else []
            preview = str(proposal.get("preview_summary") or "AI proposal")

            _draw_tb_rectangle_filled(
                dock.left + PADDING,
                dock.right - PADDING,
                y + 4,
                y - ROW_H + 4,
                EDITOR_THEME.panel_bg,
            )
            _draw_tb_rectangle_outline(
                dock.left + PADDING,
                dock.right - PADDING,
                y + 4,
                y - ROW_H + 4,
                EDITOR_THEME.panel_border,
                1,
            )
            text_left = dock.left + PADDING + 8
            text_right = dock.right - PADDING - 8
            draw_text_cached(
                _truncate(preview, _char_capacity(text_right - text_left, 11)),
                text_left,
                y - LINE_H + 4,
                color=EDITOR_THEME.text_primary if dry_run.get("ok") is True else EDITOR_THEME.warning_text,
                font_size=11,
                cache=self._text_cache,
            )
            if proposal_id:
                draw_text_cached(
                    _truncate(f"ID: {proposal_id}", _char_capacity(text_right - text_left, 10)),
                    text_left,
                    y - (LINE_H * 2) + 4,
                    color=EDITOR_THEME.text_dim,
                    font_size=10,
                    cache=self._text_cache,
                )
            meta = f"Affected: {len(affected_ids)}"
            if affected_ids:
                meta = f"{meta}  {', '.join(str(item) for item in affected_ids[:3])}"
            draw_text_cached(
                _truncate(meta, _char_capacity(text_right - text_left, 10)),
                text_left,
                y - (LINE_H * 3) + 4,
                color=EDITOR_THEME.text_dim,
                font_size=10,
                cache=self._text_cache,
            )
            status = "Dry run OK" if dry_run.get("ok") is True else f"Warnings: {warning_count}"
            draw_text_cached(
                status,
                text_left,
                y - (LINE_H * 4) + 4,
                color=EDITOR_THEME.action_text if dry_run.get("ok") is True else EDITOR_THEME.warning_text,
                font_size=10,
                cache=self._text_cache,
            )

            # Keep buttons anchored below the four text lines (preview, id, meta, status).
            button_y = y - (LINE_H * 4) - BUTTON_H - 6
            reject_rect = (dock.right - PADDING - BUTTON_W, button_y, BUTTON_W, BUTTON_H)
            accept_rect = (reject_rect[0] - BUTTON_W - 8, button_y, BUTTON_W, BUTTON_H)
            # Accept is only clickable after a successful dry-run. Failed proposals stay
            # visible for review, but accept remains fail-closed in ProposalInbox too.
            accept_enabled = dry_run.get("ok") is True
            self._draw_button(
                accept_rect,
                "Accept",
                EDITOR_THEME.action_text if accept_enabled else EDITOR_THEME.text_dim,
            )
            self._draw_button(reject_rect, "Reject", EDITOR_THEME.text_dim)
            if accept_enabled:
                self._button_rects[(proposal_id, "accept")] = accept_rect
            self._button_rects[(proposal_id, "reject")] = reject_rect

            y -= ROW_H + 8

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return False
        controller = getattr(self.window, "editor_controller", None)
        inbox = getattr(controller, "proposal_inbox", None) if controller is not None else None
        if inbox is None:
            return False
        for (proposal_id, action), rect in list(self._button_rects.items()):
            if _contains(rect, float(x), float(y)):
                handler = getattr(inbox, action, None)
                if callable(handler):
                    handler(proposal_id)
                return True
        return False

    def _draw_button(self, rect: tuple[float, float, float, float], label: str, color: Any) -> None:
        left, bottom, width, height = rect
        _draw_tb_rectangle_filled(left, left + width, bottom + height, bottom, EDITOR_THEME.input_bg)
        _draw_tb_rectangle_outline(left, left + width, bottom + height, bottom, EDITOR_THEME.input_border, 1)
        draw_text_cached(
            label,
            left + (width / 2),
            bottom + (height / 2),
            color=color,
            font_size=10,
            anchor_x="center",
            anchor_y="center",
            cache=self._text_cache,
        )


def _contains(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height


def _char_capacity(width: float, font_size: int) -> int:
    return max(1, int(max(0.0, width) / max(1.0, float(font_size) * 0.6)))


def _truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."
