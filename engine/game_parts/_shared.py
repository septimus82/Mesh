from __future__ import annotations

from typing import Any

from engine.services import (
    InputService,
    PersistenceService,
    ReplayService,
    build_input_service,
    build_persistence_service,
    build_replay_service,
)
from engine.swallowed_exceptions import _log_swallow


def resolve_input_service(window: Any) -> InputService:
    service = getattr(window, "input_service", None)
    if isinstance(service, InputService):
        return service
    service = build_input_service()
    try:
        setattr(window, "input_service", service)
    except Exception:  # noqa: BLE001  # REASON: service resolver fallback should not break runtime if window attribute assignment fails
        _log_swallow("GAME-001", "engine/game.py pass-only blanket swallow")
    return service


def resolve_persistence_service(window: Any) -> PersistenceService:
    service = getattr(window, "persistence_service", None)
    if isinstance(service, PersistenceService):
        return service
    service = build_persistence_service()
    try:
        setattr(window, "persistence_service", service)
    except Exception:  # noqa: BLE001  # REASON: service resolver fallback should not break runtime if window attribute assignment fails
        _log_swallow("GAME-002", "engine/game.py pass-only blanket swallow")
    return service


def resolve_replay_service(window: Any) -> ReplayService:
    service = getattr(window, "replay_service", None)
    if isinstance(service, ReplayService):
        return service
    service = build_replay_service()
    try:
        setattr(window, "replay_service", service)
    except Exception:  # noqa: BLE001  # REASON: service resolver fallback should not break runtime if window attribute assignment fails
        _log_swallow("GAME-003", "engine/game.py pass-only blanket swallow")
    return service
