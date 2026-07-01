"""Asset loading and caching utilities for Mesh Engine."""

from __future__ import annotations

from typing import Dict, Optional, cast

import engine.optional_arcade as optional_arcade

from .logging_tools import get_logger
from .paths import resolve_path

logger = get_logger(__name__)


class AssetManager:
    """Simple texture cache that avoids reloading the same file multiple times."""

    def __init__(self) -> None:
        self._textures: Dict[str, optional_arcade.arcade.Texture] = {}
        self._placeholder: Optional[optional_arcade.arcade.Texture] = None

    def _resolve_path(self, path: str) -> str:
        return str(resolve_path(path))

    def _load_texture_internal(self, path: str) -> Optional[optional_arcade.arcade.Texture]:
        try:
            texture = optional_arcade.arcade.load_texture(path)
            logger.debug("Loaded texture '%s'", path)
            return texture
        except Exception as exc:  # noqa: BLE001  # REASON: asset texture load backend isolation
            logger.error("Failed to load texture '%s': %s", path, exc)
            return None

    def get_texture(self, path: str) -> Optional[optional_arcade.arcade.Texture]:
        key = self._resolve_path(path)
        if key in self._textures:
            return self._textures[key]

        texture = self._load_texture_internal(key)
        if texture is None:
            texture = self._get_placeholder_texture()
        if texture is not None:
            self._textures[key] = texture
        return texture

    def load_sprite_sheet(
        self,
        path: str,
        frame_width: int,
        frame_height: int,
        total_frames: int,
        start_frame: int = 0,
    ) -> list[optional_arcade.arcade.Texture]:
        """Load and slice a sprite sheet into a list of textures."""
        resolved_path = self._resolve_path(path)

        # Load the full texture to get dimensions and calculate columns
        full_texture = self.get_texture(path)
        if not full_texture:
            return []

        img_width = full_texture.width
        columns = img_width // frame_width
        if columns <= 0:
            columns = 1

        count_to_load = start_frame + total_frames

        try:
            try:
                sheet = optional_arcade.arcade.load_spritesheet(resolved_path)
            except TypeError:
                sheet = None

            get_texture_grid = getattr(sheet, "get_texture_grid", None) if sheet is not None else None
            if callable(get_texture_grid):
                textures = list(
                    get_texture_grid(
                        (frame_width, frame_height),
                        columns,
                        count_to_load,
                        margin=(0, 0, 0, 0),
                    )
                )
            else:
                # Older Arcade versions and the headless fallback expose the
                # pre-3.x helper signature directly.
                textures = cast(
                    list[optional_arcade.arcade.Texture],
                    optional_arcade.arcade.load_spritesheet(
                        resolved_path,
                        frame_width,
                        frame_height,
                        columns,
                        count_to_load,
                        0,  # margin
                    ),
                )

            # Slice the specific range requested
            if start_frame > 0:
                if start_frame < len(textures):
                    textures = textures[start_frame:]
                else:
                    textures = []

            # Trim to requested count
            textures = textures[:total_frames]

            logger.debug("Loaded sprite sheet '%s' (subset %d frames)", path, len(textures))
            return textures
        except Exception as exc:
            logger.error("Failed to load sprite sheet '%s': %s", path, exc)
            return []

    def _get_placeholder_texture(self) -> Optional[optional_arcade.arcade.Texture]:
        if self._placeholder is not None:
            return self._placeholder

        placeholder_path = self._resolve_path("assets/placeholder.png")
        try:
            self._placeholder = optional_arcade.arcade.load_texture(placeholder_path)
            logger.info("Using 'assets/placeholder.png' as fallback texture")
        except Exception:
            logger.info("Creating generated placeholder texture")
            self._placeholder = optional_arcade.arcade.make_soft_square_texture(16, optional_arcade.arcade.color.MAGENTA, 255, 255)
        return self._placeholder

    def clear(self) -> None:
        self._textures.clear()

    def get_cache_keys(self) -> list[str]:
        """Return a list of cached texture keys."""
        return list(self._textures.keys())

    def get_cache_size(self) -> int:
        """Return the number of cached textures."""
        return len(self._textures)
