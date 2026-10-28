"""Shared settings row definitions used by multiple menu overlays."""

from __future__ import annotations

from typing import Any

SETTINGS_ROWS: tuple[tuple[str, str, str], ...] = (
    ("music_volume", "Music Volume", "slider"),
    ("sfx_volume", "SFX Volume", "slider"),
    ("fog_enabled", "Fog", "toggle"),
    ("reduced_flicker", "Calmer Flickering", "toggle"),  # gentler flicker, no stutter (accessibility)
    ("back", "Back", "action"),
)


def toast_settings_saved(window: Any) -> None:
    """Tell the player their settings were kept: once while that message shows, not once a slider step (Milestone
    21B.1: five presses of LEFT made five "UI_SETTINGS_SAVED" toasts)."""
    from ..i18n import tr  # noqa: PLC0415

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return
    text = tr("UI_SETTINGS_SAVED")
    showing = getattr(hud, "active_toasts", None)
    if callable(showing) and text in showing():
        return
    enqueue(text, seconds=2.0)
