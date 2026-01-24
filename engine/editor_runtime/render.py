from __future__ import annotations

from typing import Any


def resolve_display_name(sprite: Any, *, fallback_index: int | None = None, sprite_index: int | None = None) -> str:
    def _normalize(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            value = str(value)
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
        return None

    entity_data = getattr(sprite, "mesh_entity_data", None)
    candidates: list[Any] = []
    if isinstance(entity_data, dict):
        candidates.extend(
            [
                entity_data.get("name"),
                entity_data.get("display_name"),
                entity_data.get("id"),
                entity_data.get("tag"),
            ]
        )

    candidates.extend(
        [
            getattr(sprite, "mesh_name", None),
            getattr(sprite, "name", None),
            getattr(sprite, "mesh_tag", None),
        ]
    )

    for entry in candidates:
        normalized = _normalize(entry)
        if normalized:
            return normalized

    if fallback_index is None:
        fallback_index = sprite_index
    index_value = (fallback_index or 0) + 1
    return f"Entity#{index_value}"

