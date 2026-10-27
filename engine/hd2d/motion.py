"""Environmental animation for an HD-2D room's scattered decoration (Milestone 20E): plants sway in the room's wind
(engine.wind), torches flicker, banners stream, glowing plants pulse. All of it on the GPU: the scatter's buffers are
built once (engine.hd2d.scatter_layer) and never touched as things move; each frame sets a few uniforms (the time,
the wind, the settings) and the vertex shader moves every instance.

    "settings": {"hd2d": {"motion": {"enabled": true, "sway": 1.0, "wind": 1.0, "speed": 1.0,
                                     "assets": {"torch": {"fps": 10}, "reeds": {"sway": 1.4}}}}}

- ``enabled``: animation on (a ``motion`` block without it: on). No ``motion`` block: off, so rooms made before
  Milestone 20E look exactly as they did; off, every instance is drawn as 20D drew it, pixel for pixel.
- ``sway`` (0-2): how far plants bend; ``wind`` (0-2): how much the room's wind moves them (0: only a faint idle
  stir); ``speed`` (0.25-3): how fast they flutter and frames turn.
- ``assets``: per asset, ``enabled`` (false: that asset stands still), ``sway`` (0-3, times its own), ``fps`` (its
  frames a second, 1-30), ``loop`` ("loop" or "pingpong") and ``phase`` (0-1: how out of step instances are; 0 all
  together, 1 each its own).

How a plant moves (``angle``; the shader's ``placed`` is the same): it turns about its anchor (its foot, or for a
part such as a tree's canopy, where it is attached), never sliding or stretching. The wind leans it over, more the
stronger the wind (``lean``), and it flutters about that lean at its own rate and phase (from where it stands: two
neighbours never move together). A gust reaches it as the front passes over it, ``lag`` s late (a stiff tree later
than grass). It leans along the wind as the camera sees it: fully across the picture, little toward or away from the
camera (``MAX_DEPTH``: more would only squash or stretch it on screen); the angles are capped, so the top stays above
the ground on any slope a plant may stand on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from engine.wind import GLSL as WIND_GLSL
from engine.wind import PERIOD, Wind, speed_at

MAX_ANGLE = 0.8  # rad (46 degrees): the most a plant leans across the picture
MAX_DEPTH = 0.35  # rad (20 degrees): toward or away from the camera (its height on screen changes by under 6 %)
# Both at once: tip height cos 0.8 cos 0.35 (0.65) > its reach sqrt(sin^2 0.8 + sin^2 0.35) (0.80) x tan 35 (0.56): a tip
# never dips into the steepest slope a plant may stand on
LOOPS = ("loop", "pingpong")


class MotionError(ValueError):
    """A room's motion settings can't be used."""


@dataclass(frozen=True)
class AssetMotion:
    enabled: bool = True
    sway: float = 1.0
    fps: float | None = None  # None: the asset's own
    loop: str | None = None
    phase: float | None = None


@dataclass(frozen=True)
class Motion:
    enabled: bool = False
    sway: float = 1.0
    wind: float = 1.0
    speed: float = 1.0
    assets: tuple[tuple[str, AssetMotion], ...] = ()

    def of(self, asset: str) -> AssetMotion:
        return dict(self.assets).get(asset, AssetMotion())


OFF = Motion()


def _number(block: dict, key: str, where: str, default: float, lo: float, hi: float) -> float:
    value = block.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not lo <= value <= hi:
        raise MotionError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
    return float(value)


def _flag(block: dict, key: str, where: str) -> bool:
    value = block.get(key, True)
    if not isinstance(value, bool):
        raise MotionError(f"{where}.{key} must be true or false (got {value!r})")
    return value


def parse_motion(raw: Any, where: str = "settings.hd2d.motion") -> Motion:
    """``settings.hd2d.motion`` checked; None: off."""
    from engine.hd2d.scatter import ASSETS  # noqa: PLC0415

    if raw is None:
        return OFF
    if not isinstance(raw, dict):
        raise MotionError(f"{where} must be an object like {{\"enabled\": true, \"sway\": 1.0}}")
    unknown = set(raw) - {"enabled", "sway", "wind", "speed", "assets"}
    if unknown:
        raise MotionError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
    assets = raw.get("assets", {})
    if not isinstance(assets, dict):
        raise MotionError(f"{where}.assets must be an object of asset ids to settings")
    per = []
    for name, item in sorted(assets.items()):
        at = f"{where}.assets.{name}"
        if name not in ASSETS:
            raise MotionError(f"{where}.assets has an unknown asset '{name}' (one of: {', '.join(ASSETS)})")
        if not isinstance(item, dict):
            raise MotionError(f"{at} must be an object like {{\"fps\": 8}}")
        unknown = set(item) - {"enabled", "sway", "fps", "loop", "phase"}
        if unknown:
            raise MotionError(f"{at}: unknown setting(s) {', '.join(sorted(unknown))}")
        loop = item.get("loop")
        if loop is not None and loop not in LOOPS:
            raise MotionError(f"{at}.loop must be one of {', '.join(LOOPS)} (got {loop!r})")
        per.append((name, AssetMotion(
            enabled=_flag(item, "enabled", at), sway=_number(item, "sway", at, 1.0, 0.0, 3.0),
            fps=_number(item, "fps", at, 1.0, 1.0, 30.0) if "fps" in item else None, loop=loop,
            phase=_number(item, "phase", at, 1.0, 0.0, 1.0) if "phase" in item else None)))
    return Motion(enabled=_flag(raw, "enabled", where), sway=_number(raw, "sway", where, 1.0, 0.0, 2.0),
                  wind=_number(raw, "wind", where, 1.0, 0.0, 2.0), speed=_number(raw, "speed", where, 1.0, 0.25, 3.0),
                  assets=tuple(per))


# ---------------------------------------------------------------------- how a plant moves (the shader's twin)
def seed_of(x: int, y: int, part: int = 0) -> float:
    """An instance's own number (0..1) from where it stands (px): its flutter's phase and rate, its frames' offset.
    Fixed for an instance, different for its neighbours; worked out once, when its chunk is built."""
    h = (x * 73856093) ^ (y * 19349663) ^ (part * 83492791)
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return (h & 0xFFFF) / 65536.0


def lag(flex: float) -> float:
    """s: how late a gust reaches a plant's top (stiff ones answer slower)."""
    return 0.2 + 1.2 * (1.0 - min(1.0, max(0.0, flex)))


def lean(speed: float) -> float:
    """rad: how far a wind of ``speed`` m/s leans a fully flexible plant (rising, then levelling off)."""
    return 0.6 * speed * speed / (speed * speed + 40.0)


def flutter_rate(seed: float, speed: float = 1.0) -> float:
    """Hz: a plant's own flutter (times the room's ``speed``), a whole number of turns a ``PERIOD``: the clock's
    wrap is seamless."""
    return math.floor((0.9 + 0.8 * seed) * speed * PERIOD) / PERIOD


def wrap_safe_fps(fps: float, frames: int, pingpong: bool) -> float:
    """``fps`` nudged (by less than a frame an hour) so a part's frames come round whole at the clock's wrap."""
    cycle = 2 * frames - 2 if pingpong and frames > 2 else frames
    return round(fps * PERIOD / cycle) * cycle / PERIOD if frames > 1 else fps


def angle(x: float, y: float, t: float, flex: float, seed: float, wind: Wind, motion: Motion,
          right: tuple[float, float] = (1.0, 0.0)) -> tuple[float, float]:
    """rad: how far a plant anchored at (x, y) m leans at time t s, (across the picture, into it), for a camera
    whose right is ``right`` (on the ground). The wind leans it along the wind, as seen: fully across the picture,
    and at most ``MAX_DEPTH`` toward or away from the camera (more would only squash or stretch it on screen); its
    flutter is across the picture. (0, 0) when motion is off."""
    if not motion.enabled:
        return 0.0, 0.0
    s = speed_at(x, y, t - lag(flex), wind) * motion.wind
    vx, vy = wind.vector
    s0 = math.hypot(vx, vy)
    d = (vx / s0, vy / s0) if s0 > 0 else (1.0, 0.0)
    side, depth = d[0] * right[0] + d[1] * right[1], -d[0] * right[1] + d[1] * right[0]
    flutter = (0.035 + 0.10 * s / (s + 5.0)) * math.sin(2 * math.pi * (flutter_rate(seed, motion.speed) * t + seed))
    k = flex * motion.sway
    return (max(-MAX_ANGLE, min(MAX_ANGLE, k * (lean(s) * side + flutter))),
            max(-MAX_DEPTH, min(MAX_DEPTH, k * lean(s) * depth)))


def frame(t: float, seed: float, frames: int, fps: float, phase: float, pingpong: bool) -> int:
    """Which of its ``frames`` an animated part shows at time t s (``fps`` already times the room's speed)."""
    if frames <= 1:
        return 0
    f = math.floor(t * fps + phase * seed * frames)
    if not pingpong:
        return f % frames
    m = f % (2 * frames - 2)
    return m if m < frames else 2 * frames - 2 - m


GLSL = WIND_GLSL + """
uniform float u_time; uniform vec2 u_wind; uniform float u_gust; uniform int u_motion;
uniform float u_sway; uniform float u_influence; uniform float u_rate; uniform float u_frame_du;
uniform float u_period;
uniform vec4 u_slot_a[%(slots)d];  // a part's flex (times its asset's sway), frames, fps, phase variation
uniform vec4 u_slot_b[%(slots)d];  // its glow, ping-pong (1), moving (1), streaming downwind (1: a banner)
uniform vec4 u_slot_c[%(slots)d];  // its sheet (1: 20E's), nearer the camera by (m), light taken nearer the sun
                                   // by (m), its cell in still air (a banner's, hanging: cells on from its own)
// Where a vertex of a scattered sprite is now (m), its uv, its glow, its sheet and how far toward the sun its light is
// taken: turned about its anchor (in_pos) by the wind, its frame chosen by the time. Motion off (or its asset still):
// exactly where Milestone 20D drew it (a part drawn nearer the camera, a torch's flame, is moved that much first).
vec3 placed(out vec2 uv, out float glow, out float sheet, out float lift) {
    int k = int(in_slot + 0.5);
    vec4 a = u_slot_a[k], b = u_slot_b[k], c = u_slot_c[k];
    float h = in_seed, hgt = in_corner.y * u_stretch;
    uv = in_uv; glow = b.x; sheet = c.x; lift = c.z;
    vec2 r = normalize(u_right.xy);  // across the picture, and into it, on the ground
    vec2 f = vec2(-r.y, r.x);
    vec3 base = in_pos;
    if (c.y != 0.0) { base -= vec3(f * c.y, 0.0); }
    if (u_motion == 0 || b.z < 0.5) {
        return base + u_right * in_corner.x + vec3(0.0, 0.0, hgt);
    }
    float t = u_time;
    float s0 = length(u_wind);
    vec2 d = s0 > 0.0 ? u_wind / s0 : vec2(1.0, 0.0);
    float side = dot(d, r), depth = dot(d, f);
    bool limp = c.w > 0.5 && s0 < 1.0;
    if (limp) {
        uv.x += c.w * u_frame_du;
    } else if (a.y > 1.5) {
        float n = a.y, fr = floor(t * a.z + a.w * h * n), i = min(mod(fr, n), n - 1.0);
        if (b.y > 0.5) { float m = mod(fr, 2.0 * n - 2.0); i = m < n ? m : 2.0 * n - 2.0 - m; }
        uv.x += i * u_frame_du;
    }
    glow = b.x * (0.8 + 0.2 * sin(6.2832 * (0.35 * t + h)));
    float lag = 0.2 + 1.2 * (1.0 - clamp(a.x, 0.0, 1.0));
    float s = s0 * max(0.0, 1.0 + u_gust * gust_wave(in_pos.xy, t - lag, u_wind)) * u_influence;
    float lean = 0.6 * s * s / (s * s + 40.0);
    float rate = floor((0.9 + 0.8 * h) * u_rate * u_period) / u_period;
    float flutter = (0.035 + 0.10 * s / (s + 5.0)) * sin(6.2832 * (rate * t + h));
    float kf = a.x * u_sway;
    float ts = clamp(kf * (lean * side + flutter), -%(max)r, %(max)r);
    float td = c.y > 0.0 ? 0.0 : clamp(kf * lean * depth, -%(depth)r, %(depth)r);  // (a flame: across only)
    float cx = in_corner.x;
    if (b.w > 0.5 && !limp) { cx *= (side < 0.0 ? -1.0 : 1.0) * mix(0.45, 1.0, abs(side)); }
    return base + u_right * cx + vec3(r * (sin(ts) * hgt) + f * (sin(td) * hgt), cos(ts) * cos(td) * hgt);
}
"""


def glsl(slots: int) -> str:
    return GLSL % {"slots": max(1, slots), "max": MAX_ANGLE, "depth": MAX_DEPTH}
