"""A model's preview picture, drawn on the CPU (Milestone 16 Stage 5B): its own textured triangles, z-buffered,
from above and to one side (a three-quarter view like the editor's), lit by the default sun.

Made once when a model is imported or reimported and saved as a PNG, so Mesh Studio's model browser draws
pictures, not 3D scenes, and tests can check previews without OpenGL. Textures are sampled nearest, as pixel art
should be; collision is never drawn (it isn't in ``Model.parts``).
"""

from __future__ import annotations

import math
from typing import Any

from PIL import Image

from engine.hd2d.glb import Model

SIZE = (160, 120)
_SUN = (-0.45, -0.55, 0.70)


def render(model: Model, size: tuple[int, int] = SIZE, *, yaw: float = -35.0, pitch: float = 32.0) -> Image.Image:
    """``model`` seen from the south-south-west, ``pitch`` degrees down, fitted to ``size`` (transparent around it)."""
    w, h = size
    cy, sy, cp, sp = math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    forward = (sy * cp, cy * cp, -sp)  # looking north (turned by yaw) and down
    right = (cy, -sy, 0.0)
    up = (right[1] * forward[2] - right[2] * forward[1], right[2] * forward[0] - right[0] * forward[2],
          right[0] * forward[1] - right[1] * forward[0])
    sun_len = math.sqrt(sum(c * c for c in _SUN))
    sun = tuple(c / sun_len for c in _SUN)

    def project(x: float, y: float, z: float) -> tuple[float, float, float]:
        return (x * right[0] + y * right[1] + z * right[2], x * up[0] + y * up[1] + z * up[2],
                x * forward[0] + y * forward[1] + z * forward[2])

    triangles: list[tuple[list[tuple[float, ...]], Any, tuple[int, int], bool]] = []
    lo_x = lo_y = math.inf
    hi_x = hi_y = -math.inf
    for part in model.parts:
        v, idx = part.vertices, part.indices
        image = part.material.image
        texels = image.convert("RGBA").load() if image is not None else None
        tsize = image.size if image is not None else (1, 1)
        for t in range(0, len(idx) - 2, 3):
            corners: list[tuple[float, ...]] = []
            for i in idx[t:t + 3]:
                b = i * 8
                sx, s_y, depth = project(v[b], v[b + 1], v[b + 2])
                corners.append((sx, s_y, depth, v[b + 6], v[b + 7], v[b + 3], v[b + 4], v[b + 5]))
                lo_x, hi_x, lo_y, hi_y = min(lo_x, sx), max(hi_x, sx), min(lo_y, s_y), max(hi_y, s_y)
            triangles.append((corners, texels, tsize, part.material.repeat))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if not triangles:
        return out
    scale = 0.9 * min(w / max(hi_x - lo_x, 1e-6), h / max(hi_y - lo_y, 1e-6))
    ox, oy = w / 2 - scale * (lo_x + hi_x) / 2, h / 2 + scale * (lo_y + hi_y) / 2
    pixels: Any = out.load()
    zbuf = [math.inf] * (w * h)
    for corners, texels, (tw, th), repeat in triangles:
        pts = [(ox + scale * c[0], oy - scale * c[1]) for c in corners]
        (x0, y0), (x1, y1), (x2, y2) = pts
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        n = [sum(c[5 + k] for c in corners) / 3 for k in range(3)]
        n_len = math.sqrt(sum(c * c for c in n)) or 1.0
        light = 0.55 + 0.45 * max(0.0, sum(n[k] / n_len * sun[k] for k in range(3)))
        for py in range(max(0, int(min(y0, y1, y2))), min(h - 1, int(max(y0, y1, y2))) + 1):
            for px in range(max(0, int(min(x0, x1, x2))), min(w - 1, int(max(x0, x1, x2))) + 1):
                cx, cy_ = px + 0.5, py + 0.5
                a = ((x1 - cx) * (y2 - cy_) - (x2 - cx) * (y1 - cy_)) / area
                b = ((x2 - cx) * (y0 - cy_) - (x0 - cx) * (y2 - cy_)) / area
                c = 1.0 - a - b
                if a < 0 or b < 0 or c < 0:
                    continue
                depth = a * corners[0][2] + b * corners[1][2] + c * corners[2][2]
                at = py * w + px
                if depth >= zbuf[at]:
                    continue
                if texels is None:
                    r, g, bl, al = 200, 200, 200, 255
                else:
                    u = a * corners[0][3] + b * corners[1][3] + c * corners[2][3]
                    vv = a * corners[0][4] + b * corners[1][4] + c * corners[2][4]
                    if repeat:
                        u, vv = u % 1.0, vv % 1.0
                    tx, ty = min(tw - 1, max(0, int(u * tw))), min(th - 1, max(0, int(vv * th)))
                    r, g, bl, al = texels[tx, ty]
                if al < 128:
                    continue
                zbuf[at] = depth
                pixels[px, py] = (min(255, int(r * light)), min(255, int(g * light)), min(255, int(bl * light)), 255)
    return out
