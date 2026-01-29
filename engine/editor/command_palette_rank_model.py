"""Pure ranking helpers for editor command palette."""
from __future__ import annotations

from typing import Iterable, Optional, Tuple

from engine.editor.editor_focus_model import FOCUS_PROJECT_EXPLORER


def normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def score_command(
    command_id: str,
    title: str,
    keywords: Iterable[str],
    query: str,
    focus_target: str | None = None,
) -> Optional[Tuple[int, int, int, int, str, str]]:
    q = normalize_query(query)
    title = str(title or "").strip()
    if not title:
        return None
    title_l = title.lower()

    focus_bonus = 0
    if focus_target == FOCUS_PROJECT_EXPLORER and str(command_id or "").startswith("editor.project_explorer."):
        focus_bonus = -1

    if not q:
        return (focus_bonus, 0, 0, len(title_l), title_l, str(command_id))

    rank = 999
    pos = 999

    if title_l.startswith(q):
        rank = 0
        pos = 0
    else:
        p = title_l.find(q)
        if p >= 0:
            rank = 1
            pos = p
        else:
            kw_pos = None
            for kw in keywords:
                kw_l = str(kw or "").strip().lower()
                if not kw_l:
                    continue
                kp = kw_l.find(q)
                if kp >= 0:
                    kw_pos = kp if kw_pos is None else min(kw_pos, kp)
            if kw_pos is not None:
                rank = 2
                pos = int(kw_pos)

    if rank == 999:
        return None
    return (focus_bonus, int(rank), int(pos), len(title_l), title_l, str(command_id))