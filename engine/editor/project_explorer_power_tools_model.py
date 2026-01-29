"""Pure helpers for Project Explorer power tools."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import FrozenSet, Iterable, Optional

__all__ = [
    "invert_selection",
    "compute_common_parent",
    "format_paths_for_clipboard",
    "should_handle_project_explorer_shortcut",
]


def invert_selection(all_ids: Iterable[int], selected_ids: FrozenSet[int]) -> FrozenSet[int]:
    all_set = {int(i) for i in all_ids}
    return frozenset(all_set.difference(selected_ids))


def compute_common_parent(paths: Iterable[str]) -> Optional[str]:
    items = [str(p).replace("\\", "/") for p in paths if str(p).strip()]
    if not items:
        return None
    parents = [PurePosixPath(p).parent.as_posix() for p in items]
    if len(set(parents)) == 1:
        return parents[0] or "."
    # Compute common prefix directory
    split_parts = [p.split("/") for p in parents]
    min_len = min(len(p) for p in split_parts)
    common: list[str] = []
    for i in range(min_len):
        token = split_parts[0][i]
        if all(part[i] == token for part in split_parts[1:]):
            common.append(token)
        else:
            break
    if not common:
        return None
    return "/".join(common) or "."


def format_paths_for_clipboard(paths: Iterable[str]) -> str:
    normalized = [str(p).replace("\\", "/") for p in paths if str(p).strip()]
    return "\n".join(sorted(normalized))


def should_handle_project_explorer_shortcut(controller: object) -> bool:
    if not getattr(controller, "active", False):
        return False
    if getattr(controller, "_left_dock_tab", "") != "Project":
        return False
    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is None:
        return False
    if getattr(project_ctrl, "inline_rename_active", False) is True:
        return False
    return True