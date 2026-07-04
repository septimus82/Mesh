"""Live companion-mind diagnostics (SPIKE-PERSIST).

Enable with::

    set MESH_COMPANION_DIAG=1
    py -3.13 main.py
"""

from __future__ import annotations

import os
from typing import Any

from engine.logging_tools import get_logger

logger = get_logger(__name__)

_PREFIX = "[Mesh][CompanionDiag]"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def enabled() -> bool:
    value = os.environ.get("MESH_COMPANION_DIAG", "").strip().lower()
    return value in _TRUTHY


def _top_learned_weights(learned: Any, limit: int = 3) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for name in ("ATTACK", "DEFEND", "HESITATE", "FLEE"):
        try:
            rows.append((name, float(getattr(learned, name, 0.0))))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: abs(item[1]), reverse=True)
    return rows[: max(1, int(limit))]


def log_companion_battle_start(
    *,
    instance_id: str | None,
    source: str,
    mind: Any,
    trigger: str = "",
) -> None:
    """Emit one diagnostic line when a companion battle begins."""
    if not enabled():
        return
    weights = _top_learned_weights(getattr(mind, "learned", None), limit=3)
    weight_text = ", ".join(f"{name}={value:.1f}" for name, value in weights) or "none"
    trust = float(getattr(mind, "trust", 0.0) or 0.0)
    bond = float(getattr(mind, "bond", 0.0) or 0.0)
    trigger_text = f" trigger={trigger}" if trigger else ""
    logger.warning(
        "%s battle_start instance=%s source=%s bond=%.1f trust=%.1f weights=[%s]%s",
        _PREFIX,
        str(instance_id or "none"),
        str(source or "unknown"),
        bond,
        trust,
        weight_text,
        trigger_text,
    )
