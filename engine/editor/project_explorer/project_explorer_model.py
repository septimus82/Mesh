"""Pure model helpers for the Project Explorer panel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..editor_shell_layout import Rect


PROJECT_LINE_HEIGHT = 18.0
PROJECT_PADDING = 8.0

PROJECT_ROOTS = ("packs", "assets", "scenes", "worlds")
PROJECT_ROOT_FILES = ("config.json",)
EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "artifacts",
    "tests",
    "build",
    "dist",
    ".venv",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


@dataclass(frozen=True, slots=True)
class ProjectRow:
    """Represents a project explorer row."""

    rel_path: str
    name: str
    depth: int
    is_dir: bool


@dataclass(frozen=True, slots=True)
class ProjectExplorerLayout:
    """Layout rectangles for Project Explorer panel."""

    search_rect: "Rect"
    list_rect: "Rect"


@dataclass(frozen=True, slots=True)
class ProjectExplorerRecentItem:
    """Represents a recent entry in Project Explorer."""

    kind: str  # "scene" | "asset" | "path"
    rel_path: str
    label: str


@dataclass(frozen=True, slots=True)
class ProjectExplorerDisplayRow:
    """Display row for Project Explorer list."""

    kind: str  # "header" | "entry"
    header: str | None
    entry: ProjectRow | None
    recent: ProjectExplorerRecentItem | None
    action: str | None = None
    enabled: bool = True


def scan_project_tree(repo_root: Path) -> list[ProjectRow]:
    """Scan the project tree for whitelisted roots."""
    root = Path(repo_root)
    rows: list[ProjectRow] = []
    for root_name in PROJECT_ROOTS:
        path = root / root_name
        if path.is_dir():
            rows.extend(_walk_dir(path, root_name, depth=0))
    for file_name in PROJECT_ROOT_FILES:
        file_path = root / file_name
        if file_path.is_file():
            rows.append(ProjectRow(rel_path=file_name, name=file_name, depth=0, is_dir=False))
    return rows


def normalize_recent_key(kind: str, rel_path: str) -> str:
    normalized = str(rel_path or "").replace("\\", "/")
    return f"{kind}:{normalized}"


def push_recent(
    recent_list: Iterable[ProjectExplorerRecentItem],
    item: ProjectExplorerRecentItem,
    *,
    limit: int = 8,
) -> list[ProjectExplorerRecentItem]:
    """Push a recent item to the front, deduped and bounded."""
    key = normalize_recent_key(item.kind, item.rel_path)
    result = [item]
    for entry in recent_list:
        if normalize_recent_key(entry.kind, entry.rel_path) == key:
            continue
        result.append(entry)
        if len(result) >= limit:
            break
    return result


def coerce_recent_items(
    raw_items: Iterable[dict[str, object]],
    *,
    limit: int = 8,
) -> list[ProjectExplorerRecentItem]:
    """Coerce recent payloads into RecentItem objects."""
    result: list[ProjectExplorerRecentItem] = []
    seen: set[str] = set()
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        rel_path = entry.get("rel_path")
        label = entry.get("label")
        if not isinstance(kind, str) or kind not in ("scene", "asset", "path"):
            continue
        if not isinstance(rel_path, str) or not rel_path.strip():
            continue
        if not isinstance(label, str) or not label.strip():
            continue
        key = normalize_recent_key(kind, rel_path)
        if key in seen:
            continue
        seen.add(key)
        result.append(ProjectExplorerRecentItem(kind=kind, rel_path=rel_path, label=label))
        if len(result) >= limit:
            break
    return result


def recent_items_to_payloads(
    items: Iterable[ProjectExplorerRecentItem],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    for item in items:
        payloads.append({
            "kind": item.kind,
            "rel_path": item.rel_path,
            "label": item.label,
        })
        if len(payloads) >= limit:
            break
    return payloads


def filter_project_rows(rows: Iterable[ProjectRow], query: str) -> list[ProjectRow]:
    """Filter project rows by query, keeping parent folders of matches.

    When query is non-empty, results are ranked by relevance:
    - Exact filename match first
    - Prefix matches second
    - Word boundary matches third
    - Substring matches last
    With deterministic tie-breakers (shorter path, then lexicographic).
    """
    from .project_explorer_rank_model import rank_rows  # noqa: PLC0415

    text = str(query or "").strip().casefold()
    all_rows = list(rows)
    if not text:
        return all_rows

    row_by_path = {row.rel_path: row for row in all_rows}
    include: set[str] = set()
    matched_rows: list[ProjectRow] = []

    for row in all_rows:
        if text in row.rel_path.casefold():
            include.add(row.rel_path)
            matched_rows.append(row)
            parts = row.rel_path.split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if parent in row_by_path:
                    include.add(parent)

    # Rank matched rows by relevance, then collect parent folders at the end
    ranked_matches = rank_rows(matched_rows, text, lambda r: r.rel_path)
    parent_rows = [row for row in all_rows if row.rel_path in include and row not in matched_rows]

    # Return ranked matches first, then parent folders in original tree order
    return ranked_matches + parent_rows


def build_project_explorer_display_rows(
    rows: Iterable[ProjectRow],
    recents: Iterable[ProjectExplorerRecentItem],
    query: str,
) -> tuple[list[ProjectExplorerDisplayRow], list[ProjectExplorerDisplayRow]]:
    """Build display rows and selectable rows."""
    filtered_rows = filter_project_rows(rows, query)
    filtered_recents = _filter_recent_items(recents, query)
    recent_list = list(recents)
    has_recents = bool(recent_list)

    display_rows: list[ProjectExplorerDisplayRow] = []
    selectable_rows: list[ProjectExplorerDisplayRow] = []

    display_rows.append(ProjectExplorerDisplayRow(kind="header", header="RECENT", entry=None, recent=None))
    for recent in filtered_recents:
        row = ProjectExplorerDisplayRow(kind="entry", header=None, entry=None, recent=recent)
        display_rows.append(row)
        selectable_rows.append(row)
    action_row = ProjectExplorerDisplayRow(
        kind="action",
        header=None,
        entry=None,
        recent=None,
        action="clear_recents",
        enabled=has_recents,
    )
    display_rows.append(action_row)
    selectable_rows.append(action_row)

    if filtered_rows:
        display_rows.append(ProjectExplorerDisplayRow(kind="header", header="PROJECT", entry=None, recent=None))
        for entry in filtered_rows:
            row = ProjectExplorerDisplayRow(kind="entry", header=None, entry=entry, recent=None)
            display_rows.append(row)
            selectable_rows.append(row)

    return display_rows, selectable_rows


def clamp_project_selection(index: int, count: int) -> int:
    """Clamp selection index to valid range."""
    if count <= 0:
        return -1
    return max(0, min(index, count - 1))


def clamp_selection_on_selectables(index: int, count: int) -> int:
    """Clamp selection index based on selectable rows."""
    return clamp_project_selection(index, count)


def display_index_from_selectable_index(
    display_rows: Iterable[ProjectExplorerDisplayRow],
    selectable_index: int,
) -> int | None:
    if selectable_index < 0:
        return None
    current = 0
    for idx, row in enumerate(display_rows):
        if not _is_selectable_row(row):
            continue
        if current == selectable_index:
            return idx
        current += 1
    return None


def selectable_index_from_display_index(
    display_rows: Iterable[ProjectExplorerDisplayRow],
    display_index: int,
) -> int | None:
    if display_index < 0:
        return None
    current = 0
    for idx, row in enumerate(display_rows):
        if idx == display_index:
            return current if _is_selectable_row(row) else None
        if _is_selectable_row(row):
            current += 1
    return None


def compute_project_window(index: int, count: int, max_visible: int) -> tuple[int, int]:
    """Compute visible window for project explorer list."""
    if count <= 0 or max_visible <= 0:
        return (0, 0)
    start_idx = 0
    if index > max_visible / 2:
        start_idx = max(0, int(index - max_visible / 2))
    visible = min(count - start_idx, max_visible)
    return (start_idx, visible)


def activation_intent_for_row(row: ProjectRow) -> dict[str, str]:
    """Return activation intent for a project row."""
    if row.is_dir:
        return {"kind": "none"}
    rel_path = row.rel_path
    if _is_scene_path(rel_path):
        return {"kind": "open_scene", "scene_id": rel_path}
    if _is_image_asset(rel_path):
        return {"kind": "spawn_asset", "asset_path": rel_path}
    return {"kind": "copy_path", "path": rel_path}


def activation_intent_for_display_row(row: ProjectExplorerDisplayRow) -> dict[str, str]:
    """Return activation intent for a display row."""
    if row.kind == "action" and row.action == "clear_recents":
        return {"kind": "clear_recents"}
    if row.recent is not None:
        if row.recent.kind == "scene":
            return {"kind": "open_scene", "scene_id": row.recent.rel_path}
        if row.recent.kind == "asset":
            return {"kind": "spawn_asset", "asset_path": row.recent.rel_path}
        if row.recent.kind == "path":
            return {"kind": "copy_path", "path": row.recent.rel_path}
    if row.entry is not None:
        return activation_intent_for_row(row.entry)
    return {"kind": "none"}


def format_project_recent_label(recent: ProjectExplorerRecentItem) -> str:
    """Format a recent entry label."""
    label = recent.label or recent.rel_path
    return f"* {recent.kind}: {label}"


def format_project_action_label(row: ProjectExplorerDisplayRow) -> str:
    if row.action == "clear_recents":
        return "Clear recents (Del)"
    return "Action"


def format_project_row_label(row: ProjectRow) -> str:
    """Format a row label with indentation and folder markers."""
    indent = "  " * max(0, row.depth)
    if row.is_dir:
        return f"{indent}[+] {row.name}/"
    return f"{indent}{row.name}"


def compute_project_explorer_layout(dock: "Rect") -> ProjectExplorerLayout:
    """Compute layout rects for the Project Explorer panel."""
    from ..editor_shell_layout import TAB_HEADER_HEIGHT, Rect

    content_top = dock.top - TAB_HEADER_HEIGHT
    search_top = content_top - PROJECT_PADDING
    search_bottom = search_top - PROJECT_LINE_HEIGHT
    list_top = search_bottom
    list_bottom = dock.bottom + PROJECT_PADDING

    search_rect = Rect(
        left=dock.left + PROJECT_PADDING,
        right=dock.right - PROJECT_PADDING,
        bottom=search_bottom,
        top=search_top,
    )
    list_rect = Rect(
        left=dock.left + PROJECT_PADDING,
        right=dock.right - PROJECT_PADDING,
        bottom=list_bottom,
        top=list_top,
    )
    return ProjectExplorerLayout(search_rect=search_rect, list_rect=list_rect)


def compute_project_explorer_hit_index(
    y: float,
    list_rect: "Rect",
    start_idx: int,
    visible_count: int,
) -> int | None:
    """Compute which row index was clicked."""
    if visible_count <= 0:
        return None
    row_top = list_rect.top
    row_bottom = list_rect.bottom
    if y > row_top or y < row_bottom:
        return None
    offset = int((row_top - y) // PROJECT_LINE_HEIGHT)
    if 0 <= offset < visible_count:
        return start_idx + offset
    return None


def _walk_dir(path: Path, rel_prefix: str, *, depth: int) -> list[ProjectRow]:
    rows: list[ProjectRow] = [
        ProjectRow(rel_path=rel_prefix, name=path.name, depth=depth, is_dir=True)
    ]
    entries = list(path.iterdir())
    dirs = []
    files = []
    for entry in entries:
        name = entry.name
        if entry.is_symlink():
            continue
        if entry.is_dir():
            if _is_excluded_dir(name):
                continue
            dirs.append(entry)
        else:
            files.append(entry)

    dirs.sort(key=lambda p: (p.name.casefold(), p.name))
    files.sort(key=lambda p: (p.name.casefold(), p.name))

    for entry in dirs:
        child_rel = f"{rel_prefix}/{entry.name}"
        rows.extend(_walk_dir(entry, child_rel, depth=depth + 1))
    for entry in files:
        child_rel = f"{rel_prefix}/{entry.name}"
        rows.append(ProjectRow(rel_path=child_rel, name=entry.name, depth=depth + 1, is_dir=False))
    return rows


def _is_excluded_dir(name: str) -> bool:
    if not name:
        return True
    if name.startswith("."):
        return True
    return name in EXCLUDED_DIRS


def _is_scene_path(rel_path: str) -> bool:
    path = rel_path.replace("\\", "/")
    if not path.lower().endswith(".json"):
        return False
    parts = [part.lower() for part in path.split("/") if part]
    return "scenes" in parts


def _is_image_asset(rel_path: str) -> bool:
    path = rel_path.replace("\\", "/")
    if not path.lower().startswith("assets/"):
        return False
    ext = Path(path).suffix.lower()
    return ext in IMAGE_EXTENSIONS


def _filter_recent_items(
    recents: Iterable[ProjectExplorerRecentItem],
    query: str,
) -> list[ProjectExplorerRecentItem]:
    text = str(query or "").strip().casefold()
    if not text:
        return list(recents)
    result: list[ProjectExplorerRecentItem] = []
    for item in recents:
        if text in item.label.casefold() or text in item.rel_path.casefold():
            result.append(item)
    return result


def _is_selectable_row(row: ProjectExplorerDisplayRow) -> bool:
    return row.kind in ("entry", "action")
