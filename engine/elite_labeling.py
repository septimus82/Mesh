from __future__ import annotations

from typing import Any, Mapping


def is_boss_entity(entity: Mapping[str, Any] | None) -> bool:
    if not isinstance(entity, Mapping):
        return False

    if bool(entity.get("is_boss")):
        return True

    tags = entity.get("tags")
    if isinstance(tags, (list, tuple, set)):
        for tag in tags:
            if isinstance(tag, str) and tag.strip().lower() == "boss":
                return True

    inner = entity.get("entity")
    if isinstance(inner, Mapping):
        return is_boss_entity(inner)

    return False


def is_mini_boss_entity(entity: Mapping[str, Any] | None) -> bool:
    if not isinstance(entity, Mapping):
        return False

    if bool(entity.get("is_mini_boss")):
        return True

    tags = entity.get("tags")
    if isinstance(tags, (list, tuple, set)):
        for tag in tags:
            if isinstance(tag, str) and tag.strip().lower() == "mini_boss":
                return True

    inner = entity.get("entity")
    if isinstance(inner, Mapping):
        return is_mini_boss_entity(inner)

    return False


def is_elite_entity(entity: Mapping[str, Any] | None) -> bool:
    """Best-effort elite detector for resolved prefab/entity payloads.

    Uses existing resolved metadata after variant patches apply:
    - `is_elite == true` (typically added by variant patches)
    - tag `"elite"` in `tags` (typically added by variant patches)

    Handles both "flat" entity dicts and prefab wrapper dicts that contain an inner
    `entity` object plus top-level `tags`.
    """

    if not isinstance(entity, Mapping):
        return False

    if bool(entity.get("is_elite")):
        return True

    tags = entity.get("tags")
    if isinstance(tags, (list, tuple, set)):
        for tag in tags:
            if isinstance(tag, str) and tag.strip().lower() == "elite":
                return True

    inner = entity.get("entity")
    if isinstance(inner, Mapping):
        return is_elite_entity(inner)

    return False


def get_tier_suffix(entity: Mapping[str, Any] | None) -> str:
    if is_boss_entity(entity):
        return " [BOSS]"
    if is_mini_boss_entity(entity):
        return " [MINI-BOSS]"
    if is_elite_entity(entity):
        return " [ELITE]"
    return ""


def format_tier_label(name: str, entity: Mapping[str, Any] | None) -> str:
    base = (name or "").strip() or "<unnamed>"
    return f"{base}{get_tier_suffix(entity)}"


def format_elite_label(name: str, entity: Mapping[str, Any] | None) -> str:
    return format_tier_label(name, entity)
