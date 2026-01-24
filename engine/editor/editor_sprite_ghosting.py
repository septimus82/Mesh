"""Editor-only sprite ghosting for Alt-Drag Duplicate.

Provides temporary visual dimming of original entities during alt-drag duplicate
operations. All changes are render-only and restored after each draw.

Includes caching to avoid redundant per-frame sprite mutations when the effective
set of ghosted IDs, settings, or alt-dup active state hasn't changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Mapping


# -----------------------------------------------------------------------------
# Data Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GhostSpriteSnapshot:
    """Snapshot of sprite visual state before ghosting.

    Attributes:
        entity_id: Entity identifier.
        old_alpha: Original alpha value (if sprite had alpha attribute).
        old_color_rgb: Original color RGB tuple (if sprite had color attribute).
    """

    entity_id: str
    old_alpha: int | None
    old_color_rgb: tuple[int, int, int] | None


@dataclass(slots=True)
class GhostingCacheState:
    """Cache state for ghosting to avoid redundant sprite mutations.

    Attributes:
        ghosted_ids_key: Frozenset of currently ghosted entity IDs.
        alpha: Ghost alpha setting.
        dim_scale: Ghost dim scale setting.
        enabled: Whether ghosting is enabled.
        alt_dup_active: Whether alt-dup mode is active.
    """

    ghosted_ids_key: frozenset[str]
    alpha: int
    dim_scale: float
    enabled: bool
    alt_dup_active: bool


def make_ghosting_cache_key(
    ghost_ids: Collection[str],
    alpha: int,
    dim_scale: float,
    enabled: bool,
    alt_dup_active: bool,
) -> GhostingCacheState:
    """Create a cache key for ghosting state comparison.

    Args:
        ghost_ids: Collection of entity IDs to ghost.
        alpha: Ghost alpha value.
        dim_scale: Ghost dim scale value.
        enabled: Whether ghosting is enabled.
        alt_dup_active: Whether alt-dup mode is active.

    Returns:
        GhostingCacheState for comparison.
    """
    return GhostingCacheState(
        ghosted_ids_key=frozenset(ghost_ids) if ghost_ids else frozenset(),
        alpha=alpha,
        dim_scale=dim_scale,
        enabled=enabled,
        alt_dup_active=alt_dup_active,
    )


def should_reapply_ghosting(
    current: GhostingCacheState | None,
    previous: GhostingCacheState | None,
) -> bool:
    """Determine if ghosting needs to be reapplied.

    Args:
        current: Current ghosting cache state.
        previous: Previous ghosting cache state.

    Returns:
        True if ghosting should be reapplied, False if cached state is valid.
    """
    if previous is None:
        return True
    if current is None:
        return True

    return (
        current.ghosted_ids_key != previous.ghosted_ids_key
        or current.alpha != previous.alpha
        or current.dim_scale != previous.dim_scale
        or current.enabled != previous.enabled
        or current.alt_dup_active != previous.alt_dup_active
    )


# -----------------------------------------------------------------------------
# Pure Helper Functions
# -----------------------------------------------------------------------------


def compute_ghost_alpha(default_alpha: int, ghost_alpha: int = 90) -> int:
    """Compute clamped ghost alpha value.

    Args:
        default_alpha: The original alpha value (unused, kept for API consistency).
        ghost_alpha: Target ghost alpha value.

    Returns:
        Alpha value clamped to [0, 255].
    """
    return max(0, min(255, ghost_alpha))


def _scale_color_component(value: int, scale: float) -> int:
    """Scale a single color component and clamp to [0, 255].

    Args:
        value: Original color component (0-255).
        scale: Scale factor (0.0-1.0 typically).

    Returns:
        Scaled and clamped color component.
    """
    scaled = int(value * scale)
    return max(0, min(255, scaled))


def apply_ghosting_to_sprites(
    sprites_by_entity_id: Mapping[str, Any],
    ghost_entity_ids: Collection[str],
    ghost_alpha: int = 90,
    ghost_color_scale: float = 0.65,
) -> list[GhostSpriteSnapshot]:
    """Apply ghosting effect to specified sprites.

    For each ghost entity sprite:
    - If sprite has .alpha attribute (int): snapshot old, set alpha=ghost_alpha
    - Else if sprite has .color (RGB tuple/list): snapshot old RGB, scale RGB
    - Else: ignore silently

    Args:
        sprites_by_entity_id: Mapping of entity ID to sprite object.
        ghost_entity_ids: Collection of entity IDs to ghost.
        ghost_alpha: Alpha value for ghosted sprites (0-255).
        ghost_color_scale: Scale factor for RGB color dimming (0.0-1.0).

    Returns:
        List of GhostSpriteSnapshot in deterministic order (sorted entity IDs).
    """
    snapshots: list[GhostSpriteSnapshot] = []

    # Process in deterministic order
    for entity_id in sorted(ghost_entity_ids):
        sprite = sprites_by_entity_id.get(entity_id)
        if sprite is None:
            continue

        old_alpha: int | None = None
        old_color_rgb: tuple[int, int, int] | None = None

        # Try alpha first (preferred)
        if hasattr(sprite, "alpha"):
            try:
                current_alpha = getattr(sprite, "alpha", None)
                if isinstance(current_alpha, (int, float)):
                    old_alpha = int(current_alpha)
                    new_alpha = compute_ghost_alpha(old_alpha, ghost_alpha)
                    setattr(sprite, "alpha", new_alpha)
            except (AttributeError, TypeError):
                pass

        # If no alpha, try color scaling
        if old_alpha is None and hasattr(sprite, "color"):
            try:
                current_color = getattr(sprite, "color", None)
                if current_color is not None and len(current_color) >= 3:
                    r, g, b = int(current_color[0]), int(current_color[1]), int(current_color[2])
                    old_color_rgb = (r, g, b)
                    new_r = _scale_color_component(r, ghost_color_scale)
                    new_g = _scale_color_component(g, ghost_color_scale)
                    new_b = _scale_color_component(b, ghost_color_scale)
                    # Preserve alpha if present in color tuple
                    if len(current_color) >= 4:
                        setattr(sprite, "color", (new_r, new_g, new_b, current_color[3]))
                    else:
                        setattr(sprite, "color", (new_r, new_g, new_b))
            except (AttributeError, TypeError, IndexError):
                pass

        # Only create snapshot if we changed something
        if old_alpha is not None or old_color_rgb is not None:
            snapshots.append(GhostSpriteSnapshot(
                entity_id=entity_id,
                old_alpha=old_alpha,
                old_color_rgb=old_color_rgb,
            ))

    return snapshots


def restore_ghosted_sprites(
    snapshots: list[GhostSpriteSnapshot],
    sprites_by_entity_id: Mapping[str, Any],
) -> None:
    """Restore sprites to their original visual state.

    Safely restores alpha/color from snapshots. Missing sprites are ignored.

    Args:
        snapshots: List of GhostSpriteSnapshot from apply_ghosting_to_sprites.
        sprites_by_entity_id: Current mapping of entity ID to sprite object.
    """
    for snapshot in snapshots:
        sprite = sprites_by_entity_id.get(snapshot.entity_id)
        if sprite is None:
            continue

        # Restore alpha if we changed it
        if snapshot.old_alpha is not None:
            try:
                setattr(sprite, "alpha", snapshot.old_alpha)
            except (AttributeError, TypeError):
                pass

        # Restore color if we changed it
        if snapshot.old_color_rgb is not None:
            try:
                current_color = getattr(sprite, "color", None)
                r, g, b = snapshot.old_color_rgb
                # Preserve alpha if present
                if current_color is not None and len(current_color) >= 4:
                    setattr(sprite, "color", (r, g, b, current_color[3]))
                else:
                    setattr(sprite, "color", (r, g, b))
            except (AttributeError, TypeError):
                pass


# -----------------------------------------------------------------------------
# Editor Integration Helpers
# -----------------------------------------------------------------------------


def build_sprite_lookup_for_ghosting(
    controller: Any,
    entity_ids: Collection[str],
) -> dict[str, Any]:
    """Build entity_id -> sprite mapping for ghosting.

    Args:
        controller: Editor controller with window.scene_controller access.
        entity_ids: Entity IDs to look up.

    Returns:
        Dict mapping entity ID to sprite object (if found).
    """
    from ..editor.editor_transform_ops import resolve_entity_id_for_sprite  # noqa: PLC0415

    result: dict[str, Any] = {}

    window = getattr(controller, "window", None)
    if window is None:
        return result

    sc = getattr(window, "scene_controller", None)
    if sc is None:
        return result

    all_sprites = getattr(sc, "all_sprites", None)
    if all_sprites is None:
        return result

    # Build lookup from entity_id -> sprite
    id_set = set(entity_ids)
    try:
        for sprite in all_sprites:
            eid = resolve_entity_id_for_sprite(sprite)
            if eid and eid in id_set:
                result[eid] = sprite
    except (TypeError, AttributeError):
        pass

    return result
