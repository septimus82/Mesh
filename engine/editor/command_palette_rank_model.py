"""Pure ranking helpers for editor command palette."""
from __future__ import annotations

from collections import deque
from typing import Iterable, Optional, Tuple

from engine.editor.editor_focus_model import FOCUS_PROJECT_EXPLORER

_RECENT_COMMAND_LIMIT = 5
_RECENT_COMMAND_IDS: deque[str] = deque(maxlen=_RECENT_COMMAND_LIMIT)
_RECENCY_SCORE_BONUS = -0.5


def normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def record_command_executed(command_id: str) -> None:
    cmd_id = str(command_id or "").strip()
    if not cmd_id:
        return
    try:
        _RECENT_COMMAND_IDS.remove(cmd_id)
    except ValueError:
        pass
    _RECENT_COMMAND_IDS.appendleft(cmd_id)


def recency_bonus(command_id: str) -> float:
    return _RECENCY_SCORE_BONUS if str(command_id or "").strip() in _RECENT_COMMAND_IDS else 0.0


def score_command(
    command_id: str,
    title: str,
    keywords: Iterable[str],
    query: str,
    focus_target: str | None = None,
) -> Optional[Tuple[float, int, int, int, str, str]]:
    q = normalize_query(query)
    title = str(title or "").strip()
    if not title:
        return None
    title_l = title.lower()

    command_id_text = str(command_id)
    score_bonus = recency_bonus(command_id_text)
    if focus_target == FOCUS_PROJECT_EXPLORER and str(command_id or "").startswith("editor.project_explorer."):
        score_bonus -= 1.0

    if not q:
        return (score_bonus, 0, 0, len(title_l), title_l, command_id_text)

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
    return (score_bonus, int(rank), int(pos), len(title_l), title_l, command_id_text)
