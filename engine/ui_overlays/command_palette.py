"""Command palette UI overlay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_tb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


def format_command_palette_overlay_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}
    if not bool(payload.get("enabled", False)):
        return []

    query = str(payload.get("query") or "")
    dirty = bool(payload.get("dirty", False))
    rev = payload.get("rev")
    rev_text = str(int(rev)) if isinstance(rev, int) else "-"
    armed = bool(payload.get("armed", False))
    undo = payload.get("undo")
    redo = payload.get("redo")
    undo_text = str(int(undo)) if isinstance(undo, int) else "0"
    redo_text = str(int(redo)) if isinstance(redo, int) else "0"
    active_mode = str(payload.get("active_mode") or "none")

    header = (
        f"COMMAND PALETTE: {query} "
        f"[{'DIRTY' if dirty else 'CLEAN'} rev={rev_text}] "
        f"[{'ARMED' if armed else 'SAFE'}] "
        f"[undo={undo_text} redo={redo_text}] "
        f"[ACTIVE_MODE={active_mode}]"
    )

    prompt_active = bool(payload.get("prompt_active", False))
    prompt_text = str(payload.get("prompt_text") or "")
    prompt_kind = str(payload.get("prompt_kind") or "text")
    prompt_query = str(payload.get("prompt_query") or "")
    prompt_placeholder = str(payload.get("prompt_placeholder") or "")
    prompt_title = str(payload.get("prompt_title") or "")
    prompt_preview = str(payload.get("prompt_preview") or "").strip()
    prompt_error = str(payload.get("prompt_error") or "").strip()
    prompt_rows_value = payload.get("prompt_rows")
    prompt_rows = prompt_rows_value if isinstance(prompt_rows_value, list) else []
    selected_p = payload.get("prompt_selected_row")
    selected_prompt_row = int(selected_p) if isinstance(selected_p, int) else 0

    rows_value = payload.get("rows")
    rows = rows_value if isinstance(rows_value, list) else []
    selected = payload.get("selected_row")
    selected_row = int(selected) if isinstance(selected, int) else 0
    help_enabled = bool(payload.get("help_enabled", False))
    help_rows_value = payload.get("help_rows")
    help_rows = help_rows_value if isinstance(help_rows_value, list) else []

    lines: list[str] = [header]

    if help_enabled:
        lines.append("HELP VIEW (F1 to close)")
        if not help_rows:
            lines.append("(no help available)")
            return lines
        for row in help_rows:
            text = str(row or "").strip()
            if text:
                lines.append(text)
        return lines

    if prompt_active:
        lines.append(f"PROMPT: {prompt_title or '-'}")
        if str(prompt_kind).strip().lower() == "pick":
            lines.append(f"query: {prompt_query}")
            if prompt_placeholder:
                lines.append(f"placeholder: {prompt_placeholder}")
            prompt_rows_value = payload.get("prompt_rows")
            prompt_rows = prompt_rows_value if isinstance(prompt_rows_value, list) else []
            selected_p = payload.get("prompt_selected_row")
            selected_prompt_row = int(selected_p) if isinstance(selected_p, int) else 0
            if not prompt_rows:
                lines.append("(no matches)")
            else:
                for i, row in enumerate(prompt_rows):
                    if not isinstance(row, dict):
                        continue
                    label = str(row.get("label") or row.get("value") or "").strip() or "-"
                    prefix = ">" if i == selected_prompt_row else " "
                    lines.append(f"{prefix} {label}")
            lines.append("hint: Up/Down=select Enter=run Esc=cancel")
        else:
            lines.append(f"value: {prompt_text}")
            if prompt_placeholder:
                lines.append(f"placeholder: {prompt_placeholder}")
            lines.append("hint: Enter=run Esc=cancel")
            if prompt_error:
                lines.append(f"arg error: {prompt_error}")
            elif prompt_preview:
                lines.append(f"arg preview: {prompt_preview}")
            if prompt_rows:
                lines.append("Suggestions:")
                for i, row in enumerate(prompt_rows):
                    if not isinstance(row, dict):
                        continue
                    label = str(row.get("label") or row.get("value") or "").strip() or "-"
                    prefix = ">" if i == selected_prompt_row else " "
                    lines.append(f"{prefix} {label}")
        return lines

    preview_line = str(payload.get("preview_line") or "").strip()
    if preview_line:
        lines.append(preview_line)
    preview_line2 = str(payload.get("preview_line2") or "").strip()
    if preview_line2:
        lines.append(preview_line2)

    row_width = 84
    cmd_index = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "")
        if kind == "section":
            title = str(row.get("title") or "").strip() or "-"
            lines.append(f"-- {title} --")
            continue
        if kind != "command":
            continue
        title = str(row.get("title") or "").strip() or "-"
        enabled = bool(row.get("enabled", True))
        disabled_reason = str(row.get("disabled_reason") or "").strip()
        hotkey = str(row.get("hotkey_hint") or "").strip()

        left = title
        if not enabled:
            reason = disabled_reason or "disabled"
            left = f"{left} [disabled: {reason}]"

        prefix = ">" if cmd_index == selected_row else " "
        cmd_index += 1

        right = hotkey
        if right:
            reserve = len(right) + 1
            available = max(0, row_width - 2 - reserve)
            left_text = left[:available].ljust(available)
            lines.append(f"{prefix} {left_text} {right}")
        else:
            lines.append(f"{prefix} {left}")

    return lines


class CommandPaletteOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider
        self._text_cache = TextCache()

    def get_lines(self) -> list[str]:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: command palette overlay should keep rendering even if an optional provider callback fails
                payload = None
        return format_command_palette_overlay_lines(payload if isinstance(payload, dict) else None)

    def draw(self) -> None:
        lines = self.get_lines()
        if not lines:
            return

        width = 640.0
        height = max(160.0, 30.0 + 16.0 * float(len(lines)))
        left = 20.0
        bottom = 160.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 200),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        draw_text_cached(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )
