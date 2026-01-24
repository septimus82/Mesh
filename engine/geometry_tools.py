from __future__ import annotations

from typing import Iterable


def _is_close(a: float, b: float, eps: float) -> bool:
    return abs(a - b) <= eps


def _points_close(p1: tuple[float, float], p2: tuple[float, float], eps: float) -> bool:
    return _is_close(p1[0], p2[0], eps) and _is_close(p1[1], p2[1], eps)


def sanitize_poly(
    points: Iterable[Iterable[float]],
    *,
    eps: float = 1e-6,
) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    prev: tuple[float, float] | None = None
    for entry in points:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        try:
            pt = (float(entry[0]), float(entry[1]))
        except Exception:  # noqa: BLE001
            continue
        if prev is not None and _points_close(prev, pt, eps):
            continue
        cleaned.append(pt)
        prev = pt

    if len(cleaned) >= 2 and _points_close(cleaned[0], cleaned[-1], eps):
        cleaned.pop()

    unique: list[tuple[float, float]] = []
    for pt in cleaned:
        if any(_points_close(pt, other, eps) for other in unique):
            continue
        unique.append(pt)

    if len(unique) < 3:
        return []
    return unique
