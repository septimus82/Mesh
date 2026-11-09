"""An HD-2D room's picture treatment (M17-L4-2): a colour grade and a vignette, drawn by the renderer's final composite
(engine.hd2d.composite) in the game and in Mesh Studio's editing view alike.

    "settings": {"hd2d": {"post": {"preset": "golden_hour", "strength": 0.8, "vignette": 0.12}}}

- No ``post`` block (every room made before L4-2, and every new room): **off**. The renderer runs its original blit
  (or depth of field), so the picture is exactly what it was.
- ``preset`` (required): ``natural``, ``golden_hour``, ``moonlight`` or ``interior_warm`` (``PRESETS``). Off is no
  block (``project_ops.set_hd2d_post(preset="off")`` removes it).
- ``strength`` (0-1, default 1): the whole treatment, scaled: each grade value moves from neutral toward the
  preset's, and the vignette with it. 0: the original picture, exactly (the composite isn't run).
- ``vignette`` (0-0.5, default the preset's own): how much the picture's corners darken at full strength.
Only the values that differ from those defaults are stored.

The grade works in linear light: the frame holds sRGB-encoded 8-bit values (the renderer lights in them), so each
pixel is decoded, graded, and encoded again; alpha is kept, and each pixel reads its own world texel (no filtering).
In order: white balance and exposure; contrast on luminance only (about mid-grey, in log space, with a soft shoulder so
it never clips); saturation; split toning (cooler shadows, warmer highlights, or the other way); then **highlight
protection**: bright pixels (lamp glass, glTF emission, sunlit highlights) keep their own colour; and a channel the
grade pushes past 0.9 eases toward 1 rather than clipping (only what was already clipped stays so). The vignette darkens
toward the corners in a circle of the picture (not the window: right in Studio's canvas), from 55% of the way out.

No bloom, blur, grain or automatic exposure; the lighting and the materials are untouched. Studio's grid and
selection lines are drawn after the composite, and Mesh's HUD, dialogue and menus after the renderer: never graded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

Rgb = tuple[float, float, float]


@dataclass(frozen=True)
class Grade:
    """A preset's look (at strength 1)."""
    label: str
    white_balance: Rgb = (1.0, 1.0, 1.0)  # linear multipliers
    exposure: float = 1.0
    contrast: float = 1.0  # luminance, about mid-grey (0.18 linear)
    saturation: float = 1.0
    shadow_tint: Rgb = (1.0, 1.0, 1.0)  # split toning: multiplied into the darks ...
    highlight_tint: Rgb = (1.0, 1.0, 1.0)  # ... and the lights, by split
    split: float = 0.0
    protect: float = 0.0  # 0-1: how much the brightest pixels keep their own colour
    vignette: float = 0.0  # the preset's vignette (0-0.5)


NEUTRAL = Grade("Off")
PRESETS: dict[str, Grade] = {
    "natural": Grade("Natural", contrast=1.05, saturation=1.05, protect=0.6, vignette=0.12),
    "golden_hour": Grade("Golden hour", white_balance=(1.04, 1.0, 0.93), contrast=1.05, saturation=1.03,
                         shadow_tint=(0.94, 0.97, 1.07), highlight_tint=(1.05, 1.0, 0.92), split=0.45, protect=0.8,
                         vignette=0.16),
    "moonlight": Grade("Moonlight", white_balance=(0.96, 0.985, 1.04), exposure=1.03, contrast=1.0, saturation=0.93,
                       shadow_tint=(0.94, 0.97, 1.08), highlight_tint=(1.04, 1.0, 0.95), split=0.4, protect=0.9,
                       vignette=0.2),
    "interior_warm": Grade("Interior warm", white_balance=(1.04, 1.0, 0.94), exposure=1.02, contrast=1.0,
                           saturation=1.04, shadow_tint=(0.97, 0.98, 1.04), highlight_tint=(1.04, 1.0, 0.95),
                           split=0.3, protect=0.85, vignette=0.12),
}
STRENGTH = (1.0, 0.0, 1.0)  # (default, lo, hi)
VIGNETTE = (0.0, 0.5)  # (lo, hi)


class PostError(ValueError):
    """A room's ``settings.hd2d.post`` can't be used."""


@dataclass(frozen=True)
class Post:
    """``settings.hd2d.post``, read: the preset, the strength, and the vignette (None: the preset's)."""
    preset: str
    strength: float = 1.0
    vignette: float | None = None

    @property
    def active(self) -> bool:
        """Whether it changes the picture at all (strength 0: the original, the composite not run)."""
        return self.strength > 0.0

    @property
    def grade(self) -> Grade:
        return PRESETS[self.preset]

    @property
    def vignette_amount(self) -> float:
        """The vignette at full strength: the room's own, or its preset's."""
        return self.grade.vignette if self.vignette is None else self.vignette

    def uniforms(self) -> dict[str, Any]:
        """The composite's grade uniforms: every value moved from neutral toward the preset's by ``strength``."""
        g, s = self.grade, self.strength

        def mix(a: float, b: float) -> float:
            return a + (b - a) * s

        def mix3(a: Rgb, b: Rgb) -> Rgb:
            return (mix(a[0], b[0]), mix(a[1], b[1]), mix(a[2], b[2]))

        return {"u_wb": mix3(NEUTRAL.white_balance, g.white_balance), "u_exposure": mix(1.0, g.exposure),
                "u_contrast": mix(1.0, g.contrast), "u_saturation": mix(1.0, g.saturation),
                "u_shadow_tint": g.shadow_tint, "u_highlight_tint": g.highlight_tint, "u_split": g.split * s,
                "u_protect": g.protect, "u_vignette": self.vignette_amount * s}


def _number(raw: dict[str, Any], key: str, lo: float, hi: float, where: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not lo <= value <= hi:
        raise PostError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
    return float(value)


def parse_post(raw: Any) -> Post | None:
    """``settings.hd2d.post`` as Post (None: no block, off). Raises PostError naming the bad key."""
    if raw is None:
        return None
    where = "settings.hd2d.post"
    if not isinstance(raw, dict):
        raise PostError(f"{where} must be an object (got {type(raw).__name__})")
    unknown = set(raw) - {"preset", "strength", "vignette"}
    if unknown:
        raise PostError(f"{where} has unknown keys: {', '.join(sorted(map(str, unknown)))}")
    preset = raw.get("preset")
    if preset not in PRESETS:
        raise PostError(f"{where}.preset must be one of {', '.join(PRESETS)} (got {preset!r})")
    strength = _number(raw, "strength", STRENGTH[1], STRENGTH[2], where) if "strength" in raw else STRENGTH[0]
    vignette = _number(raw, "vignette", *VIGNETTE, where) if "vignette" in raw else None
    return Post(str(preset), strength, vignette)


def stored(post: Post | None) -> dict[str, Any] | None:
    """What the scene keeps: None (no key: off), else the preset and only the values that differ from its defaults."""
    if post is None:
        return None
    out: dict[str, Any] = {"preset": post.preset}
    if post.strength != STRENGTH[0]:
        out["strength"] = post.strength
    if post.vignette is not None and post.vignette != post.grade.vignette:
        out["vignette"] = post.vignette
    return out


__all__ = ["NEUTRAL", "PRESETS", "Grade", "Post", "PostError", "parse_post", "stored"]
