from __future__ import annotations

from typing import Any, Iterable

from ..scene_index import SceneIndex


def build_scene_index_from_sprites(sprites: Iterable[Any]) -> SceneIndex:
    """Build a SceneIndex from a sprite iterable, preserving input order."""
    return SceneIndex.build_from_sprites(list(sprites))

