"""R1 demo scene (scratch copy of Lakeside only): the lake's arm under the footbridge replaced by a stream from the
west meadow, through a bed sculpted with the existing terrain op (sculpt_terrain_stroke "flatten"), under the
bridge, into the lake. Written with the engine's own ops; new scene files, listed in the scratch world so Studio
can open them.

    python lakeside_river.py   -> lakeside_river.json (flow 1.2 m/s) and lakeside_river_still.json (flow 0)
"""
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("M17_REPO", r"D:\Games\Mesh-rivers"))
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_guard import inside_scratch  # noqa: E402

M17 = inside_scratch(M17)  # (never a mis-converted path such as D:\c\...)
sys.path[:0] = [str(REPO)]
PROJECT = M17 / "projects" / "lakeside"
SCENES = PROJECT / "packs" / "core_regions" / "scenes"
WORLD = PROJECT / "packs" / "core_regions" / "worlds" / "main.json"

# the course (px), upstream to downstream: [x, y, width, level]; the level falls 0.5 px .. 1.5 px a point
POINTS = [[700, 960, 56, -4.0], [800, 930, 60, -5.0], [900, 905, 64, -6.0], [990, 870, 66, -7.5],
          [1060, 852, 68, -9.0], [1130, 860, 70, -10.5], [1190, 890, 74, -12.0], [1250, 935, 84, -13.25]]
BED_BELOW = 14.0  # px the sculpted bed lies under the water's level where it is flattened
BED_RADIUS = 30.0  # px: the flatten brush (the ribbon's half width is 28-42 px)


def bed_dabs(points: list[list[float]], step: float = 6.0) -> list[list[float]]:
    out = []
    for a, b in zip(points, points[1:]):
        n = max(1, round(math.dist(a[:2], b[:2]) / step))
        for k in range(n):
            f = k / n
            out.append([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, 1.0])
    return out


def main() -> None:
    from engine import project_ops as ops

    scene = json.loads((SCENES / "lakeside.json").read_text(encoding="utf-8"))
    arm = next(e for e in scene["entities"] if e.get("name") == "Puddle 2")  # the lake's arm under the bridge
    scene = ops.remove_entity(scene, arm["id"])
    # the bed: flattened along the meadow part only (east of x 1040 the old arm's hollow is already deeper)
    meadow = [p for p in POINTS if p[0] <= 1060]
    for a, b in zip(meadow, meadow[1:]):
        scene = ops.sculpt_terrain_stroke(scene, "flatten", bed_dabs([a, b]), radius=BED_RADIUS,
                                          target=b[3] - BED_BELOW)
    # the grass, flowers and reeds along it removed with the scatter brush ("remove", all its decoration), as a
    # creator would in Studio (R1 doesn't clear scatter by itself)
    scene = ops.scatter_stroke(scene, "all", [[x, y] for x, y, _s in bed_dabs(POINTS, 12.0)], radius=44.0,
                               mode="remove")
    for name, flow in (("lakeside_river", 1.2), ("lakeside_river_still", 0.0)):
        out = ops.add_river(scene, "brook", POINTS, flow=flow)
        (SCENES / f"{name}.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(name, json.dumps(ops.rivers(out))[:300])
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    for name, label in (("lakeside_river", "Lakeside River"), ("lakeside_river_still", "Lakeside River (still)")):
        world["scenes"][name] = {"label": label, "path": f"packs/core_regions/scenes/{name}.json", "tags": []}
    WORLD.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
