"""Turn the vendored Lucide icons (assets/icons/lucide/*.svg, ISC licence) into the PNGs Mesh Studio draws.

Mesh has no SVG renderer, and fetching one for a few dozen line icons isn't worth it. Lucide icons are 24-unit
strokes (2 units wide, round caps and joins) built from paths, circles and rectangles, which this draws with
Pillow at 8x and scales down. The output is white with soft edges; Studio tints it per button state.

    py -3.13 tooling/make_icons.py        writes assets/icons/<name>_16.png and _32.png
"""

from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
SOURCE, OUT = REPO / "assets" / "icons" / "lucide", REPO / "assets" / "icons"
SIZES, SUPER, STROKE = (16, 32), 8, 2.0
Point = tuple[float, float]
_TOKEN = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _arc(p0: Point, rx: float, ry: float, phi_deg: float, large: bool, sweep: bool, p1: Point) -> list[Point]:
    """Points along an SVG arc (endpoint form, converted to centre form; SVG spec F.6.5)."""
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(phi_deg)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cos * dx + sin * dy, -sin * dx + cos * dy
    rx, ry = abs(rx), abs(ry)
    scale = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    coef = math.sqrt(max(0.0, num / (rx * rx * y1 * y1 + ry * ry * x1 * x1)))
    if large == sweep:
        coef = -coef
    cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx, cy = cos * cx1 - sin * cy1 + (p0[0] + p1[0]) / 2, sin * cx1 + cos * cy1 + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    start = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(4, int(abs(delta) / (math.pi / 16)))
    out = []
    for i in range(1, steps + 1):
        t = start + delta * i / steps
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cos * x - sin * y + cx, sin * x + cos * y + cy))
    return out


def _bezier(points: list[Point], steps: int = 16) -> list[Point]:
    out = []
    for i in range(1, steps + 1):
        t, pts = i / steps, list(points)
        while len(pts) > 1:
            pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(pts, pts[1:])]
        out.append(pts[0])
    return out


def path_lines(d: str) -> list[list[Point]]:
    """A path's subpaths as polylines (closed ones end where they began)."""
    tokens, i = _TOKEN.findall(d), 0
    lines: list[list[Point]] = []
    cur: Point = (0.0, 0.0)
    start: Point = (0.0, 0.0)
    cmd = ""

    def num() -> float:
        nonlocal i
        i += 1
        return float(tokens[i - 1])

    def flag() -> bool:  # arc flags may be packed ("011"): read one digit at a time
        nonlocal i
        token = tokens[i]
        if len(token) > 1 and token[0] in "01":
            tokens[i] = token[1:]
            return bool(token[0] == "1")
        i += 1
        return bool(token == "1")

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd, i = tokens[i], i + 1
        rel = cmd.islower()
        base = cur if rel else (0.0, 0.0)
        c = cmd.upper()
        if c == "M":
            cur = (base[0] + num(), base[1] + num())
            start = cur
            lines.append([cur])
            cmd = "l" if rel else "L"  # further pairs are lines
        elif c == "L":
            cur = (base[0] + num(), base[1] + num())
            lines[-1].append(cur)
        elif c == "H":
            cur = ((cur[0] if rel else 0.0) + num(), cur[1])
            lines[-1].append(cur)
        elif c == "V":
            cur = (cur[0], (cur[1] if rel else 0.0) + num())
            lines[-1].append(cur)
        elif c == "C":
            p1 = (base[0] + num(), base[1] + num())
            p2 = (base[0] + num(), base[1] + num())
            p3 = (base[0] + num(), base[1] + num())
            lines[-1].extend(_bezier([cur, p1, p2, p3]))
            cur = p3
        elif c == "Q":
            p1 = (base[0] + num(), base[1] + num())
            p2 = (base[0] + num(), base[1] + num())
            lines[-1].extend(_bezier([cur, p1, p2]))
            cur = p2
        elif c == "A":
            rx, ry, rot = num(), num(), num()
            large, sweep = flag(), flag()
            end = (base[0] + num(), base[1] + num())
            lines[-1].extend(_arc(cur, rx, ry, rot, large, sweep, end))
            cur = end
        elif c == "Z":
            lines[-1].append(start)
            cur = start
            lines.append([cur])
        else:
            raise ValueError(f"unsupported path command {cmd!r}")
    return [line for line in lines if len(line) > 1 or line]


def element_lines(el: ET.Element) -> list[list[Point]]:
    tag, a = el.tag.split("}")[-1], el.attrib
    if tag == "path":
        return path_lines(a["d"])
    if tag == "circle":
        cx, cy, r = float(a["cx"]), float(a["cy"]), float(a["r"])
        return [[(cx + r * math.cos(t * math.pi / 32), cy + r * math.sin(t * math.pi / 32)) for t in range(65)]]
    if tag == "rect":
        x, y, w, h = (float(a.get(k, 0)) for k in ("x", "y", "width", "height"))
        r = min(float(a.get("rx", a.get("ry", 0))), w / 2, h / 2)
        if not r:
            return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
        pts: list[Point] = []
        for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
            pts += [(cx + r * math.cos(math.radians(a0 + d)), cy + r * math.sin(math.radians(a0 + d))) for d in range(0, 91, 10)]
        return [pts + [pts[0]]]
    return []


def render(svg: Path, size: int) -> Image.Image:
    big = size * SUPER
    k = big / 24.0
    width = STROKE * k
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    for el in ET.parse(svg).getroot().iter():
        for line in element_lines(el):
            pts = [(x * k, y * k) for x, y in line]
            if len(pts) > 1:
                draw.line(pts, fill=255, width=round(width), joint="curve")
            for x, y in pts:  # round caps and joins
                draw.ellipse([x - width / 2, y - width / 2, x + width / 2, y + width / 2], fill=255)
    alpha = mask.resize((size, size), Image.Resampling.LANCZOS)
    icon = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    icon.putalpha(alpha)
    return icon


def main() -> int:
    svgs = sorted(SOURCE.glob("*.svg"))
    for svg in svgs:
        for size in SIZES:
            render(svg, size).save(OUT / f"{svg.stem}_{size}.png")
    print(f"{len(svgs)} icons x {len(SIZES)} sizes -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
