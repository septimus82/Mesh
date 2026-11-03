"""#461 R1 evidence: rivers in the HD-2D starter village (hidden windows only).

    py -3.13 tooling/r1_river_study.py look OUT      # the two rivers, flowing and still, and their frame cost

The test village: a project from the HD-2D RPG template whose north path (the paving under the bridge) gives way to
a stream flowing north under the bridge, with a second stream flowing east south of the village road. Each bed is
sculpted first with the existing terrain op (``sculpt_terrain_stroke``, "flatten": R1 doesn't carve), then the river
is added with ``project_ops.add_river``. Everything is measured from the renderer's own frames: where a river's
course lands on screen (its camera's view-projection), and how its pattern moves between two moments.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PX = 32.0
# [x, y, width, level] px, upstream to downstream
NORTH = [[640, 430, 72, -6.0], [652, 600, 72, -7.0], [640, 768, 72, -8.0], [610, 930, 76, -9.0], [600, 1080, 80, -10.0]]
EAST = [[150, 110, 64, -5.0], [300, 80, 64, -6.0], [430, 105, 68, -7.0], [560, 90, 72, -8.0]]
BED_BELOW = 12.0  # px the flattened bed lies under the water


def _dabs(points: list[list[float]], step: float = 6.0) -> list[list[float]]:
    out = []
    for a, b in zip(points, points[1:]):
        n = max(1, round(math.dist(a[:2], b[:2]) / step))
        out += [[a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n, 1.0] for k in range(n)]
    return out


def make_project(out: Path, name: str, *, flow: float = 1.2, rivers: bool = True) -> Path:
    """The village with its two stream beds; with ``rivers``, the streams in them (flowing at ``flow`` m/s)."""
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    hd2d = scene["settings"]["hd2d"]
    hd2d["structures"] = [s for s in hd2d["structures"] if not s["id"].startswith("path_north")]
    for course in (NORTH, EAST):
        for a, b in zip(course, course[1:]):
            scene = ops.sculpt_terrain_stroke(scene, "flatten", _dabs([a, b]), radius=a[2] / 2 + 4,
                                              target=b[3] - BED_BELOW)
    if rivers:
        scene = ops.add_river(scene, "north", NORTH, flow=flow)
        scene = ops.add_river(scene, "east", EAST, flow=flow)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def frame(game: HiddenGame, target: tuple[float, float, float], water_time: float) -> Any:
    """The renderer's frame (an RGB image) looking at ``target`` (m) with the water's clock at ``water_time``."""
    from PIL import Image

    hd = game.window.hd2d_renderer
    hd.camera.target = target
    hd._camera_ready = True
    game.window.water_time = water_time
    return Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def to_screen(game: HiddenGame, p: tuple[float, float, float]) -> tuple[float, float] | None:
    """Where a world point (m) lands in the last frame (pixels, top-left origin), or None if off it."""
    vp = game.window.hd2d_renderer.last_vp
    c = [sum(vp[r][k] * v for k, v in enumerate((*p, 1.0))) for r in range(4)]
    if c[3] <= 1e-6:
        return None
    x, y = (c[0] / c[3] * 0.5 + 0.5) * study.SIZE[0], (0.5 - c[1] / c[3] * 0.5) * study.SIZE[1]
    return (x, y) if 0 <= x < study.SIZE[0] and 0 <= y < study.SIZE[1] else None


def course(game: HiddenGame, river_id: str, offset_m: float = 0.0) -> list[tuple[float, float, float]]:
    """The river's course (m) every texel (1/32 m) downstream, ``offset_m`` to the right of its middle."""
    from engine.hd2d.river import ribbon

    river = next(r for r in game.window.hd2d_renderer.settings.rivers if r.id == river_id)
    rib = ribbon(river)
    out = []
    for k in range(len(rib.centre) - 1):
        (x0, y0), (x1, y1) = rib.centre[k], rib.centre[k + 1]
        tx, ty = rib.tangent[k]
        for s in range(8):  # a sample is a quarter metre: 8 texels
            f = s / 8
            out.append((x0 + (x1 - x0) * f + ty * offset_m, y0 + (y1 - y0) * f - tx * offset_m, rib.level[k]))
    return out


def profile(game: HiddenGame, image: Any, points: list[tuple[float, float, float]]) -> list[float | None]:
    """The brightness of the frame at each point (None: off screen)."""
    out: list[float | None] = []
    for p in points:
        at = to_screen(game, p)
        if at is None:
            out.append(None)
            continue
        r, g, b = image.getpixel((int(at[0]), int(at[1])))
        out.append(0.299 * r + 0.587 * g + 0.114 * b)
    return out


def shift(lanes: list[tuple[list[float | None], list[float | None]]], reach: int = 24) -> tuple[int, float]:
    """How far (texels, + downstream) a pattern moved: over several lanes along the river, each ``(before, after)``,
    the best-correlated shift and that correlation (of the detail: each less its 1 m running mean)."""
    lanes = [(_detail(a), _detail(b)) for a, b in lanes]
    best = (0, -2.0)
    for s in range(-reach, reach + 1):
        pairs = [(a, b) for before, after in lanes for a, b in zip(before[max(0, -s):], after[max(0, s):])
                 if a is not None and b is not None]
        if len(pairs) < 40:
            continue
        ma, mb = sum(a for a, _ in pairs) / len(pairs), sum(b for _, b in pairs) / len(pairs)
        da = math.sqrt(sum((a - ma) ** 2 for a, _ in pairs)) or 1.0
        db = math.sqrt(sum((b - mb) ** 2 for _, b in pairs)) or 1.0
        corr = sum((a - ma) * (b - mb) for a, b in pairs) / (da * db)
        if corr > best[1]:
            best = (s, corr)
    return best


def drift(game: HiddenGame, river_id: str, target: tuple[float, float, float], at: float,
          dt: float = 0.25) -> tuple[int, float]:
    """How far the river's surface moved downstream (texels) in ``dt`` seconds at ``at``: what changed from at - dt
    to at against what changed from at to at + dt, along lanes across its middle (what stands still, the mirror of
    a bridge or the bed's light, changes not at all and drops out)."""
    frames = [frame(game, target, at + k * dt) for k in (-1, 0, 1)]
    lanes = []
    for offset in (-0.5, -0.375, -0.25, -0.125, 0.0, 0.125, 0.25, 0.375, 0.5):
        line = course(game, river_id, offset)
        p0, p1, p2 = (profile(game, f, line) for f in frames)
        d0 = [None if a is None or b is None else b - a for a, b in zip(p0, p1)]
        d1 = [None if a is None or b is None else b - a for a, b in zip(p1, p2)]
        lanes.append((d0, d1))
    return shift(lanes)


def _detail(values: list[float | None], reach: int = 16) -> list[float | None]:
    out: list[float | None] = []
    for i, v in enumerate(values):
        near = [w for w in values[max(0, i - reach):i + reach + 1] if w is not None]
        out.append(None if v is None else v - sum(near) / len(near))
    return out


def centre_of(points: list[list[float]]) -> tuple[float, float, float]:
    mid = points[len(points) // 2]
    return (mid[0] / PX, mid[1] / PX, mid[3] / PX)


def look(out: Path) -> dict[str, Any]:
    """Each river flowing (two moments a quarter second apart) and still, its pattern's measured drift, the frame
    cost with and without the rivers, and the GL objects they hold."""
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for name, flow in (("flowing", 1.2), ("still", 0.0)):
        game = HiddenGame(make_project(out, name, flow=flow), size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(3)
            for rid, points in (("north", NORTH), ("east", EAST)):
                target = centre_of(points)
                a, b = frame(game, target, 10.0), frame(game, target, 10.25)
                a.save(out / f"{name}_{rid}_t10.00.png")
                b.save(out / f"{name}_{rid}_t10.25.png")
                report[f"{name}_{rid}"] = {"drift_texels": drift(game, rid, target, 10.25),
                                           "frames_identical": a.tobytes() == b.tobytes()}
            report[f"{name}_stats"] = {k: v for k, v in game.window.hd2d_renderer.stats().items()
                                       if k in ("rivers", "water_bytes", "draw_calls", "triangles")}
            report[f"{name}_gl"] = _gl_counts(game.window.ctx)
        finally:
            game.close()
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def frame_ms(game: HiddenGame, target: tuple[float, float, float], frames: int = 60) -> dict[str, float]:
    """Whole-frame time (ms, read back: the GPU's work included) looking at ``target``, the water's clock running."""
    times = []
    for i in range(frames):
        t = time.perf_counter()
        frame(game, target, 10.0 + i / 60)
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {"median": round(times[len(times) // 2], 2), "p90": round(times[int(len(times) * 0.9)], 2)}


def cost(out: Path) -> dict[str, Any]:
    """Frame time looking at the north river under the bridge, with the rivers and with their beds only."""
    report = {}
    for name, rivers in (("rivers", True), ("beds_only", False)):
        game = HiddenGame(make_project(out, f"cost_{name}", rivers=rivers), size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(3)
            frame_ms(game, centre_of(NORTH), 10)  # (warm)
            report[name] = frame_ms(game, centre_of(NORTH), 120)
        finally:
            game.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=("look",))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report = look(args.out)
    report["cost"] = cost(args.out)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
