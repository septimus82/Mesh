"""Selective bloom (M17-L4-4): a room's ``settings.hd2d.bloom``, off until a creator picks a preset.

**What glows, and why not "the bright pixels".** The world is drawn into an 8-bit picture (RGBA8): every emitter is
added and clamped to the display range before it is stored, so the picture holds no light above white, and a white
wall, a pale sky or sunlit grass is as bright there as a lantern. A blur of the picture's bright pixels would make
them glow alike. So bloom reads instead the light the world *emits*: while it is on, the world's framebuffer gets a
second colour attachment (``EMISSION_FORMAT``: three floats a pixel, unclamped, linear light) that every world shader
writes beside its colour (``OUTPUTS``) in the same draw:

- a glTF material's emission and a lamp's own lamp head (its lamp's colour x intensity: above 1 at a strong lamp),
- scattered sprites that shine (campfire flames, torches, glowcaps: their glow x their own colour),
- a campfire's embers (blended, as they are drawn),
- zero from everything else (ground, characters, water, smoke, weather), which is what hides an emitter behind a
  wall or a character: the depth test keeps whichever is nearer, emission and colour alike; a translucent thing (smoke,
  a shadow blob) dims the emission behind it by its own opacity. No extra draw call, no second pass of the world.

Lamps' light on the ground and walls is illumination, not emission: it never blooms. Nothing that is drawn after the
renderer (Mesh's HUD, dialogue, menus) or after the picture is made (Studio's grid, selection, handles) can glow.

**The pass** (``BloomPass``), each frame bloom is on, after the world and before the final composite:

1. *Prefilter*, into a target ``BASE_HEIGHT`` pixels tall (the picture's aspect): each emission texel above the
   threshold (luminance, linear; a soft knee of ``KNEE`` x the threshold), at most ``MAX_SOURCE`` (one texel can't
   flood the picture), dimmed by the room's haze at that texel's own depth (a lantern far in the haze glows as dimly as
   it shows), averaged over exactly the texels each target pixel covers: area-weighted, so the glow's energy is the
   same at any picture size and a small emitter crossing a pixel boundary doesn't flicker.
2. *Down*: ``LEVELS - 1`` halvings, each a 13-tap filter (no aliasing, no ringing).
3. *Up*: back up the chain, each level a 3x3 tent of the one below mixed with its own by ``spread`` (0: tight, 1:
   wide). Every filter's weights sum to 1: the glow's total light equals the light that passed the threshold.

The composite (engine.hd2d.composite) adds ``strength`` x the result in linear light, after the depth of field and the
haze and before the colour grade and vignette, then encodes for display. The chain's size is fixed in the picture's
terms (``BASE_HEIGHT``, ``LEVELS``), so a glow is the same share of the picture at 720p, 1080p or in Studio's canvas.

**Cost.** Nothing at all while off: no attachment, target, program or pass, the world drawn exactly as before. On: the
emission attachment (4 bytes a pixel: 3.7 MB at 1280x720, 8.3 MB at 1920x1080) and the chain (2.5 MB at 16:9),
made on the first frame that needs them, remade on a new picture size, freed when bloom is turned off, the room
changes or the window closes. A driver refusing any of it leaves bloom off with the reason kept (``Hd2dRenderer
.bloom_unavailable``); the rest of the picture (haze, grade, depth of field) is untouched. Software GL runs it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# Every program drawing into the world's framebuffer declares both: f_emit is ignored (no draw buffer) unless bloom
# is on, when it is the world's emission (linear, unclamped; its alpha is the blend's, as f_color's).
OUTPUTS = "\nlayout(location = 0) out vec4 f_color; layout(location = 1) out vec4 f_emit;\n"
EMISSION_FORMAT = 0x8C3A  # GL_R11F_G11F_B10F: colour-renderable and blendable in every GL 3.3, software GL included
BASE_HEIGHT = 360  # the chain's first level, in pixels tall (the picture's aspect)
LEVELS = 6  # 360, 180, 90, 45, 23, 12 tall: the widest glow a sixth or so of the picture
KNEE = 0.5  # the soft knee's half-width, as a share of the threshold
MIN_KNEE = 0.02
MAX_SOURCE = 4.0  # an emission texel's luminance is capped here before it spreads (linear)

STRENGTH = (0.0, 3.0)
THRESHOLD = (0.0, 1.0)
SPREAD = (0.0, 1.0)


@dataclass(frozen=True)
class Look:
    """A preset's values."""
    label: str
    strength: float
    threshold: float
    spread: float


PRESETS: dict[str, Look] = {
    # tuned on Lakeside and the template village (M17-L4-4 evidence)
    "subtle": Look("Subtle", 1.0, 0.25, 0.5),
    "warm": Look("Warm", 2.0, 0.1, 0.65),
}


class BloomError(ValueError):
    """A room's ``settings.hd2d.bloom`` can't be used."""


@dataclass(frozen=True)
class Bloom:
    """``settings.hd2d.bloom``, read: the preset, and each value (None: the preset's)."""
    preset: str
    strength: float | None = None
    threshold: float | None = None
    spread: float | None = None

    @property
    def look(self) -> Look:
        return PRESETS[self.preset]

    @property
    def values(self) -> Look:
        """Every value in play: the room's own, else its preset's."""
        k = self.look
        return Look(k.label, k.strength if self.strength is None else self.strength,
                    k.threshold if self.threshold is None else self.threshold,
                    k.spread if self.spread is None else self.spread)

    @property
    def active(self) -> bool:
        """Whether it changes the picture at all (strength 0: the original; nothing made, nothing run)."""
        return self.values.strength > 0.0


def knee_weight(luminance: float, threshold: float) -> float:
    """How much of an emission texel of ``luminance`` passes (0-1): none well below the threshold, all of what's
    above it, a smooth (quadratic) knee between. What the prefilter computes."""
    knee = max(threshold * KNEE, MIN_KNEE)
    soft = min(max(luminance - threshold + knee, 0.0), 2.0 * knee)
    soft = soft * soft / (4.0 * knee)
    return max(soft, luminance - threshold) / max(luminance, 1e-5)


def base_size(size: tuple[int, int]) -> tuple[int, int]:
    """The chain's first level for a picture ``size``: ``BASE_HEIGHT`` tall, the picture's aspect."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    return max(1, round(w * BASE_HEIGHT / h)), BASE_HEIGHT


def level_sizes(size: tuple[int, int]) -> list[tuple[int, int]]:
    """Every level's size, the first (``base_size``) to the smallest."""
    w, h = base_size(size)
    out = [(w, h)]
    for _ in range(LEVELS - 1):
        w, h = max(1, (w + 1) // 2), max(1, (h + 1) // 2)
        out.append((w, h))
    return out


def _number(raw: dict[str, Any], key: str, lo: float, hi: float, where: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not lo <= value <= hi:
        raise BloomError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
    return float(value)


def parse_bloom(raw: Any) -> Bloom | None:
    """``settings.hd2d.bloom`` as Bloom (None: no block, off). Raises BloomError naming the bad key."""
    if raw is None:
        return None
    where = "settings.hd2d.bloom"
    if not isinstance(raw, dict):
        raise BloomError(f"{where} must be an object (got {type(raw).__name__})")
    unknown = set(raw) - {"preset", "strength", "threshold", "spread"}
    if unknown:
        raise BloomError(f"{where} has unknown keys: {', '.join(sorted(map(str, unknown)))}")
    preset = raw.get("preset")
    if not isinstance(preset, str) or preset not in PRESETS:
        raise BloomError(f"{where}.preset must be one of {', '.join(PRESETS)} (got {preset!r})")
    return Bloom(preset,
                 _number(raw, "strength", *STRENGTH, where) if "strength" in raw else None,
                 _number(raw, "threshold", *THRESHOLD, where) if "threshold" in raw else None,
                 _number(raw, "spread", *SPREAD, where) if "spread" in raw else None)


def stored(bloom: Bloom | None) -> dict[str, Any] | None:
    """What the scene keeps: None (no key: off), else the preset and only the values that differ from its own."""
    if bloom is None:
        return None
    k, out = bloom.look, {"preset": bloom.preset}
    for key in ("strength", "threshold", "spread"):
        value = getattr(bloom, key)
        if value is not None and value != getattr(k, key):
            out[key] = value
    return out


DEPTH_GLSL = """
uniform int u_ortho; uniform float u_near; uniform float u_far;
float view_depth(float d) {
    if (u_ortho == 1) return u_near + d * (u_far - u_near);
    return u_near * u_far / (u_far - d * (u_far - u_near));
}
"""
PREFILTER_FS = """
#version 330
// The world's emission (texelFetch: exact texels) and depth; u_scale: emission texels per target pixel on each axis
uniform sampler2D u_emit; uniform sampler2D u_depth; uniform vec2 u_scale;
uniform float u_threshold; uniform float u_knee; uniform float u_max;
// the room's haze (engine.hd2d.haze; u_haze 0: none): an emitter in it glows as dimly as it shows
uniform float u_haze; uniform float u_haze_onset; uniform float u_haze_falloff;
out vec4 f_color;
""" + DEPTH_GLSL + """
float luma(vec3 l) { return dot(l, vec3(0.2126, 0.7152, 0.0722)); }
vec3 passed(ivec2 t) {
    vec3 e = texelFetch(u_emit, t, 0).rgb;
    float y = luma(e);
    if (y <= 0.0) return vec3(0.0);
    if (y > u_max) { e *= u_max / y; y = u_max; }
    if (u_haze > 0.0) {
        float d = texelFetch(u_depth, t, 0).r;
        if (d < 1.0) {
            float x = max(view_depth(d) - u_haze_onset, 0.0) / u_haze_falloff;
            float k = 1.0 - u_haze * (1.0 - exp(-3.0 * x * x));
            e *= k; y *= k;
        }
    }
    float soft = clamp(y - u_threshold + u_knee, 0.0, 2.0 * u_knee);
    soft = soft * soft / (4.0 * u_knee);
    return e * (max(soft, y - u_threshold) / max(y, 1e-5));
}
void main() {
    ivec2 size = textureSize(u_emit, 0);
    vec2 lo = floor(gl_FragCoord.xy) * u_scale;
    vec2 hi = lo + u_scale;
    ivec2 a = ivec2(floor(lo));
    ivec2 b = ivec2(ceil(hi)) - 1;
    vec3 sum = vec3(0.0);
    for (int y = a.y; y <= b.y; y++) {
        float wy = min(hi.y, float(y + 1)) - max(lo.y, float(y));
        for (int x = a.x; x <= b.x; x++) {
            float wx = min(hi.x, float(x + 1)) - max(lo.x, float(x));
            sum += wx * wy * passed(clamp(ivec2(x, y), ivec2(0), size - 1));
        }
    }
    f_color = vec4(sum / (u_scale.x * u_scale.y), 1.0);
}
"""
DOWN_FS = """
#version 330
// Half the size: the 13-tap filter (bilinear taps; weights sum to 1), u_texel one texel of the level read
uniform sampler2D u_src; uniform vec2 u_texel;
in vec2 v_uv; out vec4 f_color;
vec3 at(float x, float y) { return texture(u_src, v_uv + u_texel * vec2(x, y)).rgb; }
void main() {
    vec3 o = at(0.0, 0.0) * 0.125;
    o += (at(-2.0, -2.0) + at(2.0, -2.0) + at(-2.0, 2.0) + at(2.0, 2.0)) * 0.03125;
    o += (at(0.0, -2.0) + at(-2.0, 0.0) + at(2.0, 0.0) + at(0.0, 2.0)) * 0.0625;
    o += (at(-1.0, -1.0) + at(1.0, -1.0) + at(-1.0, 1.0) + at(1.0, 1.0)) * 0.125;
    f_color = vec4(o, 1.0);
}
"""
UP_FS = """
#version 330
// Twice the size: the level below as a 3x3 tent (its texels: u_texel), mixed with this level's own by u_spread
uniform sampler2D u_low; uniform sampler2D u_here; uniform vec2 u_texel; uniform float u_spread;
in vec2 v_uv; out vec4 f_color;
vec3 at(float x, float y) { return texture(u_low, v_uv + u_texel * vec2(x, y)).rgb; }
void main() {
    vec3 s = at(0.0, 0.0) * 4.0;
    s += (at(-1.0, 0.0) + at(1.0, 0.0) + at(0.0, -1.0) + at(0.0, 1.0)) * 2.0;
    s += at(-1.0, -1.0) + at(1.0, -1.0) + at(-1.0, 1.0) + at(1.0, 1.0);
    f_color = vec4(mix(texture(u_here, v_uv).rgb, s / 16.0, u_spread), 1.0);
}
"""


class BloomPass:
    """Bloom's GPU side: its three programs, the world's emission attachment (and the framebuffer that draws the world
    with it), and the chain's levels. Made by the renderer the first frame bloom is on; ``release`` frees it all."""

    def __init__(self, ctx: Any, vertex_shader: str) -> None:
        self.ctx = ctx
        made: list[Any] = []
        try:
            for fs in (PREFILTER_FS, DOWN_FS, UP_FS):
                made.append(ctx.program(vertex_shader=vertex_shader, fragment_shader=fs))
        except BaseException:
            for p in made:
                p.delete()
            raise
        self.prefilter, self.down, self.up = made
        from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415  # (the renderer's clip planes)

        self.prefilter["u_emit"], self.prefilter["u_depth"] = 0, 1
        self.prefilter["u_near"], self.prefilter["u_far"] = NEAR, FAR
        self.down["u_src"] = 0
        self.up["u_low"], self.up["u_here"] = 0, 1
        self._world: tuple[Any, Any, Any, Any] | None = None  # (framebuffer, emission, the world's colour, its depth)
        self._chain: tuple[tuple[int, int], list[tuple[Any, Any]], list[tuple[Any, Any]]] | None = None
        self.allocations = 0  # emission attachments and chains made (resizes make new ones)
        self.passes = 0  # passes run by the last ``render``

    # -- the world's emission
    def world_target(self, colour: Any, depth: Any) -> Any:
        """The framebuffer the world is drawn into while bloom is on: the world's own colour and depth, plus the
        emission attachment (the picture's size; remade when the world's textures are)."""
        if self._world is not None and self._world[2] is colour and self._world[3] is depth:
            return self._world[0]
        self._free_world()
        ctx = self.ctx
        emission = ctx.texture(tuple(colour.size), components=3, dtype="f2", internal_format=EMISSION_FORMAT)
        try:
            fbo = ctx.framebuffer(color_attachments=[colour, emission], depth_attachment=depth)
        except BaseException:
            emission.delete()
            raise
        emission.filter = (ctx.NEAREST, ctx.NEAREST)
        self._world = (fbo, emission, colour, depth)
        self.allocations += 1
        return fbo

    def clear_emission(self) -> None:
        """No emission anywhere (after the framebuffer's own clear, which gives every attachment the sky's colour)."""
        from pyglet import gl as raw  # noqa: PLC0415  # (arcade clears every attachment alike)

        zero = (raw.GLfloat * 4)(0.0, 0.0, 0.0, 0.0)
        raw.glClearBufferfv(raw.GL_COLOR, 1, zero)

    @property
    def emission(self) -> Any:
        return self._world[1] if self._world is not None else None

    # -- the chain
    def _levels(self, size: tuple[int, int]) -> tuple[list[tuple[Any, Any]], list[tuple[Any, Any]]]:
        if self._chain is not None and self._chain[0] == tuple(size):
            return self._chain[1], self._chain[2]
        self._free_chain()
        ctx = self.ctx
        downs: list[tuple[Any, Any]] = []
        ups: list[tuple[Any, Any]] = []
        try:
            sizes = level_sizes(size)
            for i, s in enumerate(sizes):
                for into in (downs, ups) if i < len(sizes) - 1 else (downs,):
                    tex = ctx.texture(s, components=3, dtype="f2", internal_format=EMISSION_FORMAT,
                                      wrap_x=ctx.CLAMP_TO_EDGE, wrap_y=ctx.CLAMP_TO_EDGE,
                                      filter=(ctx.LINEAR, ctx.LINEAR))
                    try:
                        into.append((ctx.framebuffer(color_attachments=[tex]), tex))
                    except BaseException:
                        tex.delete()
                        raise
        except BaseException:
            for fbo, tex in downs + ups:
                fbo.delete()
                tex.delete()
            raise
        self._chain = ((int(size[0]), int(size[1])), downs, ups)
        self.allocations += 1
        return downs, ups

    def render(self, quad: Any, depth: Any, bloom: Bloom, haze: tuple[float, float, float] | None,
               ortho: bool) -> Any:
        """The frame's glow (a texture ``BASE_HEIGHT`` tall, linear light) from the emission the world just drew.
        ``haze``: (strength, onset, falloff) of the room's haze this frame, or None. Leaves the last level's framebuffer
        active: the caller makes the picture's own active again."""
        ctx = self.ctx
        if self._world is None:
            raise RuntimeError("BloomPass.render before world_target: no emission to spread")
        emission = self._world[1]
        size = (int(emission.size[0]), int(emission.size[1]))
        downs, ups = self._levels(size)
        v = bloom.values
        p = self.prefilter
        base = downs[0][1].size
        p["u_scale"] = (size[0] / base[0], size[1] / base[1])
        p["u_threshold"], p["u_knee"], p["u_max"] = v.threshold, max(v.threshold * KNEE, MIN_KNEE), MAX_SOURCE
        p["u_haze"] = haze[0] if haze else 0.0
        if haze:
            p["u_haze_onset"], p["u_haze_falloff"] = haze[1], haze[2]
        p["u_ortho"] = 1 if ortho else 0
        self.passes = 0
        with ctx.enabled_only():
            downs[0][0].use()
            emission.use(0)
            depth.use(1)
            quad.render(p)
            self.passes += 1
            for i in range(1, len(downs)):
                src = downs[i - 1][1]
                downs[i][0].use()
                src.use(0)
                self.down["u_texel"] = (1.0 / src.size[0], 1.0 / src.size[1])
                quad.render(self.down)
                self.passes += 1
            self.up["u_spread"] = v.spread
            low = downs[-1][1]
            for i in range(len(ups) - 1, -1, -1):
                ups[i][0].use()
                low.use(0)
                downs[i][1].use(1)
                self.up["u_texel"] = (1.0 / low.size[0], 1.0 / low.size[1])
                quad.render(self.up)
                self.passes += 1
                low = ups[i][1]
        from pyglet import gl as raw  # noqa: PLC0415  # (the world's depth isn't left bound where it's drawn into)

        raw.glActiveTexture(raw.GL_TEXTURE1)
        raw.glBindTexture(raw.GL_TEXTURE_2D, 0)
        raw.glActiveTexture(raw.GL_TEXTURE0)
        return low

    # -- bookkeeping
    def memory_bytes(self) -> int:
        """Bytes of the targets it holds (4 a texel)."""
        total = 0
        if self._world is not None:
            total += self._world[1].width * self._world[1].height * 4
        if self._chain is not None:
            total += sum(t.width * t.height * 4 for _f, t in self._chain[1] + self._chain[2])
        return total

    def gl_objects(self) -> list[Any]:
        out = [self.prefilter, self.down, self.up]
        if self._world is not None:
            out += [self._world[0], self._world[1]]
        if self._chain is not None:
            out += [o for pair in self._chain[1] + self._chain[2] for o in pair]
        return out

    def _free_world(self) -> None:
        if self._world is not None:
            self._world[0].delete()
            self._world[1].delete()
            self._world = None

    def _free_chain(self) -> None:
        if self._chain is not None:
            for fbo, tex in self._chain[1] + self._chain[2]:
                fbo.delete()
                tex.delete()
            self._chain = None

    def release(self) -> None:
        self._free_world()
        self._free_chain()
        for p in (self.prefilter, self.down, self.up):
            p.delete()


__all__ = ["BASE_HEIGHT", "EMISSION_FORMAT", "LEVELS", "MAX_SOURCE", "OUTPUTS", "PRESETS", "Bloom", "BloomError",
           "BloomPass", "Look", "base_size", "knee_weight", "level_sizes", "parse_bloom", "stored"]
