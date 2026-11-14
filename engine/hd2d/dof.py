"""Depth of field for an HD-2D room (#460 Phase B): what the camera is focused on stays sharp, what lies nearer or
farther softens with its distance from that focus, as with a real lens. It reads the depth the world was drawn with
(``Hd2dRenderer``'s own colour + depth attachments), so two things at the same height on screen but at different
distances blur differently; it is never a blur by screen position.

    "settings": {"hd2d": {"depth_of_field": {"enabled": true, "focus_range": 2.5, "near_falloff": 10,
                                             "far_falloff": 10, "max_blur": 2.5, "strength": 1.0}}}

- No ``depth_of_field`` block (every room made before Phase B, and every new room): off. Off, or ``strength`` 0, the
  renderer runs its original blit, so the picture is exactly what it was.
- ``enabled`` (a block without it: on). Turning it on without other values chooses **Subtle**
  (``SUBTLE``: a conservative look made for outdoor rooms).
- ``focus_range`` (m, 0.5-20): how far in front of and behind the focus everything stays fully sharp. The focus is
  the followed character (the camera's ``follow`` tag), at the depth of its own upright picture; the sharp band
  always covers that picture's own depth (``character_band``), so the character never softens. No character (an
  empty room, a cutscene with nobody followed): the point the camera looks at.
- ``near_falloff`` / ``far_falloff`` (m, 1-60 / 1-120): beyond the sharp band, how far it takes to reach the most
  blur, nearer the camera and farther away.
- ``max_blur`` (px of a 720-line picture, 0.5-4): the most blur. It scales with the picture's height, so the look is
  the same in any window size.
- ``strength`` (0-1): all of the blur, scaled.

What depth each thing has: ground, structures, decoration, characters and campfires are drawn with their own depth.
Water is drawn without depth (it is see-through), so it blurs as what lies under it (the bed: at most its depth
off); falling weather, embers and smoke blur as what is behind them; soft shadows lie on the ground, so they blur as
it does; the sky is the farthest thing (full far blur: it is a flat colour). Mesh's HUD, menus and dialogue are drawn
after the world, so they are never blurred.

Indoor rooms: their steep camera sees only a few metres of depth, so the effect is slight there; it is left off
unless the creator turns it on. Software rendering (llvmpipe, softpipe, SwiftShader, Microsoft Basic Render) can't
afford it (measured: +86-90 ms a 720p frame): it is bypassed there and ``unavailable_reason`` says why.

Supported: the game's perspective camera (every Mesh camera preset). The orthographic camera is handled by the same
linearisation but has not been measured (untested).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

NEAR, FAR = 0.1, 500.0  # the renderer's camera clip planes (engine.hd2d.renderer.Camera.view_projection)
REFERENCE_LINES = 720.0  # max_blur is in pixels of a picture this tall
TAPS_MIN, TAPS_MAX = 12, 24  # samples a pixel (measured: the cost of the pass is linear in these)
CHARACTER_MARGIN = 0.25  # m kept sharp beyond the followed character's own depth

# (default, lo, hi) per setting; the defaults are Subtle
FIELDS: dict[str, tuple[float, float, float]] = {
    "focus_range": (2.5, 0.5, 20.0),
    "near_falloff": (10.0, 1.0, 60.0),
    "far_falloff": (10.0, 1.0, 120.0),
    "max_blur": (2.5, 0.5, 4.0),
    "strength": (1.0, 0.0, 1.0),
}
SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swiftshader", "basic render", "software rasterizer",
                      "software renderer", "swrast")


class DofError(ValueError):
    """A room's depth-of-field settings can't be used."""


@dataclass(frozen=True)
class DepthOfField:
    enabled: bool = False
    focus_range: float = FIELDS["focus_range"][0]
    near_falloff: float = FIELDS["near_falloff"][0]
    far_falloff: float = FIELDS["far_falloff"][0]
    max_blur: float = FIELDS["max_blur"][0]
    strength: float = FIELDS["strength"][0]

    @property
    def active(self) -> bool:
        """Whether it changes the picture at all (off, or strength 0: the renderer's original blit)."""
        return self.enabled and self.strength > 0.0


OFF = DepthOfField()
SUBTLE = DepthOfField(enabled=True)


def parse_dof(raw: Any) -> DepthOfField:
    """``settings.hd2d.depth_of_field`` as DepthOfField (None: off). Raises DofError naming the bad key."""
    if raw is None:
        return OFF
    where = "settings.hd2d.depth_of_field"
    if not isinstance(raw, dict):
        raise DofError(f"{where} must be an object (got {type(raw).__name__})")
    unknown = set(raw) - {"enabled", *FIELDS}
    if unknown:
        raise DofError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise DofError(f"{where}.enabled must be true or false (got {enabled!r})")
    values = {}
    for key, (default, lo, hi) in FIELDS.items():
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or not lo <= value <= hi:
            raise DofError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
        values[key] = float(value)
    return DepthOfField(enabled=enabled, **values)


def stored(dof: DepthOfField) -> dict[str, Any] | None:
    """What the scene keeps: None (no key) when off with Subtle's values, so an untouched room stays as it was;
    otherwise ``enabled`` and the values that differ from Subtle's."""
    out: dict[str, Any] = {k: getattr(dof, k) for k, (default, _lo, _hi) in FIELDS.items() if getattr(dof, k) != default}
    if not dof.enabled and not out:
        return None
    return {"enabled": dof.enabled, **out}


def with_changes(dof: DepthOfField, **change: Any) -> DepthOfField:
    """``dof`` with ``change`` applied and checked (DofError on a bad value)."""
    raw: dict[str, Any] = {"enabled": dof.enabled, **{k: getattr(dof, k) for k in FIELDS}, **change}
    return parse_dof(raw)


def software_renderer(renderer_name: str | None) -> str | None:
    """The software rasteriser this GL renderer string names (it can't afford the pass), or None."""
    name = (renderer_name or "").lower()
    return next((s for s in SOFTWARE_RENDERERS if s in name), None)


def dof_unavailable_reason(ctx: Any) -> str | None:
    """Why this GL context can't draw the depth of field (a software rasteriser), or None."""
    try:
        name = str(ctx.info.RENDERER)
    except AttributeError:  # (a context without the query: assume hardware, as every other pass does)
        return None
    found = software_renderer(name)
    if found is None:
        return None
    return (f"depth of field is off on this computer: it is drawing with software rendering ({name}), which can't "
            "afford it. The room shows without it; on a graphics card it shows as set.")


def blur_radius(dof: DepthOfField, height_px: int) -> float:
    """The most blur, in pixels of a picture ``height_px`` tall."""
    return dof.max_blur * dof.strength * max(1, int(height_px)) / REFERENCE_LINES


def taps_for(radius_px: float) -> int:
    """Samples a pixel for a blur this wide: enough to cover its disk (about 1.25 per pixel of it), capped."""
    return max(TAPS_MIN, min(TAPS_MAX, math.ceil(1.25 * math.pi * radius_px * radius_px)))


def character_band(height_m: float, pitch_deg: float) -> float:
    """Half the depth an upright character picture ``height_m`` tall spans, seen from ``pitch_deg`` above (plus a
    margin): the focus band never narrower than this, so all of the character is sharp."""
    return abs(height_m) * math.sin(math.radians(pitch_deg)) / 2.0 + CHARACTER_MARGIN


def view_depth(eye: tuple[float, float, float], target: tuple[float, float, float],
               point: tuple[float, float, float]) -> float:
    """``point``'s distance from the camera along its view axis (m): what the depth buffer linearises to."""
    d = [t - e for t, e in zip(target, eye)]
    n = math.sqrt(sum(c * c for c in d)) or 1.0
    return sum((p - e) * c / n for p, e, c in zip(point, eye, d))


def linear_depth(d: float, ortho: bool, near: float = NEAR, far: float = FAR) -> float:
    """A depth-buffer value (0..1) as metres along the view axis (the shader's ``lin``)."""
    if ortho:
        return near + d * (far - near)
    return near * far / (far - d * (far - near))


def coc(distance: float, focus: float, band: float, near_falloff: float, far_falloff: float, radius: float) -> float:
    """Signed blur radius (px) of something ``distance`` m away: < 0 nearer than the sharp band, > 0 farther (the
    shader's ``coc``)."""
    dz = distance - focus
    if abs(dz) <= band:
        return 0.0
    if dz > 0:
        return min(1.0, (dz - band) / max(far_falloff, 1e-3)) * radius
    return -min(1.0, (-dz - band) / max(near_falloff, 1e-3)) * radius


FRAGMENT = """
#version 330
uniform sampler2D u_color;
uniform sampler2D u_depth;
uniform int u_ortho;
uniform float u_near;
uniform float u_far;
uniform float u_focus;       // m along the view axis
uniform float u_band;        // half-width of the sharp band (m)
uniform float u_falloff_n;
uniform float u_falloff_f;
uniform float u_radius;      // the most blur (px of this picture)
uniform int u_taps;
in vec2 v_uv;                // the full-picture quad's (engine.hd2d.renderer.BLIT_VS)
out vec4 f_color;

float lin(float d) {
    if (u_ortho == 1) return u_near + d * (u_far - u_near);
    return u_near * u_far / (u_far - d * (u_far - u_near));
}
float coc(float dist) {  // signed px: < 0 nearer than the band, > 0 farther
    float dz = dist - u_focus;
    if (abs(dz) <= u_band) return 0.0;
    if (dz > 0.0) return min(1.0, (dz - u_band) / u_falloff_f) * u_radius;
    return -min(1.0, (-dz - u_band) / u_falloff_n) * u_radius;
}
void main() {
    // The world's own pixel under this one, from the quad's coordinates (not gl_FragCoord): right in a viewport
    // anywhere in the window, Mesh Studio's canvas included.
    ivec2 top = textureSize(u_color, 0) - 1;
    ivec2 px = clamp(ivec2(floor(v_uv * vec2(top + 1))), ivec2(0), top);
    vec4 centre = texelFetch(u_color, px, 0);
    float zc = lin(texelFetch(u_depth, px, 0).r);
    float cc = abs(coc(zc));
    vec3 sum = centre.rgb;
    float wsum = 1.0;
    const float GOLDEN = 2.39996323;
    // Scatter as gather: a sample adds to this pixel only if its own blur reaches here, and one BEHIND this pixel
    // only within this pixel's own blur, so a sharp silhouette never takes in the blurred background behind it (no
    // halo), while a blurred near thing spreads softly over what is behind it.
    for (int i = 0; i < u_taps; ++i) {
        float r = u_radius * sqrt((float(i) + 0.5) / float(u_taps));
        float a = float(i) * GOLDEN;
        ivec2 d = ivec2(round(vec2(cos(a), sin(a)) * r));
        float dist = length(vec2(d));                 // the offset actually read
        if (dist < 0.5) continue;                     // (the centre is counted once)
        ivec2 q = clamp(px + d, ivec2(0), top);
        float zs = lin(texelFetch(u_depth, q, 0).r);
        float w = clamp(abs(coc(zs)) - dist + 1.0, 0.0, 1.0);
        if (zs > zc + 0.05) w *= clamp(cc - dist + 1.0, 0.0, 1.0);
        sum += texelFetch(u_color, q, 0).rgb * w;
        wsum += w;
    }
    f_color = vec4(sum / wsum, centre.a);
}
"""


class DofPass:
    """The composite on the GPU: one program, drawn with the renderer's own full-picture quad. It reads the
    renderer's attachments and allocates nothing else, then or per frame."""

    def __init__(self, ctx: Any, vertex_shader: str) -> None:
        self.ctx = ctx
        self.program = ctx.program(vertex_shader=vertex_shader, fragment_shader=FRAGMENT)

    def gl_objects(self) -> list[Any]:
        return [self.program]

    def release(self) -> None:
        self.program.delete()

    def render(self, quad: Any, colour: Any, depth: Any, *, ortho: bool, focus: float,
               band: float, dof: DepthOfField, radius: float) -> None:
        """Draw the blurred picture into the active framebuffer (its viewport set by the caller)."""
        p = self.program
        p["u_color"], p["u_depth"] = 0, 1
        p["u_ortho"] = 1 if ortho else 0
        p["u_near"], p["u_far"] = NEAR, FAR
        p["u_focus"], p["u_band"] = float(focus), float(band)
        p["u_falloff_n"], p["u_falloff_f"] = dof.near_falloff, dof.far_falloff
        p["u_radius"], p["u_taps"] = float(radius), taps_for(radius)
        colour.use(0)
        depth.use(1)
        quad.render(p)
        from pyglet import gl as raw  # noqa: PLC0415  # (arcade has no unbind)

        raw.glActiveTexture(raw.GL_TEXTURE1)  # the world's depth isn't left bound where the next frame draws into it
        raw.glBindTexture(raw.GL_TEXTURE_2D, 0)
        raw.glActiveTexture(raw.GL_TEXTURE0)


__all__ = ["OFF", "SUBTLE", "DepthOfField", "DofError", "DofPass", "blur_radius", "character_band", "coc",
           "dof_unavailable_reason",
           "linear_depth", "parse_dof", "software_renderer", "stored", "taps_for", "view_depth",
           "with_changes"]
