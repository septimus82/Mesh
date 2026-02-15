"""Pure model for HD-2D look presets."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Hd2dLookPreset:
    id: str
    name: str
    patch: dict[str, Any]


_PRESETS: tuple[Hd2dLookPreset, ...] = (
    Hd2dLookPreset(
        id="soft",
        name="Soft",
        patch={
            "depth_tint_enabled": True,
            "depth_tint_strength": 0.25,
            "depth_tint_near_color": [255, 255, 255, 255],
            "depth_tint_far_color": [210, 210, 230, 255],
            "shadows_enabled": True,
            "shadows_contact_enabled": True,
            "shadows_ao_enabled": False,
            "outline_enabled": False,
            "outline_strength": 0.4,
            "outline_radius_px": 1,
            "outline_color_rgba": [0, 0, 0, 80],
        },
    ),
    Hd2dLookPreset(
        id="crisp",
        name="Crisp",
        patch={
            "depth_tint_enabled": True,
            "depth_tint_strength": 0.2,
            "depth_tint_near_color": [255, 255, 255, 255],
            "depth_tint_far_color": [190, 190, 210, 255],
            "shadows_enabled": True,
            "shadows_contact_enabled": True,
            "shadows_ao_enabled": False,
            "outline_enabled": True,
            "outline_strength": 0.7,
            "outline_radius_px": 1,
            "outline_color_rgba": [0, 0, 0, 110],
        },
    ),
    Hd2dLookPreset(
        id="noir",
        name="Noir",
        patch={
            "depth_tint_enabled": True,
            "depth_tint_strength": 0.55,
            "depth_tint_near_color": [210, 210, 220, 255],
            "depth_tint_far_color": [90, 90, 110, 255],
            "shadows_enabled": True,
            "shadows_contact_enabled": True,
            "shadows_ao_enabled": True,
            "outline_enabled": True,
            "outline_strength": 0.9,
            "outline_radius_px": 2,
            "outline_color_rgba": [0, 0, 0, 160],
        },
    ),
    Hd2dLookPreset(
        id="dreamy",
        name="Dreamy",
        patch={
            "depth_tint_enabled": True,
            "depth_tint_strength": 0.45,
            "depth_tint_near_color": [255, 245, 255, 255],
            "depth_tint_far_color": [200, 180, 220, 255],
            "shadows_enabled": True,
            "shadows_contact_enabled": True,
            "shadows_ao_enabled": True,
            "outline_enabled": True,
            "outline_strength": 0.35,
            "outline_radius_px": 1,
            "outline_color_rgba": [200, 200, 255, 80],
        },
    ),
)


def list_hd2d_presets() -> list[Hd2dLookPreset]:
    return list(_PRESETS)


def get_hd2d_preset_name(preset_id: str) -> str | None:
    wanted = str(preset_id or "").strip().lower()
    for preset in _PRESETS:
        if preset.id == wanted:
            return preset.name
    return None


def get_hd2d_preset_patch(preset_id: str) -> dict[str, Any] | None:
    wanted = str(preset_id or "").strip().lower()
    for preset in _PRESETS:
        if preset.id == wanted:
            return copy.deepcopy(preset.patch)
    return None


def apply_hd2d_preset(scene_payload: dict[str, Any], preset_id: str) -> dict[str, Any]:
    patch = get_hd2d_preset_patch(preset_id)
    if patch is None:
        return copy.deepcopy(scene_payload)
    payload = copy.deepcopy(scene_payload)
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings = dict(settings)
    settings.update(patch)
    payload["settings"] = settings
    return payload
