"""Small helpers for widget-based overlays."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence


@dataclass
class OverlayFocusModel:
    """Minimal two-target focus state for text/list overlays."""

    focus: str = "input"

    def toggle_focus(self) -> str:
        self.focus = "results" if self.focus == "input" else "input"
        return self.focus

    def reset(self, focus: str = "input") -> str:
        self.focus = "results" if focus == "results" else "input"
        return self.focus


def _call_bool(obj: Any, method_name: str, *args: Any) -> bool:
    method = getattr(obj, method_name, None)
    if callable(method):
        return bool(method(*args))
    return False


def apply_text_input(overlay: Any, text: str) -> bool:
    return _call_bool(overlay, "append_text", text)


def apply_backspace(overlay: Any) -> bool:
    return _call_bool(overlay, "backspace")


def apply_nav_key(overlay: Any, key: int) -> bool:
    return _call_bool(overlay, "handle_navigation_key", int(key))


def apply_enter(overlay: Any) -> bool:
    return _call_bool(overlay, "on_key_enter")


def apply_mouse_scroll(
    overlay: Any,
    scroll_y: float,
    *,
    x: float = 0.0,
    y: float = 0.0,
    scroll_x: float = 0.0,
) -> bool:
    return _call_bool(overlay, "on_mouse_scroll", float(x), float(y), float(scroll_x), float(scroll_y))


def apply_mouse_press(
    overlay: Any,
    x: float,
    y: float,
    *,
    button: int = 1,
    modifiers: int = 0,
) -> bool:
    return _call_bool(overlay, "on_mouse_press", float(x), float(y), int(button), int(modifiers))


def build_empty_row(message: str) -> str:
    return str(message)


def build_status_row(
    *,
    label: str = "Results",
    count: int,
    selected_index: int | None,
) -> str:
    total = max(0, int(count))
    prefix = f"{label}: {total}"
    if total <= 0 or selected_index is None:
        return prefix
    selected = max(0, min(int(selected_index), total - 1)) + 1
    return f"{prefix}  Selected: {selected}/{total}"


def compose_list_rows(
    content_rows: Sequence[str],
    *,
    empty_row: str | None = None,
    status_row: str | None = None,
    hints_row: str | None = None,
    show_status: bool = True,
) -> list[str]:
    rows = [str(row) for row in content_rows]
    if not rows and empty_row is not None:
        rows.append(str(empty_row))
    if show_status and status_row is not None:
        rows.append(str(status_row))
    if hints_row is not None:
        rows.append(str(hints_row))
    return rows


def resolve_preserved_selection_index(
    previous_items: Sequence[Any],
    new_items: Sequence[Any],
    previous_index: int,
    *,
    identity_fn: Callable[[Any], Any | None],
    clamp_fn: Callable[[int, int], int],
    fallback_index: int = 0,
) -> tuple[int, bool]:
    preserved = False
    target_index = int(fallback_index)

    if 0 <= int(previous_index) < len(previous_items):
        previous_identity = identity_fn(previous_items[int(previous_index)])
        if previous_identity is not None:
            for idx, item in enumerate(new_items):
                if identity_fn(item) == previous_identity:
                    target_index = int(idx)
                    preserved = True
                    break

    return int(clamp_fn(int(target_index), len(new_items))), preserved
