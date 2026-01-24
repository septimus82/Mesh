from __future__ import annotations

import os
from engine import optional_arcade

def draw_asset_placement_ghost(
    asset_path: str,
    x: float,
    y: float,
) -> None:
    """
    Draws a semi-transparent ghost of the asset at the given world coordinates.
    """
    try:
        # Load texture (Arcade caches this automatically)
        # Note: asset_path is relative to project root, e.g. "assets/sprites/foo.png"
        # Arcade load_texture expects a path relative to CWD or absolute.
        # Assuming CWD is project root.
        texture = optional_arcade.arcade.load_texture(asset_path)
    except Exception:
        # If loading fails (e.g. headless or bad path), we might draw a fallback or skip
        # In editor context, we normally expect valid paths.
        # Draw a placeholder square
        optional_arcade.arcade.draw_rectangle_outline(
            x, y, 32, 32, optional_arcade.arcade.color.RED, 2
        )
        return

    # Draw semi-transparent
    # alpha=128 is ~50% opacity
    texture.draw_scaled(
        x, y, 1.0, 0.0, 128
    )
