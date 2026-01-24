from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class NavGridCache(Generic[T]):
    """
    Tiny deterministic cache keyed by (scene_path, revision).

    Intended for per-scene nav grids; callers should pass a monotonic revision
    (e.g. window.scene_dirty_counter) and call invalidate() on reload.
    """

    scene_path: str | None = None
    revision: int = -1
    value: Optional[T] = None

    def invalidate(self) -> None:
        self.scene_path = None
        self.revision = -1
        self.value = None

    def get_or_build(self, *, scene_path: str | None, revision: int, build: Callable[[], T | None]) -> T | None:
        key = str(scene_path or "").strip() or None
        if key is None:
            self.invalidate()
            return None
        if self.scene_path == key and self.revision == int(revision) and self.value is not None:
            return self.value
        self.scene_path = key
        self.revision = int(revision)
        self.value = build()
        return self.value

