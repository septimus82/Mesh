"""Scene opening flows for the editor.

Extracted from editor_controller.py to reduce module size.
Contains pure helpers for scene switching and browsing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List

if TYPE_CHECKING:
    from engine.scene_index import SceneRow


def build_scene_switcher_rows(
    cached_options: list[tuple[str, str]],
    query: str,
    recent_scenes: list[str],
) -> list[tuple[str, str]]:
    """Build the visible list of scene options for the switcher.
    
    Args:
        cached_options: All available (path, label) scene options.
        query: Current filter query string.
        recent_scenes: List of recently opened scene paths.
    
    Returns:
        Filtered and sorted list of (path, label) tuples.
    """
    if not cached_options:
        return []

    query = str(query or "").strip()
    if query:
        from engine.command_palette import filter_options  # noqa: PLC0415
        return filter_options(cached_options, query)

    # No query - show recents first, then rest
    label_by_path = {value: label for value, label in cached_options}
    recent_list: list[tuple[str, str]] = []
    for path in recent_scenes:
        label = label_by_path.get(path)
        if label is not None:
            recent_list.append((path, label))
    recent_set = {path for path, _ in recent_list}
    rest = [opt for opt in cached_options if opt[0] not in recent_set]
    return recent_list + rest


def apply_scene_switcher_filter(
    options: list[tuple[str, str]],
    query: str,
) -> list[tuple[str, str]]:
    """Apply filter query to scene switcher options.
    
    Args:
        options: List of (path, label) tuples.
        query: Filter query string.
    
    Returns:
        Filtered list of options.
    """
    query = str(query or "").strip()
    if not query:
        return list(options)
    from engine.command_palette import filter_options  # noqa: PLC0415
    return filter_options(options, query)


def clamp_scene_selection_index(current_index: int, count: int) -> int:
    """Clamp a scene selection index to valid bounds.
    
    Args:
        current_index: Current selection index.
        count: Total number of items.
    
    Returns:
        Clamped index value (-1 if count is 0).
    """
    if count <= 0:
        return -1
    if current_index < 0:
        return 0
    return max(0, min(current_index, count - 1))


def compute_scene_window(index: int, count: int, max_visible: int = 16) -> tuple[int, int]:
    """Compute visible window for scene list scrolling.
    
    Args:
        index: Current selection index.
        count: Total number of items.
        max_visible: Maximum visible items.
    
    Returns:
        Tuple of (start_index, end_index) for visible range.
    """
    if count <= 0:
        return 0, 0
    start_idx = 0
    if index > max_visible / 2:
        start_idx = max(0, int(index - max_visible / 2))
    end_idx = min(count, start_idx + max_visible)
    return start_idx, end_idx


def compute_scene_browser_layout(
    window_width: float,
    window_height: float,
    row_count: int,
) -> dict[str, float]:
    """Compute layout dimensions for scene browser overlay.
    
    Args:
        window_width: Window width in pixels.
        window_height: Window height in pixels.
        row_count: Number of scene rows to display.
    
    Returns:
        Dict with layout keys: left, right, top, bottom, start_x, start_y,
        row_start_y, line_height.
    """
    line_height = 18.0
    header_lines = 3.0
    visible = min(row_count, 16)
    height = max(140.0, 24.0 + line_height * (header_lines + float(visible)))
    width = min(760.0, max(520.0, window_width * 0.7))
    left = (window_width - width) / 2.0
    right = left + width
    bottom = (window_height - height) / 2.0
    top = bottom + height
    start_x = left + 20.0
    start_y = top - 20.0
    row_start_y = start_y - line_height * header_lines
    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "start_x": start_x,
        "start_y": start_y,
        "row_start_y": row_start_y,
        "line_height": line_height,
    }


def compute_scene_browser_hit_index(
    x: float,
    y: float,
    layout: dict[str, float],
    start_idx: int,
    visible_count: int,
) -> int | None:
    """Compute which row index was clicked in the scene browser.
    
    Args:
        x: Click x coordinate.
        y: Click y coordinate.
        layout: Layout dict from compute_scene_browser_layout.
        start_idx: First visible row index.
        visible_count: Number of visible rows.
    
    Returns:
        Row index if click is valid, None otherwise.
    """
    left = layout["left"]
    right = layout["right"]
    top = layout["top"]
    bottom = layout["bottom"]

    # Check if click is within browser bounds
    if x < left or x > right or y < bottom or y > top:
        return None

    if visible_count <= 0:
        return None

    row_start_y = layout["row_start_y"]
    line_height = layout["line_height"]
    list_top = row_start_y + line_height * 0.6
    list_bottom = row_start_y - line_height * visible_count

    if y > list_top or y < list_bottom:
        return None

    offset = int((row_start_y - y) // line_height)
    if 0 <= offset < visible_count:
        return start_idx + offset
    return None


def build_scene_switcher_lines(
    active: bool,
    query: str,
    options: list[tuple[str, str]],
    selection_index: int,
    recent_scenes: list[str],
) -> list[str]:
    """Build display lines for scene switcher overlay.
    
    Args:
        active: Whether switcher is active.
        query: Current filter query.
        options: Visible (path, label) options.
        selection_index: Currently selected index.
        recent_scenes: List of recent scene paths.
    
    Returns:
        List of strings to display.
    """
    if not active:
        return []

    lines = ["SCENE SWITCHER", "--------------"]
    filter_line = f"Filter: {query}"
    if active:
        filter_line += "_"
    lines.append(filter_line)
    lines.append("--------------")

    if not options:
        lines.append("  (No scenes)")
        return lines

    recent_set = set(recent_scenes)
    selection_index = clamp_scene_selection_index(selection_index, len(options))

    start_idx, end_idx = compute_scene_window(selection_index, len(options))

    for idx in range(start_idx, end_idx):
        path, label = options[idx]
        if idx == selection_index:
            prefix = "> "
        elif path in recent_set:
            prefix = "* "
        else:
            prefix = "  "
        lines.append(f"{prefix}{label} [{path}]")

    return lines


def build_scene_browser_lines(
    active: bool,
    query: str,
    rows: List["SceneRow"],
    selection_index: int,
) -> list[str]:
    """Build display lines for scene browser overlay.
    
    Args:
        active: Whether browser is active.
        query: Current search query.
        rows: List of SceneRow objects.
        selection_index: Currently selected index.
    
    Returns:
        List of strings to display.
    """
    if not active:
        return []

    selection_index = clamp_scene_selection_index(selection_index, len(rows))
    lines = ["SCENE BROWSER", f"Search: {query}_", "--------------"]

    if not rows:
        lines.append("  (No scenes)")
        return lines

    start_idx, end_idx = compute_scene_window(selection_index, len(rows))

    for idx in range(start_idx, end_idx):
        row = rows[idx]
        if idx == selection_index:
            prefix = "> "
        elif row.is_recent:
            prefix = "* "
        else:
            prefix = "  "
        pack_label = row.pack_name or "root"
        lines.append(f"{prefix}{row.display_name} [{pack_label}]")

    return lines


def open_scene_by_id(
    scene_id: str,
    *,
    confirm_unsaved_fn: Callable[[str, Callable[[], None]], bool],
    request_scene_change_fn: Callable[[str], None] | None,
    record_recent_fn: Callable[[str], None],
    close_panels_fn: Callable[[], None],
) -> bool:
    """Open a scene by its ID with dirty guard integration.
    
    Args:
        scene_id: The scene path/ID to open.
        confirm_unsaved_fn: Function to check for unsaved changes.
            Should return True if confirmation is pending (deferred).
        request_scene_change_fn: Function to request scene change.
        record_recent_fn: Function to record scene in recents.
        close_panels_fn: Function to close switcher/browser panels.
    
    Returns:
        True if scene was opened, False if deferred or failed.
    """
    from engine.path_norm import normalize_scene_path  # noqa: PLC0415

    normalized = normalize_scene_path(scene_id)
    if not normalized:
        return False

    def _apply() -> None:
        close_panels_fn()
        if request_scene_change_fn is not None:
            request_scene_change_fn(normalized)
        record_recent_fn(normalized)

    if confirm_unsaved_fn("Switch Scene", _apply):
        return False

    _apply()
    return True
