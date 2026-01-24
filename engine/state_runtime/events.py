from __future__ import annotations

from typing import Any

from engine.constants import EVENT_ENTERED_ZONE


def apply_event(controller: Any, name: str, payload: dict[str, Any]) -> None:
    if str(name) != EVENT_ENTERED_ZONE:
        return
    zone_id = str(payload.get("zone") or "").strip()
    if not zone_id:
        return
    setter = getattr(controller, "set_var", None)
    if callable(setter):
        setter("last_zone_id", zone_id)

