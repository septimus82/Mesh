"""#460 Phase A PROTOTYPE (scratch only, not product code): a depth-aware depth-of-field pass for Mesh's HD-2D renderer.

It reads the renderer's own world framebuffer attachments (colour + the 24-bit depth texture the world was depth-tested
against), linearises depth into metres along the view axis with the same near/far the renderer's camera uses
(``engine.hd2d.renderer.Camera.view_projection``: 0.1 .. 500 m, perspective or orthographic), and gathers a bounded
blur whose radius is each pixel's circle of confusion (CoC) from its distance to the focal plane.

Halo control ("scatter as gather"): a sample contributes only if its own CoC reaches the centre pixel, and a sample
BEHIND the centre only within the centre's own CoC, so a sharp foreground silhouette never takes in blurred background
(no bleed onto the in-focus player or a near wall), while a blurred foreground spills softly over what is behind it.
"""
from __future__ import annotations

import math
from array import array
from typing import Any

FRAGMENT = """
#version 330
uniform sampler2D u_color;
uniform sampler2D u_depth;
uniform float u_near;
uniform float u_far;
uniform int u_ortho;
uniform float u_focus;       // focal distance along the view axis (m)
uniform float u_range;       // half-width of the sharp band around it (m)
uniform float u_falloff_n;   // metres nearer than the band over which blur grows to its maximum
uniform float u_falloff_f;   // ... and farther
uniform float u_max_n;       // largest near blur radius (px)
uniform float u_max_f;       // largest far blur radius (px)
uniform int u_taps;
uniform int u_debug;         // 1: show the CoC (red near, blue far, black sharp)
in vec2 v_uv;
out vec4 f_color;

float lin(float d) {
    float z = d * 2.0 - 1.0;
    if (u_ortho == 1) return (z * (u_far - u_near) + (u_far + u_near)) * 0.5;
    return 2.0 * u_near * u_far / (u_far + u_near - z * (u_far - u_near));
}
float coc(float dist) {  // signed px: < 0 nearer than the focal band, > 0 farther
    float dz = dist - u_focus;
    if (abs(dz) <= u_range) return 0.0;
    if (dz > 0.0) return clamp((dz - u_range) / max(u_falloff_f, 1e-3), 0.0, 1.0) * u_max_f;
    return -clamp((-dz - u_range) / max(u_falloff_n, 1e-3), 0.0, 1.0) * u_max_n;
}
void main() {
    ivec2 px = ivec2(gl_FragCoord.xy);
    vec4 centre = texelFetch(u_color, px, 0);
    float zc = lin(texelFetch(u_depth, px, 0).r);
    float cc = coc(zc);
    if (u_debug == 1) {
        f_color = vec4(max(-cc, 0.0) / max(u_max_n, 1e-3), 0.0, max(cc, 0.0) / max(u_max_f, 1e-3), 1.0);
        return;
    }
    float reach = max(u_max_n, u_max_f);
    if (reach < 0.5) { f_color = centre; return; }   // no blur at all: exactly the world's own pixels
    vec3 sum = centre.rgb;
    float wsum = 1.0;
    const float GOLDEN = 2.39996323;
    for (int i = 0; i < u_taps; ++i) {
        float r = reach * sqrt((float(i) + 0.5) / float(u_taps));
        float a = float(i) * GOLDEN;
        ivec2 d = ivec2(round(vec2(cos(a), sin(a)) * r));
        float dist = length(vec2(d));                                    // the offset actually read, in pixels
        if (dist < 0.5) continue;                                        // (the centre is already counted)
        ivec2 q = clamp(px + d, ivec2(0), textureSize(u_color, 0) - 1);
        float zs = lin(texelFetch(u_depth, q, 0).r);
        float cs = abs(coc(zs));
        float w = clamp(cs - dist + 1.0, 0.0, 1.0);                      // the sample's blur reaches here
        if (zs > zc + 0.05) w *= clamp(abs(cc) - dist + 1.0, 0.0, 1.0);  // behind: only within our own blur
        sum += texelFetch(u_color, q, 0).rgb * w;
        wsum += w;
    }
    f_color = vec4(sum / wsum, centre.a);
}
"""

VERTEX = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() { v_uv = in_vert * 0.5 + 0.5; gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

PRESETS: dict[str, dict[str, float] | None] = {
    "off": None,
    "subtle": {"range": 2.5, "falloff_n": 10.0, "falloff_f": 10.0, "max_n": 2.5, "max_f": 2.5, "taps": 24},
    "miniature": {"range": 1.0, "falloff_n": 5.0, "falloff_f": 5.0, "max_n": 6.0, "max_f": 6.0, "taps": 48},
}


class DofPass:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.program = ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        from arcade.gl import BufferDescription

        self.buffer = ctx.buffer(data=array("f", [-1, -1, 1, -1, -1, 1, 1, 1]).tobytes())
        self.quad = ctx.geometry([BufferDescription(self.buffer, "2f", ["in_vert"])], mode=ctx.TRIANGLE_STRIP)
        self.query = ctx.query(samples=False, time=True, primitives=False)
        self.last_ns: int | None = None

    def objects(self) -> list[Any]:
        return [self.program, self.quad, self.query]

    def render(self, colour: Any, depth: Any, camera: Any, params: dict[str, float], *, debug: bool = False,
               focus: float | None = None) -> None:
        p = self.program
        w, h = colour.size
        p["u_color"], p["u_depth"] = 0, 1
        p["u_near"], p["u_far"] = 0.1, 500.0  # (engine.hd2d.renderer.Camera.view_projection)
        p["u_ortho"] = 1 if camera.ortho else 0
        p["u_focus"] = float(camera.distance if focus is None else focus)  # the followed target is at this distance
        p["u_range"], p["u_falloff_n"], p["u_falloff_f"] = params["range"], params["falloff_n"], params["falloff_f"]
        p["u_max_n"], p["u_max_f"], p["u_taps"] = params["max_n"], params["max_f"], int(params["taps"])
        p["u_debug"] = 1 if debug else 0
        colour.use(0)
        depth.use(1)
        with self.ctx.enabled_only():
            with self.query:
                self.quad.render(p)
        self.last_ns = self.query.time_elapsed


def linear_depth(d: Any, ortho: bool, near: float = 0.1, far: float = 500.0) -> Any:
    z = d * 2.0 - 1.0
    if ortho:
        return (z * (far - near) + (far + near)) * 0.5
    return 2.0 * near * far / (far + near - z * (far - near))
