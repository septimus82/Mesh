"""Lighting cache management and invalidation.

This module provides headless cache tracking for the lighting system.
It computes digests of lighting configurations to detect when rebuilds
are needed, without any GPU/Arcade dependencies.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lighting_config import LightingSceneConfig


@dataclass(slots=True)
class LightingCacheState:
    """Tracks cache state for lighting system invalidation.

    This is a headless cache tracker that computes digests of configurations
    to determine when GPU resources need rebuilding.

    Attributes:
        lights_digest: Digest of current light configurations.
        occluders_digest: Digest of current occluder configurations.
        hulls_digest: Digest of computed shadow hulls.
        ambient_digest: Digest of ambient settings.
        layer_dirty: Whether the light layer needs rebuild.
        shadows_dirty: Whether shadow geometry needs rebuild.
        last_rebuild_frame: Frame number of last rebuild.
    """

    lights_digest: str = ""
    occluders_digest: str = ""
    hulls_digest: str = ""
    ambient_digest: str = ""
    layer_dirty: bool = True
    shadows_dirty: bool = True
    last_rebuild_frame: int = -1

    def clear(self) -> None:
        """Reset cache state, marking everything dirty."""
        self.lights_digest = ""
        self.occluders_digest = ""
        self.hulls_digest = ""
        self.ambient_digest = ""
        self.layer_dirty = True
        self.shadows_dirty = True
        self.last_rebuild_frame = -1

    def digest(self) -> str:
        """Return combined digest of all cache state."""
        combined = f"{self.lights_digest}|{self.occluders_digest}|{self.hulls_digest}|{self.ambient_digest}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass(slots=True)
class CacheInvalidationResult:
    """Result of cache invalidation check.

    Attributes:
        lights_changed: Whether light configs changed.
        occluders_changed: Whether occluder configs changed.
        ambient_changed: Whether ambient settings changed.
        needs_layer_rebuild: Whether light layer needs rebuild.
        needs_shadow_rebuild: Whether shadow geometry needs rebuild.
        old_digest: Previous combined digest.
        new_digest: New combined digest.
    """

    lights_changed: bool = False
    occluders_changed: bool = False
    ambient_changed: bool = False
    needs_layer_rebuild: bool = False
    needs_shadow_rebuild: bool = False
    old_digest: str = ""
    new_digest: str = ""


def compute_ambient_digest(
    ambient_color: tuple[int, int, int, int],
    ambient_tint: tuple[int, int, int, int] | None = None,
    ambient_darkness_alpha: int = 0,
) -> str:
    """Compute digest for ambient lighting settings.

    Args:
        ambient_color: Base ambient RGBA color.
        ambient_tint: Optional tint color.
        ambient_darkness_alpha: Darkness overlay alpha.

    Returns:
        Deterministic string digest.
    """
    tint_str = str(ambient_tint) if ambient_tint else "none"
    return f"amb:{ambient_color}:tint:{tint_str}:dark:{ambient_darkness_alpha}"


def check_cache_invalidation(
    cache_state: LightingCacheState,
    scene_config: "LightingSceneConfig",
) -> CacheInvalidationResult:
    """Check if cache needs invalidation based on new config.

    Compares digests of the new scene configuration against cached digests
    to determine what needs rebuilding.

    Args:
        cache_state: Current cache state.
        scene_config: New scene configuration to check.

    Returns:
        CacheInvalidationResult indicating what changed.
    """
    new_lights_digest = scene_config.lights_digest()
    new_occluders_digest = scene_config.occluders_digest()
    new_ambient_digest = compute_ambient_digest(
        scene_config.ambient_color,
        scene_config.ambient_tint,
        scene_config.ambient_darkness_alpha,
    )

    lights_changed = new_lights_digest != cache_state.lights_digest
    occluders_changed = new_occluders_digest != cache_state.occluders_digest
    ambient_changed = new_ambient_digest != cache_state.ambient_digest

    # Layer rebuild needed if lights or ambient changed
    needs_layer_rebuild = lights_changed or ambient_changed or cache_state.layer_dirty

    # Shadow rebuild needed if occluders changed
    needs_shadow_rebuild = occluders_changed or cache_state.shadows_dirty

    old_digest = cache_state.digest()

    return CacheInvalidationResult(
        lights_changed=lights_changed,
        occluders_changed=occluders_changed,
        ambient_changed=ambient_changed,
        needs_layer_rebuild=needs_layer_rebuild,
        needs_shadow_rebuild=needs_shadow_rebuild,
        old_digest=old_digest,
        new_digest="",  # Computed after update
    )


def update_cache_state(
    cache_state: LightingCacheState,
    scene_config: "LightingSceneConfig",
    hulls_digest: str = "",
    frame_number: int = 0,
) -> None:
    """Update cache state after rebuild.

    Args:
        cache_state: Cache state to update (modified in place).
        scene_config: Scene configuration that was built.
        hulls_digest: Digest of computed shadow hulls.
        frame_number: Current frame number.
    """
    cache_state.lights_digest = scene_config.lights_digest()
    cache_state.occluders_digest = scene_config.occluders_digest()
    cache_state.hulls_digest = hulls_digest
    cache_state.ambient_digest = compute_ambient_digest(
        scene_config.ambient_color,
        scene_config.ambient_tint,
        scene_config.ambient_darkness_alpha,
    )
    cache_state.layer_dirty = False
    cache_state.shadows_dirty = False
    cache_state.last_rebuild_frame = frame_number


def mark_lights_dirty(cache_state: LightingCacheState) -> None:
    """Mark light layer as needing rebuild.

    Args:
        cache_state: Cache state to update.
    """
    cache_state.layer_dirty = True


def mark_shadows_dirty(cache_state: LightingCacheState) -> None:
    """Mark shadow geometry as needing rebuild.

    Args:
        cache_state: Cache state to update.
    """
    cache_state.shadows_dirty = True


def mark_all_dirty(cache_state: LightingCacheState) -> None:
    """Mark everything as needing rebuild.

    Args:
        cache_state: Cache state to update.
    """
    cache_state.layer_dirty = True
    cache_state.shadows_dirty = True
