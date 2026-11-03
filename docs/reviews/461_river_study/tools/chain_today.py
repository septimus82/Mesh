"""#461 scratch experiment (no engine change): the best "stream" today's water can make: a chain of rotated
rectangular water bodies along a curved course, each at the ground's height there (read from the live terrain),
made with the engine's own ops (place_blank + set_water), in a NEW scene file of the scratch Lakeside copy.

    python chain_today.py [--overlap]   (writes lakeside_stream_chain.json; captures are taken separately)
"""
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh")
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg")})
PROJECT = M17 / "projects" / "lakeside"
SCENES = PROJECT / "packs" / "core_regions" / "scenes"
# the course (px): west meadow -> under the existing footbridge (1100.8, 848) -> the lake's inlet
COURSE = [(760.0, 930.0), (860.0, 880.0), (960.0, 840.0), (1040.0, 845.0), (1100.0, 850.0), (1160.0, 870.0),
          (1230.0, 905.0)]
WIDTH = 72.0  # px (2.25 m)
OFFSET = float(sys.argv[1]) if len(sys.argv) > 1 else -3.0  # px above (+) or below (-) the ground


def heights() -> list[float]:
    import hd2d_demo

    game = hd2d_demo.HiddenGame(PROJECT, size=(640, 360))
    try:
        game.load("packs/core_regions/scenes/lakeside.json")
        terrain = game.window.hd2d_renderer.terrain
        out = []
        for i in range(len(COURSE) - 1):
            (x0, y0), (x1, y1) = COURSE[i], COURSE[i + 1]
            samples = [terrain.surface_at(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) for t in (0.0, 0.5, 1.0)]
            out.append(min(s[0] for s in samples if s is not None))
        return out
    finally:
        game.close()


def main() -> None:
    from engine import project_ops as ops

    levels = heights()
    scene = json.loads((SCENES / "lakeside.json").read_text(encoding="utf-8"))
    pieces = []
    for i in range(len(COURSE) - 1):
        (x0, y0), (x1, y1) = COURSE[i], COURSE[i + 1]
        length = math.hypot(x1 - x0, y1 - y0) + 16.0  # (a little overlap, or there are gaps where they turn)
        scene, eid = ops.place_blank(scene, "lakeside", f"Stream {i + 1}", (x0 + x1) / 2, (y0 + y1) / 2)
        scene = ops.set_water(scene, eid, preset="natural_pond", shape="rect", width=round(length), height=WIDTH,
                              rotation=round(math.degrees(math.atan2(y1 - y0, x1 - x0)), 1))
        scene = ops.set_entity_fields(scene, eid, elevation=round(levels[i] + OFFSET, 2))  # relative to the ground there
        pieces.append({"id": eid, "length_px": round(length), "rotation": round(math.degrees(math.atan2(y1 - y0, x1 - x0)), 1),
                       "level_px": round(levels[i] + OFFSET, 2)})
    (SCENES / f"lakeside_stream_chain{'_above' if OFFSET > 0 else ''}.json").write_text(json.dumps(scene), encoding="utf-8")
    print(json.dumps({"pieces": pieces}, indent=1))


if __name__ == "__main__":
    main()
