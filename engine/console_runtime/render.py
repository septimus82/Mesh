from __future__ import annotations


def visible_metrics(total_lines: int, visible_line_count: int) -> tuple[int, int]:
    target_visible = max(1, int(visible_line_count))
    total = max(0, int(total_lines))
    visible = min(target_visible, total)
    max_offset = max(0, total - visible)
    return visible, max_offset


def trim_lines_and_adjust_scroll(
    lines: list[str],
    *,
    max_lines: int,
    scroll_offset: int,
) -> tuple[int, int]:
    if max_lines <= 0:
        return 0, scroll_offset
    if len(lines) <= max_lines:
        return 0, scroll_offset
    removed = len(lines) - max_lines
    del lines[:removed]

    if removed <= 0:
        return 0, scroll_offset
    if scroll_offset <= removed:
        return removed, 0
    return removed, scroll_offset - removed


def get_visible_lines(
    lines: list[str],
    *,
    visible_line_count: int,
    scroll_offset: int,
) -> tuple[list[str], int]:
    visible, max_offset = visible_metrics(len(lines), visible_line_count)
    if visible == 0:
        return [], 0
    scroll_offset = min(int(scroll_offset), max_offset)
    total = len(lines)
    start = max(0, total - visible - scroll_offset)
    end = start + visible
    return lines[start:end], scroll_offset


def get_scroll_state(
    lines: list[str],
    *,
    visible_line_count: int,
    scroll_offset: int,
) -> dict[str, int]:
    visible, max_offset = visible_metrics(len(lines), visible_line_count)
    return {
        "total": len(lines),
        "visible": visible,
        "offset": int(scroll_offset),
        "max_offset": max_offset,
    }


def wrap_lines_for_display(lines: list[str], *, max_cols: int, max_lines: int | None = None) -> list[str]:
    """Deterministically wrap lines to a fixed column width for UI display.

    This is intentionally a pure helper (no state mutations). Controller code
    can opt into it without changing stored scrollback.
    """
    if max_cols <= 0:
        wrapped = [str(line) for line in lines]
    else:
        wrapped = []
        width = int(max_cols)
        for line in lines:
            text = str(line)
            parts = text.splitlines() or [""]
            for part in parts:
                if not part:
                    wrapped.append("")
                    continue
                for i in range(0, len(part), width):
                    wrapped.append(part[i : i + width])

    if max_lines is None:
        return wrapped
    cap = int(max_lines)
    if cap <= 0:
        return []
    if len(wrapped) <= cap:
        return wrapped
    return wrapped[-cap:]

