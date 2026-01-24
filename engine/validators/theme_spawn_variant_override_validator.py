from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engine.prefabs import get_prefab_manager


def validate_theme_spawn_variant_override_settings(
    *,
    scene_path: str,
    settings: Mapping[str, Any] | None,
    prefab_manager: Any | None = None,
) -> tuple[list[str], list[str]]:
    """Validate the scene-level themed-spawn variant override settings.

    Returns (errors, warnings). This is validation-only; it does not mutate settings.
    """
    if not isinstance(settings, Mapping):
        return [], []

    override = settings.get("theme_spawn_variant_id")
    legacy = settings.get("variant_id")

    errors: list[str] = []
    warnings: list[str] = []

    if override is not None and legacy is not None:
        errors.append(f"Scene {scene_path}: settings cannot specify both theme_spawn_variant_id and variant_id")
        return errors, warnings

    raw = override if override is not None else legacy
    if raw is None:
        return errors, warnings

    if not isinstance(raw, str) or not raw.strip():
        errors.append(f"Scene {scene_path}: theme_spawn_variant_id must be a non-empty string")
        return errors, warnings

    pm = prefab_manager if prefab_manager is not None else get_prefab_manager()
    variant_id = raw.strip()
    if not pm.get_variant(variant_id):
        errors.append(f"Scene {scene_path}: Unknown theme_spawn_variant_id '{variant_id}'")
        return errors, warnings

    if override is None and legacy is not None:
        warnings.append(f"Scene {scene_path}: settings.variant_id is deprecated for themed spawns; use theme_spawn_variant_id")

    return errors, warnings

