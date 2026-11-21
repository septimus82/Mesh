"""Shared settings row definitions used by multiple menu overlays."""

from __future__ import annotations

from typing import Any

SETTINGS_ROWS: tuple[tuple[str, str, str], ...] = (
    ("music_volume", "Music Volume", "slider"),
    ("sfx_volume", "SFX Volume", "slider"),
    ("ambience_volume", "Ambience Volume", "slider"),  # rain, wind, water, birds (Milestone 21B)
    ("fog_enabled", "Fog", "toggle"),
    ("reduced_flicker", "Calmer Flickering", "toggle"),  # gentler flicker, no stutter (accessibility)
    ("back", "Back", "action"),
)


def toast_settings_saved(window: Any) -> None:
    """Tell the player their settings were kept: once while that message shows, not once a slider step (Milestone
    21B.1: five presses of LEFT made five "UI_SETTINGS_SAVED" toasts)."""
    _toast_once(window, "UI_SETTINGS_SAVED")


def toast_settings_not_saved(window: Any) -> None:
    """Tell the player their settings could not be kept (H9.1: never "saved" when they weren't), the same way."""
    _toast_once(window, "UI_SETTINGS_NOT_SAVED")


def _toast_once(window: Any, key: str) -> None:
    from ..i18n import tr  # noqa: PLC0415

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return
    text = tr(key)
    showing = getattr(hud, "active_toasts", None)
    if callable(showing) and text in showing():
        return
    enqueue(text, seconds=2.0)
