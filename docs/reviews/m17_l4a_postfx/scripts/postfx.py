"""M17-L4A prototype post pass (scratch, never engine code): one full-screen fragment pass reading the world's colour
(as the renderer composited it: the plain blit, or the depth of field) and the world's depth, in this order:

  1. atmospheric depth (haze): mixes toward a haze colour by how far a pixel lies BEYOND the focus depth (view-axis
     metres from the eye, reconstructed from the depth buffer), optionally thinning with height above the ground;
  2. colour grade: white balance, contrast about mid-grey on luminance only (log2 space), saturation, split toning,
     with highlight protection (bright pixels such as lamp glass keep their colour);
  3. vignette: aspect-correct elliptical edge darkening.

All maths in linear light (the frame holds sRGB-encoded 8-bit values: decode, work, encode). texelFetch, no
filtering: with every effect off the output is the input texel exactly (verified by the harness).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

import numpy as np

POST_FS = """
#version 330
uniform sampler2D u_colour; uniform sampler2D u_depth;
uniform mat4 u_inv_vp; uniform vec3 u_eye; uniform vec3 u_fwd; uniform vec2 u_size;
uniform int u_haze_on; uniform vec3 u_haze_col; uniform float u_focus; uniform float u_haze_start;
uniform float u_haze_range; uniform float u_haze_max; uniform float u_haze_ground; uniform float u_haze_height;
uniform int u_grade_on; uniform vec3 u_wb; uniform float u_contrast; uniform float u_pivot; uniform float u_sat;
uniform vec3 u_shadow_tint; uniform vec3 u_high_tint; uniform float u_split; uniform float u_protect;
uniform float u_exposure;
uniform float u_vig; uniform float u_vig_inner; uniform float u_vig_outer;
uniform int u_debug;
out vec4 f_color;
vec3 lin(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }
vec3 enc(vec3 l) { l = clamp(l, 0.0, 1.0); return mix(l * 12.92, 1.055 * pow(l, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, l)); }
float luma(vec3 l) { return dot(l, vec3(0.2126, 0.7152, 0.0722)); }
void main() {
    ivec2 p = ivec2(gl_FragCoord.xy);
    vec4 src = texelFetch(u_colour, p, 0);
    if (u_haze_on == 0 && u_grade_on == 0 && u_vig <= 0.0 && u_debug == 0) { f_color = src; return; }
    vec3 c = lin(src.rgb);
    float d = texelFetch(u_depth, p, 0).r;
    vec2 ndc = (vec2(p) + 0.5) / u_size * 2.0 - 1.0;
    vec4 w = u_inv_vp * vec4(ndc, d * 2.0 - 1.0, 1.0);
    vec3 world = w.xyz / w.w;
    float depth = d >= 0.999999 ? 1e4 : dot(world - u_eye, u_fwd);  // view-axis metres (the sky: very far)
    float haze = 0.0;
    if (u_haze_on == 1) {
        haze = clamp((depth - (u_focus + u_haze_start)) / max(0.01, u_haze_range), 0.0, 1.0);
        haze = haze * haze * (3.0 - 2.0 * haze) * u_haze_max;  // smooth onset
        if (u_haze_height > 0.0 && d < 0.999999) haze *= exp(-max(0.0, world.z - u_haze_ground) / u_haze_height);
        c = mix(c, u_haze_col, haze);
    }
    if (u_debug == 1) { f_color = vec4(vec3(clamp((depth - u_focus) / 20.0 * 0.5 + 0.5, 0.0, 1.0)), 1.0); return; }
    if (u_debug == 2) { f_color = vec4(vec3(haze), 1.0); return; }
    if (u_grade_on == 1) {
        vec3 o = c;
        vec3 g = c * u_wb * u_exposure;
        float y = max(luma(g), 1e-5);
        float y2 = u_pivot * pow(y / u_pivot, u_contrast);       // contrast on luminance, about mid-grey
        y2 = y2 / (1.0 + max(0.0, y2 - 0.8) * 1.5);             // soft shoulder: no hard clip from the contrast
        g *= y2 / y;
        float yy = luma(g);
        g = mix(vec3(yy), g, u_sat);
        float t = clamp(yy / (2.0 * u_pivot), 0.0, 1.0);          // split toning: shadows / highlights tints
        g *= mix(vec3(1.0), mix(u_shadow_tint, u_high_tint, t), u_split);
        float keep = u_protect * smoothstep(0.55, 0.95, max(max(o.r, o.g), o.b));
        c = mix(g, o, keep);                                      // highlight protection (lamp glass, emission)
    }
    if (u_vig > 0.0) {
        vec2 q = (vec2(p) + 0.5) / u_size - 0.5;
        q.x *= u_size.x / u_size.y;                               // aspect-correct: round in the picture
        float r = length(q) / length(vec2(0.5 * u_size.x / u_size.y, 0.5));  // 0 centre, 1 corner
        c *= 1.0 - u_vig * smoothstep(u_vig_inner, u_vig_outer, r);
    }
    f_color = vec4(enc(c), 1.0);
}
"""


@dataclass
class Post:
    """One candidate's settings (scratch only; no scene keys)."""
    haze: bool = False
    haze_col: tuple[float, float, float] = (0.6, 0.7, 0.85)  # linear
    haze_start: float = 2.0      # m beyond the focus before haze begins
    haze_range: float = 14.0     # m over which it reaches haze_max
    haze_max: float = 0.3
    haze_height: float = 0.0     # m: e-folding height above the ground (0: no height term)
    grade: bool = False
    wb: tuple[float, float, float] = (1.0, 1.0, 1.0)
    exposure: float = 1.0
    contrast: float = 1.0
    pivot: float = 0.18
    sat: float = 1.0
    shadow_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    high_tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    split: float = 0.0
    protect: float = 0.0
    vig: float = 0.0
    vig_inner: float = 0.55
    vig_outer: float = 1.05
    debug: int = 0
    dof: Any = None              # an engine.hd2d.dof.DepthOfField to run the EXISTING depth of field (None: room's own)
    label: str = ""

    def active(self) -> bool:
        return self.haze or self.grade or self.vig > 0 or self.debug != 0

    def as_dict(self) -> dict[str, Any]:
        return {f.name: (repr(getattr(self, f.name)) if f.name == "dof" else getattr(self, f.name)) for f in fields(self)}


def srgb_to_linear(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    return (r, g, b)


class PostPass:
    """The prototype pass on a moderngl/arcade context: run(colour_tex, depth_tex, renderer, post) -> RGB bytes."""

    def __init__(self, ctx: Any, blit_vs: str, quad: Any, size: tuple[int, int]) -> None:
        self.ctx, self.quad, self.size = ctx, quad, size
        self.prog = ctx.program(vertex_shader=blit_vs, fragment_shader=POST_FS)
        self.tex = ctx.texture(size, components=4)
        self.fbo = ctx.framebuffer(color_attachments=[self.tex])

    def uniforms(self, renderer: Any, post: Post, focus: float) -> None:
        pr = self.prog
        cam = renderer.camera
        vp = np.array(renderer.last_vp, dtype=np.float64)
        inv = np.linalg.inv(vp)
        pr["u_inv_vp"] = tuple(float(x) for x in inv.T.flatten())  # column-major
        eye = np.array(cam.eye(), dtype=np.float64)
        tgt = np.array(cam.target, dtype=np.float64)
        fwd = (tgt - eye) / np.linalg.norm(tgt - eye)
        pr["u_eye"] = tuple(eye)
        pr["u_fwd"] = tuple(fwd)
        pr["u_size"] = (float(self.size[0]), float(self.size[1]))
        pr["u_focus"] = float(focus)
        ground = renderer.settings.ground.elevation / 32.0 if renderer.settings.ground is not None else 0.0
        vals = {"u_haze_on": int(post.haze), "u_haze_col": post.haze_col, "u_haze_start": post.haze_start,
                "u_haze_range": post.haze_range, "u_haze_max": post.haze_max, "u_haze_ground": ground,
                "u_haze_height": post.haze_height, "u_grade_on": int(post.grade), "u_wb": post.wb,
                "u_exposure": post.exposure, "u_contrast": post.contrast, "u_pivot": post.pivot, "u_sat": post.sat,
                "u_shadow_tint": post.shadow_tint, "u_high_tint": post.high_tint, "u_split": post.split,
                "u_protect": post.protect, "u_vig": post.vig, "u_vig_inner": post.vig_inner,
                "u_vig_outer": post.vig_outer, "u_debug": post.debug}
        for k, v in vals.items():
            try:
                pr[k] = v
            except KeyError:  # (optimised away)
                pass

    def run(self, colour: Any, depth: Any, renderer: Any, post: Post, focus: float, read: bool = True) -> bytes | None:
        ctx = self.ctx
        self.fbo.use()
        self.uniforms(renderer, post, focus)
        colour.use(0)
        depth.use(1)
        self.prog["u_colour"] = 0
        self.prog["u_depth"] = 1
        with ctx.enabled_only():
            self.quad.render(self.prog)
        return self.fbo.read(components=3) if read else None

    def release(self) -> None:
        for o in (self.fbo, self.tex, self.prog):
            try:
                o.release() if hasattr(o, "release") else o.delete()
            except Exception:
                pass


@dataclass
class Presets:
    items: dict[str, Post] = field(default_factory=dict)
