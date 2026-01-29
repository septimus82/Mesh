"""Pure model for jumping to problem targets from the Problems panel.

Headless-safe logic for resolving jump targets and formatting location text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from .scene_lint_model import SceneLintIssue


class JumpTarget(TypedDict, total=False):
    """Jump target resolution result."""

    kind: Literal["scene", "entity", "file", "none"]
    path: str | None
    entity_id: str | None
    scene_path: str | None
    line: int | None
    col: int | None


def choose_jump_target(issue: SceneLintIssue) -> JumpTarget:
    """Resolve jump target from a lint issue.

    Returns a dict describing where to jump:
    - kind: 'scene' (load scene), 'entity' (load scene + select entity),
            'file' (reveal in explorer), or 'none' (not resolvable)
    - path: file path if available
    - entity_id: entity ID to select after loading scene
    - scene_path: scene to load
    - line/col: for future file position support (currently unused)

    Deterministic and headless-safe.
    """
    # Entity-specific issues -> jump to entity in scene
    if issue.entity_id and issue.scene_id:
        return JumpTarget(
            kind="entity",
            path=issue.scene_id,
            entity_id=issue.entity_id,
            scene_path=issue.scene_id,
            line=None,
            col=None,
        )

    # Scene-level issues -> jump to scene
    if issue.scene_id and not issue.entity_id:
        return JumpTarget(
            kind="scene",
            path=issue.scene_id,
            entity_id=None,
            scene_path=issue.scene_id,
            line=None,
            col=None,
        )

    # No resolvable target
    return JumpTarget(
        kind="none",
        path=None,
        entity_id=None,
        scene_path=None,
        line=None,
        col=None,
    )


def format_location_text(target: JumpTarget) -> str:
    """Format jump target as location text for clipboard.

    Format: "path:line:col" or "path" if line/col unavailable.
    Returns empty string if no path.
    """
    path = target.get("path")
    if not path:
        return ""

    line = target.get("line")
    col = target.get("col")

    if line is not None and col is not None:
        return f"{path}:{line}:{col}"
    elif line is not None:
        return f"{path}:{line}"
    else:
        return path


def is_jump_supported(target: JumpTarget) -> bool:
    """Check if jump target is actionable.

    Returns True if the target can be jumped to (has a valid kind).
    """
    kind = target.get("kind", "none")
    return kind in ("scene", "entity", "file")
