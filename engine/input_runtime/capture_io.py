from __future__ import annotations

from typing import Sequence


def _recent_push_many(window: object, *, attr: str, values: Sequence[object], max_items: int = 12) -> None:
    if not values:
        return
    recent = getattr(window, attr, None)
    if not isinstance(recent, list):
        recent = []
    # Unique move-to-front in deterministic order.
    for v in values:
        try:
            while v in recent:
                recent.remove(v)
        except Exception:  # noqa: BLE001
            continue
        recent.insert(0, v)
    if len(recent) > int(max_items):
        del recent[int(max_items) :]
    setattr(window, attr, recent)


def _recent_push_int(window: object, *, attr: str, value: int, max_items: int = 12) -> None:
    _recent_push_many(window, attr=attr, values=[int(value)], max_items=max_items)


def _recent_push_str(window: object, *, attr: str, value: str, max_items: int = 12) -> None:
    text = str(value or "").strip()
    if not text:
        return
    _recent_push_many(window, attr=attr, values=[text], max_items=max_items)
