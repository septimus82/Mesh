"""#461 GEOMETRY PROTOTYPE (scratch, pure Python, not engine code; its pictures are diagrams, not game renders).

A river as control points (x, y, width; metres) -> a centripetal Catmull-Rom centreline through every point, sampled
every STEP metres of arc length -> a ribbon: left/right banks at +-width/2 along the local normal, with per-vertex
``u`` (metres downstream, the flow coordinate) and ``v`` (-1 left bank .. +1 right bank). V1's refusal checks:
a bend tighter than the river is wide (the inner bank would fold over itself), and crossings (the centreline or a
bank meeting itself). Also times a long river's rebuild.
"""
import json
import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

STEP = 0.25  # m between samples (8 px: the world's 32 px/m grid)
MIN_TURN_RADIUS = 0.6  # the tightest bend allowed, as a multiple of the half width at that point


def catmull_rom(points, steps_per_span=32):
    """Centripetal Catmull-Rom through every point (ends repeated): no cusps or self-loops within a span."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]

        def tj(ti, a, b):
            return ti + max(1e-6, math.dist(a[:2], b[:2])) ** 0.5

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        for s in range(steps_per_span):
            t = t1 + (t2 - t1) * s / steps_per_span

            def lerp(a, b, ta, tb):
                if tb - ta < 1e-9:
                    return a
                return tuple(((tb - t) * a[k] + (t - ta) * b[k]) / (tb - ta) for k in range(len(a)))

            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    out.append(tuple(points[-1]))
    return out


def resample(curve, step=STEP):
    """Even spacing along the arc: (x, y, width, u)."""
    out = [(curve[0][0], curve[0][1], curve[0][2], 0.0)]
    carried, u = 0.0, 0.0
    for a, b in zip(curve, curve[1:]):
        seg = math.dist(a[:2], b[:2])
        d = step - carried
        while d <= seg:
            f = d / seg
            u += step
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, u))
            d += step
        carried = seg - (d - step)
    end = curve[-1]
    out.append((end[0], end[1], end[2], u + carried))
    return out


def ribbon(samples):
    """Banks and the per-vertex flow frame; problems found (V1 refuses them)."""
    left, right, problems = [], [], []
    for i, (x, y, w, u) in enumerate(samples):
        a, b = samples[max(0, i - 1)], samples[min(len(samples) - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        n = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / n, tx / n
        left.append((x + nx * w / 2, y + ny * w / 2, u, -1.0))
        right.append((x - nx * w / 2, y - ny * w / 2, u, 1.0))
        if 0 < i < len(samples) - 1:  # turning radius from three samples
            ax, ay, bx, by = x - a[0], y - a[1], b[0] - x, b[1] - y
            turn = abs(math.atan2(ax * by - ay * bx, ax * bx + ay * by))
            arc = (math.hypot(ax, ay) + math.hypot(bx, by)) / 2
            radius = arc / turn if turn > 1e-9 else math.inf
            if radius < MIN_TURN_RADIUS * w / 2:
                problems.append(("bend too tight", round(x, 2), round(y, 2), round(radius, 2), round(w, 2)))
    for name, line in (("centreline", [(s[0], s[1]) for s in samples]), ("left bank", left), ("right bank", right)):
        hit = _self_crossing(line)
        if hit:
            problems.append((f"{name} crosses itself", *hit))
    return left, right, problems


def _self_crossing(line):
    """The first pair of non-adjacent segments that cross (a 1 m grid of buckets keeps it near-linear)."""
    buckets = {}
    for i in range(len(line) - 1):
        (x0, y0), (x1, y1) = line[i][:2], line[i + 1][:2]
        for cx in range(int(math.floor(min(x0, x1))), int(math.floor(max(x0, x1))) + 1):
            for cy in range(int(math.floor(min(y0, y1))), int(math.floor(max(y0, y1))) + 1):
                for j in buckets.get((cx, cy), ()):
                    if i - j > 2 and _cross(line[i][:2], line[i + 1][:2], line[j][:2], line[j + 1][:2]):
                        return (round(x0, 2), round(y0, 2))
                buckets.setdefault((cx, cy), []).append(i)
    return None


def _cross(p1, p2, p3, p4):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = orient(p3, p4, p1), orient(p3, p4, p2), orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def build(points):
    t = time.perf_counter()
    samples = resample(catmull_rom(points))
    left, right, problems = ribbon(samples)
    ms = (time.perf_counter() - t) * 1000
    return {"samples": samples, "left": left, "right": right, "problems": problems, "ms": round(ms, 2),
            "vertices": 2 * len(samples), "triangles": 2 * (len(samples) - 1),
            "length_m": round(samples[-1][3], 2)}


CASES = {
    # the scratch stream's course (Lakeside px / 32), 2.25 m wide, widening to 3.5 m at the lake
    "lakeside_stream": [(23.75, 29.06, 2.25), (26.88, 27.5, 2.25), (30.0, 26.25, 2.0), (32.5, 26.41, 2.0),
                        (34.38, 26.56, 2.25), (36.25, 27.19, 2.75), (38.44, 28.28, 3.5)],
    "hairpin_too_tight": [(5.0, 5.0, 3.0), (10.0, 5.0, 3.0), (10.6, 6.0, 3.0), (5.0, 7.0, 3.0)],
    "self_crossing_loop": [(2.0, 2.0, 1.5), (10.0, 2.0, 1.5), (10.0, 8.0, 1.5), (4.0, 8.0, 1.5), (6.0, 0.0, 1.5)],
    "gentle_s_wide": [(2.0, 10.0, 6.0), (12.0, 4.0, 6.0), (24.0, 14.0, 7.0), (36.0, 6.0, 8.0)],
}


def diagram(name, result, out, scale=24, pad=2.0):
    xs = [p[0] for p in result["left"] + result["right"]]
    ys = [p[1] for p in result["left"] + result["right"]]
    x0, y0 = min(xs) - pad, min(ys) - pad
    w, h = int((max(xs) - x0 + pad) * scale), int((max(ys) - y0 + pad) * scale)
    img = Image.new("RGB", (max(w, 200), max(h, 120) + 30), (245, 245, 240))
    d = ImageDraw.Draw(img)

    def P(p):
        return ((p[0] - x0) * scale, h - (p[1] - y0) * scale)
    L, R = result["left"], result["right"]
    for i in range(len(L) - 1):
        quad = [P(L[i]), P(L[i + 1]), P(R[i + 1]), P(R[i])]
        shade = 150 + int(80 * ((L[i][2] % 2.0) / 2.0))  # bands every 2 m of u: the downstream coordinate
        d.polygon(quad, fill=(60, 110, shade), outline=(40, 70, 110))
    d.line([P(s) for s in result["samples"]], fill=(255, 255, 255), width=1)
    for pr in result["problems"]:
        cx, cy = P(pr[1:3])
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=(220, 30, 30), width=2)
    label = (f"{name}: DIAGRAM from the scratch geometry prototype (not a game render) - {result['length_m']} m, "
             f"{result['triangles']} tris, {result['ms']} ms, problems: {len(result['problems'])}")
    d.text((4, h + 8), label, fill=(0, 0, 0))
    img.save(out)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, pts in CASES.items():
        r = build(pts)
        diagram(name, r, out / f"G_{name}.png")
        report[name] = {k: r[k] for k in ("length_m", "vertices", "triangles", "ms")} | {"problems": r["problems"][:4]}
    # a long river: 40 control points over ~200 m, timed (what an edit would rebuild)
    longpts = [(i * 5.0, 20.0 + 8.0 * math.sin(i * 0.7), 3.0 + (i % 5) * 0.5) for i in range(40)]
    r = build(longpts)
    report["long_200m"] = {k: r[k] for k in ("length_m", "vertices", "triangles", "ms")} | {"problems": len(r["problems"])}
    print(json.dumps(report, indent=1))
