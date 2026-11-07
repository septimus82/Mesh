"""M17-L1 candidate: Lakeside's meadow and daylight composition, made ONLY with Mesh's authoring operations
(engine.project_ops: what Mesh Studio's Scatter, Paint and Light controls record, and what `mesh author` / MCP apply),
from the pristine shipped lakeside.json. Deterministic (fixed seeds): the same input always gives the same output.

    py -3.13 l1_compose.py SOURCE_lakeside.json OUT_lakeside.json

What it does (owner brief, #458 comment 6703738229):
 1. Daylight: the four lamp posts stay; their point lights are switched off (``enabled: false``, Studio's light On
    toggle), so a noon room has no lamp pools and night lighting is one toggle away. The ambient light is untouched.
 2. Trees: the evenly spaced single trees become stands (woods on the hills and at the edges, a group between the
    shop and the pond, a few in the gardens, some singles) with clearings between. Under a stand the meadow is cleared
    and comes back sparser, with bushes: a woodland floor.
 3. A village green: round the houses, shop and crossroads the tall grass is mostly thinned away (a mown look), so
    the short grass near people reads darker and calmer than the long grass of the wild meadow.
 4. Flowers: no longer sprinkled over everything; drifts in the open meadow, clumps along fences and garden fronts
    and the pond's grassy margin; quiet spaces round the paths and the green.
 5. Worn ground: earth trodden in at the doorsteps, the shop front, the crossroads and the bridge's south end.
Nothing else changes: structures, water, terrain heights, paths' existing paint, doors, arrivals, the player, wind,
motion, camera and sun stay exactly as shipped (checked at the end).
"""
import copy
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
from engine import project_ops as ops  # noqa: E402

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
shipped = json.loads(src.read_text(encoding="utf-8"))
doc = copy.deepcopy(shipped)
log = {}


def count(d, kinds=None):
    sc = d["settings"]["hd2d"].get("scatter") or {}
    return sum(len(v) for k, v in sc.items() if kinds is None or k in kinds)


def ring(cx, cy, r, n=6):
    """A closed little loop of dabs round (cx, cy): one stroke covering a disc of about radius r."""
    return [[round(cx + r * math.cos(t)), round(cy + r * math.sin(t))] for t in (i * math.tau / n for i in range(n))] + [[cx, cy]]


# what a clearing stroke takes away: ground cover only (grass, flowers, shrubs). Rocks, reeds and anything else the
# room has are never touched (an "all" stroke would take them too)
COVER = {"grass_tuft": 1.0, "grass_tall": 1.0, "grass_dry": 1.0, "flowers_pink": 1.0, "flowers_yellow": 1.0,
         "bush": 1.0, "bush_berries": 1.0}


def grid(x0, y0, x1, y1, step):
    return [[x, y] for y in range(y0, y1 + 1, step) for x in range(x0, x1 + 1, step)]


# ---- 1. daylight: lamp lights off, the posts kept
for i, light in enumerate(doc["lights"]):
    if light.get("type") != "ambient":
        doc = ops.set_light(doc, i, enabled=False)
log["lamp_lights_disabled"] = sum(1 for lt in doc["lights"] if lt.get("enabled") is False)

# ---- 2. trees: stands and clearings
GROVE = (1150, 590, 1460, 860)  # the shipped grove between the shop and the pond already frames the shore: kept
in_grove = lambda x, y: GROVE[0] <= x <= GROVE[2] and GROVE[1] <= y <= GROVE[3]  # noqa: E731
all_trees = doc["settings"]["hd2d"]["scatter"]["tree_small"]
old_trees = [tuple(r[:2]) for r in all_trees if not in_grove(*r[:2])]
kept = [r for r in all_trees if in_grove(*r[:2])]
doc = ops.set_scatter(doc, {**doc["settings"]["hd2d"]["scatter"], "tree_small": kept})
STANDS = [  # (centre px, radius px, seed): woods on the hills and at the room's edges; trees packed as close as
    # their own spacing allows (3 m), so a stand reads as a wood, not as a thinner field
    ((470, 1300), 300, 11),   # north-west hill wood
    ((1880, 1330), 230, 12),  # north-east wood
    ((110, 760), 170, 13),    # west edge
    ((1960, 230), 130, 14),   # south-east corner
    ((1990, 900), 120, 15),   # east edge
    ((170, 170), 130, 16),    # south-west corner
    ((175, 470), 75, 18),     # west of the cottages (in 8 m chunks that held trees before: no new tree draws)
]
SINGLES = [(900, 1230), (1300, 1430), (880, 1000), (1600, 150), (760, 1450)]
# (each single stands in an 8 m chunk that already held trees in the shipped scene: a tree model draws once per
#  chunk, so a single in a chunk of its own would add a draw call to the views that see it)
# the meadow comes back where the old single trees stood outside the stands (their bare rings filled)
inside = lambda x, y: any((x - c[0]) ** 2 + (y - c[1]) ** 2 < (r + 60) ** 2 for c, r, _s in STANDS)  # noqa: E731
for i, (x, y) in enumerate(old_trees):
    if not inside(x, y):
        doc = ops.scatter_stroke(doc, "Meadow", [[x, y]], radius=56, seed=500 + i)
# trees block walking, and the kit lets them stand on earth: so they keep off the paths. Their dabs keep 100 px from
# any painted earth (a 48 px dab: every trunk at least 52 px, 1.6 m, from a path) and they grow on grass only
from engine.hd2d.terrain import Terrain  # noqa: E402

_paths = Terrain.from_ground(ops._parsed_ground(doc))
EARTH = [(x, y) for y in range(0, 1536, 16) for x in range(0, 2048, 16) if _paths.material_at(x, y) != "grass"]
CLEARINGS = [(400, 1168, 140)]  # the hilltop the hill path climbs to (past its painted end): a clearing, walkable
clear_of_paths = lambda x, y, gap=100: (all((x - ex) ** 2 + (y - ey) ** 2 > gap * gap for ex, ey in EARTH)  # noqa: E731
                                        and all((x - cx) ** 2 + (y - cy) ** 2 > (cr + gap - 52) ** 2
                                                for cx, cy, cr in CLEARINGS))
for (cx, cy), r, seed in STANDS:
    rng = random.Random(seed)  # dabs: a jittered grid over the stand's disc (its edge left irregular)
    area = [[round(cx + x + rng.uniform(-14, 14)), round(cy + y + rng.uniform(-14, 14))]
            for y in range(-r, r + 1, 56) for x in range(-r, r + 1, 56)
            if x * x + y * y <= (r * rng.uniform(0.8, 1.0)) ** 2]
    trees_at = [d for d in area if clear_of_paths(*d)]
    clear = [[cx + x, cy + y] for y in range(-r - 40, r + 41, 40) for x in range(-r - 40, r + 41, 40)
             if x * x + y * y <= (r + 40) ** 2]  # (the whole disc first: one grass tuft left blocks a tree's 1.6 m)
    doc = ops.scatter_stroke(doc, COVER, clear, radius=40, mode="remove", seed=seed)
    doc = ops.scatter_stroke(doc, {"tree_small": 1.0}, trees_at, radius=48, density=0.3, clumping=0.0, seed=seed,
                             on=["grass"])
    doc = ops.scatter_stroke(doc, "Shrubs", area, radius=48, density=0.3, clumping=0.6, seed=seed + 100)
    doc = ops.scatter_stroke(doc, "Meadow", area, radius=48, density=1.0, clumping=0.7, seed=seed + 200)
for i, (x, y) in enumerate(SINGLES):
    assert clear_of_paths(x, y, 80), (x, y)
    doc = ops.scatter_stroke(doc, COVER, [[x, y]], radius=60, mode="remove", seed=300 + i)
    doc = ops.scatter_stroke(doc, {"tree_small": 1.0}, [[x, y]], radius=24, density=2.0, seed=300 + i, on=["grass"])
    doc = ops.scatter_stroke(doc, "Meadow", [[x, y]], radius=64, density=1.6, clumping=0.5, seed=400 + i)
# a tree model draws once per 8 m chunk: no tree in a chunk that held none in the shipped scene (so no view gains a
# draw call); any stand tree that spilled into one is taken away with a small Remove dab on it
TREE_CHUNKS = {(int(r[0] // 256), int(r[1] // 256)) for r in all_trees}
for row in list(doc["settings"]["hd2d"]["scatter"]["tree_small"]):
    if (int(row[0] // 256), int(row[1] // 256)) not in TREE_CHUNKS:
        doc = ops.scatter_stroke(doc, {"tree_small": 1.0}, [[row[0], row[1]]], radius=8, mode="remove", seed=0)
assert all((int(r[0] // 256), int(r[1] // 256)) in TREE_CHUNKS for r in doc["settings"]["hd2d"]["scatter"]["tree_small"])
log["trees"] = [len(all_trees), count(doc, ["tree_small"])]

# ---- 3. trodden path edges: tall grass thinned along the paths (within about 1.3 m of their earth), and a few
#         shrub clumps at the cottages' corners, so paths and houses sit in the meadow instead of on top of it
from engine.hd2d.terrain import Terrain  # noqa: E402

terrain = Terrain.from_ground(ops._parsed_ground(doc))
edges = [[x, y] for y in range(48, 1536, 40) for x in range(48, 2048, 40)
         if terrain.material_at(x, y) == "earth" and (y < 900 or x < 900)]  # (the village's paths, not the pond ring)
doc = ops.scatter_stroke(doc, {"grass_tall": 1.0}, edges, radius=42, mode="thin", share=0.5, seed=21)
for i, (x, y) in enumerate([(500, 700), (720, 690), (470, 300), (650, 300)]):
    doc = ops.scatter_stroke(doc, "Meadow", [[x, y]], radius=36, mode="thin", share=0.7, seed=40 + i)
    doc = ops.scatter_stroke(doc, "Shrubs", [[x, y]], radius=36, density=0.9, clumping=0.3, seed=50 + i)
log["path_edge_dabs"] = len(edges)
log["grass_tall"] = [len(shipped["settings"]["hd2d"]["scatter"]["grass_tall"]), count(doc, ["grass_tall"])]
log["bushes"] = [sum(len(shipped["settings"]["hd2d"]["scatter"][k]) for k in ("bush", "bush_berries")),
                 count(doc, ["bush", "bush_berries"])]

# ---- 4. flowers: drifts and clumps with quiet spaces between
doc = ops.clear_scatter(doc, ["flowers_pink", "flowers_yellow"])
DRIFTS = [  # dabs of one drift (a short sweep), radius px
    ([(250, 330), (330, 300), (410, 280)], 52),     # meadow west of the cottages
    ([(1480, 300), (1570, 270), (1660, 250)], 56),  # meadow south-east
    ([(880, 1080), (970, 1120), (1060, 1150)], 56),  # north meadow
    ([(260, 1010), (330, 1060)], 48),               # west slope
    ([(1560, 1250), (1640, 1290)], 44),             # the pond's grassy north margin
    ([(1820, 760), (1880, 700)], 48),               # east meadow
    ([(700, 1180), (780, 1200)], 44),               # below the north-west wood
    ([(1400, 470), (1460, 430)], 40),               # by the barrels, east of the shop
    ([(520, 380), (520, 430)], 34),                 # along the fence by the cottages (west side of it)
    ([(690, 700), (760, 700)], 30),                 # along the fence north of the cottage
    ([(545, 585), (675, 585)], 26),                 # the cottage's front garden, either side of its door
    ([(500, 210), (625, 210)], 24),                 # the south cottage's front
    ([(1040, 1350), (1110, 1380)], 44),             # far north
    ([(1170, 165), (1240, 145)], 40),               # south-east of the crossroads, off the path
]
for i, (dabs, r) in enumerate(DRIFTS):
    pts = [list(p) for p in dabs]
    doc = ops.scatter_stroke(doc, "Meadow", pts, radius=r, mode="thin", share=0.55, seed=600 + i)
    doc = ops.scatter_stroke(doc, {"flowers_yellow": 1.0, "flowers_pink": 1.0} if i % 3 else
                             {"flowers_yellow": 2.0, "flowers_pink": 1.0}, pts, radius=r, density=3.5, clumping=0.8,
                             seed=700 + i)
log["flowers"] = [sum(len(shipped["settings"]["hd2d"]["scatter"][k]) for k in ("flowers_pink", "flowers_yellow")),
                  count(doc, ["flowers_pink", "flowers_yellow"])]

# ---- 5. worn ground: earth trodden in where people stand and turn
WORN = [  # (dabs (x, y, strength), radius px)
    ([(608, 578, 0.55), (596, 566, 0.45), (622, 560, 0.35)], 44),    # the cottage's doorstep
    ([(560, 196, 0.5), (548, 184, 0.4), (574, 206, 0.35)], 40),      # the south cottage's doorstep
    ([(1168, 470, 0.55), (1130, 480, 0.45), (1205, 462, 0.45)], 62),  # the shop front
    ([(900, 410, 0.45), (880, 430, 0.35), (925, 395, 0.35)], 56),    # the crossroads
    ([(1090, 712, 0.45), (1080, 690, 0.35)], 40),                    # the bridge's south end
]
for i, (dabs, r) in enumerate(WORN):
    doc = ops.paint_terrain_stroke(doc, "earth", [list(d) for d in dabs], radius=r)
    doc = ops.scatter_stroke(doc, COVER, [[d[0], d[1]] for d in dabs[:1]], radius=round(r * 0.55), mode="remove",
                             seed=800 + i)
log["scatter_total"] = [count(shipped), count(doc)]

# ---- what must not change
def strip(d):
    d = copy.deepcopy(d)
    h = d["settings"]["hd2d"]
    h.pop("scatter", None)
    h["ground"]["terrain"].pop("materials", None)
    for lt in d["lights"]:
        lt.pop("enabled", None)
    return d


for row in doc["settings"]["hd2d"]["scatter"]["tree_small"]:  # (no tree on or right beside a path)
    assert clear_of_paths(row[0], row[1], 40) or tuple(row) in {tuple(r) for r in kept}, row
assert strip(doc) == strip(shipped), "something besides scatter, paint and the lamps' on/off changed"
for kind in ("rock_small", "rock_medium", "reeds", "reeds_cattail"):  # (only ground cover and trees were recomposed)
    assert doc["settings"]["hd2d"]["scatter"][kind] == shipped["settings"]["hd2d"]["scatter"][kind], kind
assert doc["settings"]["hd2d"]["ground"]["terrain"]["chunks"] == shipped["settings"]["hd2d"]["ground"]["terrain"]["chunks"]
text = json.dumps(doc, indent=2, sort_keys=True) + "\n"  # as Studio saves a scene: sorted keys, indent 2, LF endings
dst.write_bytes(text.encode("utf-8"))  # (bytes: Windows' text mode would turn every LF into CRLF)
print(json.dumps(log, indent=1))
