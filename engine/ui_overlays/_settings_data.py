"""Shared settings row definitions used by multiple menu overlays."""

from __future__ import annotations

SETTINGS_ROWS: tuple[tuple[str, str, str], ...] = (
    ("music_volume", "Music Volume", "slider"),
    ("sfx_volume", "SFX Volume", "slider"),
    ("fog_enabled", "Fog", "toggle"),
    ("reduced_flicker", "Calmer Flickering", "toggle"),  # gentler flicker, no stutter (accessibility)
    ("back", "Back", "action"),
)
