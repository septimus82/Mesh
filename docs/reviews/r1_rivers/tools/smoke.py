import math
import sys
import time

sys.path.insert(0, r"D:\Games\Mesh-rivers")
from engine.hd2d.river import RiverError, parse_rivers, ribbon, vertices  # noqa: E402

P = 32.0


def r(pts, rid="s", **kw):
    return {"id": rid, "points": [[x * P, y * P, w * P, lv * P] for x, y, w, lv in pts], **kw}


CASES = {
    "lakeside": r([(23.75, 29.06, 2.25, 0), (26.88, 27.5, 2.25, 0), (30.0, 26.25, 2.0, -0.3), (32.5, 26.41, 2.0, -0.6),
                   (34.38, 26.56, 2.25, -0.8), (36.25, 27.19, 2.75, -0.85), (38.44, 28.28, 3.5, -0.9)]),
    "gentle_s": r([(2, 10, 3, 0), (14, 6, 3, 0), (26, 12, 3.5, 0), (38, 8, 4, 0)]),
    "hairpin_narrow_roomy": r([(0, 0, 0.8, 0), (8, 0, 0.8, 0), (11, 2.5, 0.8, 0), (8, 5, 0.8, 0), (0, 5, 0.8, 0)]),
    "hairpin_wide": r([(5, 5, 3, 0), (10, 5, 3, 0), (10.6, 6, 3, 0), (5, 7, 3, 0)]),
    "loop": r([(2, 2, 1.5, 0), (10, 2, 1.5, 0), (10, 8, 1.5, 0), (4, 8, 1.5, 0), (6, 0, 1.5, 0)]),
    "uphill_points": r([(0, 0, 2, 0), (5, 0, 2, 0.5)]),
    "near_touch_parallel": r([(0, 0, 1.0, 0), (12, 0, 1.0, 0), (16, 0.55, 1.0, 0), (16, 1.6, 1.0, 0), (12, 2.1, 1.0, 0),
                              (0, 2.1, 1.0, 0)]),
    "wide_s": r([(2, 10, 6, 0), (12, 4, 6, 0), (24, 14, 7, 0), (36, 6, 8, 0)]),
}
for name, raw in CASES.items():
    t = time.perf_counter()
    try:
        out = parse_rivers([raw])
        rb = ribbon(out[0])
        print(f"OK  {name}: {rb.length_m:.2f} m, {len(rb.u)} samples, {(time.perf_counter() - t) * 1000:.1f} ms")
    except RiverError as e:
        print(f"REF {name}: {e} ({(time.perf_counter() - t) * 1000:.1f} ms)")
long = r([(i * 5.0, 20 + 8 * math.sin(i * 0.7), 3 + (i % 5) * 0.5, -i * 0.05) for i in range(40)])
try:
    t = time.perf_counter()
    rv = parse_rivers([long])
    d, idx = vertices(rv, 0.035)
    print("long", round(ribbon(rv[0]).length_m, 1), "m", len(d) // 21, "verts", len(idx) // 3, "tris",
          round((time.perf_counter() - t) * 1000, 1), "ms (parse+check twice + pack)")
except RiverError as e:
    print("REF long", e)
two = [r([(0, 0, 2, 0), (20, 0, 2, 0)], "a"), r([(10, -5, 2, 0), (10, 5, 2, 0)], "b")]
try:
    parse_rivers(two)
    print("OK crossing rivers (wrong)")
except RiverError as e:
    print("REF crossing rivers:", e)
