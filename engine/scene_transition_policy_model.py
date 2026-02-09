"""
Pure scene transition policy model.

Decouples runtime transitions from editor unsaved-changes behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SceneTransitionRequest:
    from_scene_path: str | None
    to_scene_path: str
    reason: str
    is_editor: bool
    has_unsaved_changes: bool


@dataclass(frozen=True)
class SceneTransitionDecision:
    allowed: bool
    requires_confirm: bool
    message_lines: Tuple[str, ...]


def decide_scene_transition(req: SceneTransitionRequest) -> SceneTransitionDecision:
    if not req.is_editor:
        return SceneTransitionDecision(True, False, ())
    if not req.has_unsaved_changes:
        return SceneTransitionDecision(True, False, ())
    reason = str(req.reason or "").strip()
    lines: Tuple[str, ...] = (reason,) if reason else ()
    return SceneTransitionDecision(False, True, lines)
