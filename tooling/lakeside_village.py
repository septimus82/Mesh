"""Lakeside Village: an HD-2D showcase built in Mesh Studio, the way a creator builds it (hidden window only).

    py -3.13 tooling/lakeside_village.py PHASE PROJECT OUT_DIR

PROJECT is a game made with ``mesh new "Lakeside Village" --template hd2d_rpg``; OUT_DIR gets the pictures and each
phase's report. Every authoring step goes through Mesh Studio's own input events: its buttons, fields, mouse strokes
and keys (``hd2d_studio_demo.StudioDriver``). There are two exceptions, both documented in
``docs/reviews/lakeside_village.md`` and approved by the owner as workarounds for Studio gaps:

- ``make_hd2d``: Studio's "+ New room" only makes 2D rooms. One edit gives the new room the HD-2D template's own
  settings (``engine.hd2d.starter_village``), with a 64 x 48 m ground: its extent, gameplay camera, sun and sky.
- Where the water stands (its elevation): Studio sets it from where the water is placed and has no field for it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")

from hd2d_studio_demo import StudioDriver  # noqa: E402

PX = 32.0
W_M, H_M = 64.0, 48.0
ROOM = "Lakeside"
ROOM_FILE = "packs/core_regions/scenes/lakeside.json"


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def make_hd2d(project: Path) -> dict[str, Any]:
    """The documented edit (Studio can't make an HD-2D room): what the HD-2D template does to make its village room
    (``engine.hd2d.starter_village``), at 64 x 48 m: an outdoor grass map of the room's size (Studio's new room has an
    indoor floor and walls), the HD-2D settings (ground extent, gameplay camera, sun, ambient) and the sky light."""
    from engine.hd2d.starter_village import OUTDOOR_VIEW, _camera, _hd2d, _map

    path = project / ROOM_FILE
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene.pop("tilemap", None)  # (Studio's indoor floor and walls: replaced by the template's outdoor map)
    scene = _map(scene, ROOM_FILE, int(W_M), int(H_M), project)
    settings = scene.setdefault("settings", {})
    settings["hd2d"] = _hd2d(W_M, H_M, _camera(30.0, OUTDOOR_VIEW, (0, 0, W_M, H_M)))
    settings["world_width"], settings["world_height"] = W_M * PX, H_M * PX
    settings["lighting_shadow_softness"] = "soft"
    scene["lights"] = [{"id": "sky", "type": "ambient", "color": "#9aa6d0", "mode": "soft"}]
    _write(path, scene)
    return {"edited": ROOM_FILE, "settings.hd2d": settings["hd2d"], "world": [settings["world_width"],
                                                                              settings["world_height"]]}


def room(project: Path, out: Path) -> dict[str, Any]:
    """Phase 1: the room. In Studio: + New room "Lakeside", saved. Then the documented edit; then Studio again: the
    room opens as HD-2D."""
    d = StudioDriver(project)
    try:
        d.button("+ New room")
        d.type_into("room_name", ROOM)
        d.button("Create")
        d.frame(2)
        made = d.studio.project.current
        _save(d)
        report: dict[str, Any] = {"made_room": made, "rooms": [r[0] for r in d.studio.project.rooms()],
                                  "message": d.studio.message}
    finally:
        d.close()
    report["documented_edit"] = make_hd2d(project)
    d = StudioDriver(project)
    try:
        d.button(ROOM)
        d.frame(5)
        report["hd2d_view"] = d.studio.hd2d.renderer is not None
        d.picture(out / "01_room_empty.png")
    finally:
        d.close()
    return report


# -- the plan (metres; x east, y north) --------------------------------------------------------------------------------
POND = (44.0, 31.0)             # the pond's middle; its basin is sculpted, its water placed in it
INLET = [(33.0, 26.0), (36.5, 27.5), (39.5, 29.0)]   # a narrow inlet running south-west from the pond: the bridge spans it
HILLS = [((12.0, 37.0), 9.0, 3.0), ((24.0, 42.0), 7.0, 2.0), ((56.0, 42.0), 8.0, 2.5), ((57.0, 12.0), 7.0, 1.5),
         ((6.0, 18.0), 6.0, 1.2)]  # (middle, radius m, height m)
PATHS = [
    [(30.0, 0.5), (29.5, 5.0), (28.0, 9.0), (27.0, 12.0)],                  # in from the south to the square
    [(27.0, 12.0), (23.0, 14.0), (19.5, 15.5)],                              # west, to the cottage
    [(27.0, 12.0), (31.0, 13.0), (35.0, 14.5)],                              # east, to the shop
    [(27.0, 12.0), (29.0, 17.0), (31.5, 21.5), (34.0, 25.0), (35.0, 28.5), (35.5, 33.0), (38.0, 38.5),
     (44.0, 40.5), (50.0, 39.0), (53.0, 34.0)],                              # north over the bridge, round the pond
    [(19.5, 15.5), (16.0, 21.0), (13.0, 27.0), (12.0, 33.0)],                # north-west, up the hill
]


def _ground_at(d: Any, x: float, y: float) -> float:
    h = d.studio.hd2d.renderer.terrain.height(x * PX, y * PX) if d.studio.hd2d.renderer.terrain else None
    return (h or 0.0) / PX


def _circle(c: tuple[float, float], r: float, n: int = 10, wobble: float = 0.0) -> list[tuple[float, float]]:
    """A ring round ``c`` (``wobble``: up to that share of ``r`` in and out, smoothly, for a natural shore)."""
    import math

    def at(k: int) -> tuple[float, float]:
        a = 2 * math.pi * k / n
        rr = r * (1 + wobble * (0.6 * math.sin(3 * a + 0.7) + 0.4 * math.sin(5 * a + 2.1)))
        return c[0] + rr * math.cos(a), c[1] + rr * math.sin(a)

    return [at(k) for k in range(n + 1)]


def _sculpt_to(d: Any, middle: tuple[float, float], radius: float, height: float, *, lower: bool = False) -> int:
    """Brush strokes round ``middle`` (Studio's Raise or Lower, its radius), repeated until the ground there reaches
    ``height``, as a creator holds the brush until it looks right. Returns the strokes made."""
    import m20b_sculpt_study as m20b
    import m20c_material_study as m20c

    m20c._look_at(d, middle[0], middle[1], max(24.0, radius * 3.2))
    strokes = 0
    for _ in range(60):
        now = _ground_at(d, *middle)
        if (now <= height) if lower else (now >= height):
            break
        m20b._stroke(d, m20c._on_ground(d, _circle(middle, radius * 0.35, 8), 0.4))
        strokes += 1
    return strokes


def _paint_line(d: Any, line: list[tuple[float, float]], *, chunk_m: float = 6.0) -> int:
    """A long stroke the way a creator paints one: the view follows along, each visible stretch one stroke (Studio
    paints only what is in its view)."""
    import m20b_sculpt_study as m20b
    import m20c_material_study as m20c

    points = m20c._spline(line, 0.08) if len(line) > 1 else line
    strokes, start, run = 0, 0, 0.0
    for i in range(1, len(points)):
        run += ((points[i][0] - points[i - 1][0]) ** 2 + (points[i][1] - points[i - 1][1]) ** 2) ** 0.5
        if run >= chunk_m or i == len(points) - 1:
            part = points[start:i + 1]
            mid = part[len(part) // 2]
            m20c._look_at(d, mid[0], mid[1], 16.0)
            m20b._stroke(d, [(x, y, _ground_at(d, x, y)) for x, y in part])
            strokes += 1
            start, run = i, 0.0
    return strokes


def ground(project: Path, out: Path) -> dict[str, Any]:
    """Phase 2: the land, in Studio. Sculpt: the hills, the pond's basin and its inlet (Raise, Lower, Smooth). Paint:
    the paths (Earth), a sandy shore (Sand), the square (Stone). Saved."""
    import m20b_sculpt_study as m20b
    import m20c_material_study as m20c

    d = StudioDriver(project)
    report: dict[str, Any] = {"hills": [], "paths": len(PATHS)}
    try:
        d.button(ROOM)
        d.frame(3)
        d.button("Sculpt")
        d.button("Raise")
        for middle, radius, height in HILLS:
            d.type_into("sculpt_radius", f"{radius:g}")
            d.type_into("sculpt_rate", "0.5")
            n = _sculpt_to(d, middle, radius, height)
            report["hills"].append({"middle": middle, "strokes": n, "height_m": round(_ground_at(d, *middle), 2)})
        d.button("Lower")
        d.type_into("sculpt_radius", "7")
        d.type_into("sculpt_rate", "1.5")
        n = _sculpt_to(d, POND, 7.0, -1.3, lower=True)
        d.type_into("sculpt_radius", "4.5")
        for x, y in ((POND[0] - 4.5, POND[1] + 2.0), (POND[0] + 4.0, POND[1] - 1.5)):  # a less round pond
            _sculpt_to(d, (x, y), 4.5, -1.0, lower=True)
        d.type_into("sculpt_radius", "2")
        m20c._look_at(d, 36.5, 27.5, 18.0)
        for _ in range(4):
            m20b._stroke(d, m20c._on_ground(d, INLET, 0.3))
        report["pond"] = {"strokes": n, "depth_m": round(_ground_at(d, *POND), 2),
                          "inlet_m": [round(_ground_at(d, x, y), 2) for x, y in INLET]}
        d.button("Smooth")
        d.type_into("sculpt_radius", "6")
        for middle, radius, _h in HILLS:  # soften each hill's foot, as a creator does with Smooth
            m20c._look_at(d, middle[0], middle[1], max(24.0, radius * 3.2))
            m20b._stroke(d, m20c._on_ground(d, _circle(middle, radius * 0.9, 12), 0.4))
        m20c._look_at(d, POND[0], POND[1], 26.0)
        m20b._stroke(d, m20c._on_ground(d, _circle(POND, 7.5, 12), 0.4))
        d.button("Sculpt")  # (off)
        d.button("Paint")
        d.button("Earth")
        d.type_into("paint_radius", "1.1")
        report["path_strokes"] = [_paint_line(d, line) for line in PATHS]
        d.button("Sand")
        d.type_into("paint_radius", "1.6")
        report["shore_strokes"] = _paint_line(d, _circle(POND, 7.6, 36, wobble=0.12))
        d.button("Paint")  # (off)
        _save(d)
        report["message"] = d.studio.message
        report["undo_steps"] = len(d.studio.project._undo)
        m20c._look_at(d, 32.0, 22.0, 70.0)
        d.picture(out / "02_ground.png")
    finally:
        d.close()
    return report


LEVEL = -0.45  # m: the water's surface, a little below the banks


def _contour(d: Any, middle: tuple[float, float], toward: tuple[float, float], level: float) -> tuple[float, float]:
    """The first spot from ``middle`` toward ``toward`` where the ground comes up to ``level``: where to click so the
    water, which takes the height of where it is put, gets that level (Studio has no field for it)."""
    for i in range(1, 400):
        t = i / 400
        x, y = middle[0] + (toward[0] - middle[0]) * t, middle[1] + (toward[1] - middle[1]) * t
        if _ground_at(d, x, y) >= level:
            return x, y
    raise AssertionError(f"no ground at {level} m between {middle} and {toward}")


def _water(d: Any, at_level: tuple[float, float], middle: tuple[float, float], fields: dict[str, str],
           buttons: list[str]) -> dict[str, Any]:
    """Objects > Water, clicked where the ground is at the level wanted; dragged (at that level) to ``middle``; then its
    inspector: buttons and fields."""
    import m20c_material_study as m20c

    m20c._look_at(d, at_level[0], at_level[1], 18.0)  # (the view on the spot, as a creator pans to it)
    d.key(d.arcade.key.ESCAPE)  # (nothing selected: the inspector's "Water" heading isn't the Objects list's)
    d.button("Water")
    d.click(*d.screen((at_level[0], at_level[1], _ground_at(d, *at_level))))
    entity_id = d.studio.selected
    assert entity_id, d.studio.message
    placed = d.studio._entity(entity_id) or {}
    level = float(placed.get("elevation", 0.0)) / PX
    m20c._look_at(d, (at_level[0] + middle[0]) / 2, (at_level[1] + middle[1]) / 2, 28.0)
    start = d.screen((float(placed["x"]) / PX, float(placed["y"]) / PX, level))
    d.drag(start, d.screen((middle[0], middle[1], level)), steps=16)
    for label in buttons:
        d.button(label)
    for key, text in fields.items():
        d.type_into(key, text)
    water = d.studio._entity(entity_id) or {}
    return {"id": entity_id, "level_m": round(level, 3), "x_m": round(float(water["x"]) / PX, 2),
            "y_m": round(float(water["y"]) / PX, 2), "water": water.get("water")}


def water(project: Path, out: Path) -> dict[str, Any]:
    """Phase 3: the pond and its inlet, in Studio: Objects > Water placed where the bank is at the water's level,
    dragged into the basin; Natural pond, a natural outline, the sculpted ground as its shore; its size and turn."""
    import m20c_material_study as m20c

    d = StudioDriver(project)
    try:
        d.button(ROOM)
        d.frame(3)
        # Walk through it: Off: the Natural pond preset can be waded, out to the basin's 1.5 m middle (the player sinks
        # 1.1 m under the surface); deep water stops a player here, and the bridge is the way over the inlet.
        pond = _water(d, _contour(d, POND, (POND[0] + 9.0, POND[1]), LEVEL), POND,
                      {"water_w": "460", "water_h": "330"}, ["Natural pond", "Natural", "Ground", "Walk through it: On"])
        mid = INLET[1]
        inlet = _water(d, _contour(d, mid, (mid[0] - 2.0, mid[1] + 4.0), LEVEL), mid,
                       {"water_w": "330", "water_h": "96", "water_turn": "25"},
                       ["Natural pond", "Natural", "Ground", "Walk through it: On"])
        _save(d)
        report = {"pond": pond, "inlet": inlet, "message": d.studio.message}
        m20c._look_at(d, 40.0, 29.0, 34.0)
        d.picture(out / "03_water.png")
    finally:
        d.close()
    return report


def _right_button(d: Any, text: str) -> None:
    """Click the button starting with ``text`` in Studio's right panel (the Rooms list on the left has buttons of the
    same names: a room called Cottage, a model called Cottage)."""
    edge = d.studio.hd2d._rect()[1]
    for widget in d.studio.ui.walk_widgets():
        label = getattr(widget, "text", None)
        if isinstance(label, str) and label.startswith(text) and widget.rect.left >= edge:
            r = widget.rect
            d.click(r.left + r.width / 2, r.bottom + r.height / 2)
            return
    raise AssertionError(f"no '{text}' in the right panel")


def _place_model(d: Any, name: str, x: float, y: float, *, turn: float | None = None, height: float | None = None,
                 scale: float | None = None) -> dict[str, Any]:
    """Models... > search > the model > Place in scene > a click on the ground at (x, y); then its inspector's fields for
    the exact place, turn, height (m) and scale, as a creator types them."""
    import m20c_material_study as m20c

    k = d.arcade.key
    d.key(k.ESCAPE)
    m20c._look_at(d, x, y, 20.0)
    if d.studio.panel != "structures":  # (Models... opens and closes the list)
        d.button("Models...")
    if d.studio.hd2d.chosen_model is not None:  # (still on the last model's page)
        _right_button(d, "< All models")
    d.type_into("model_search", name)
    _right_button(d, name)
    d.button("Place in scene")
    d.click(*d.screen((x, y, _ground_at(d, x, y))))
    sid = d.studio.hd2d.structure
    assert sid, d.studio.message
    d.type_into("structure_x", f"{x:g}")
    d.type_into("structure_y", f"{y:g}")
    if turn is not None:
        d.type_into("structure_rotation", f"{turn:g}")
    if height is not None:
        d.type_into("structure_elevation", f"{height:g}")
    if scale is not None:
        d.type_into("structure_scale", f"{scale:g}")
    st = d.structure(sid) or {}
    return {"id": sid, "model": name, "x": st.get("x"), "y": st.get("y"), "elevation": st.get("elevation"),
            "rotation": st.get("rotation"), "scale": st.get("scale")}


BUILDINGS = [("Cottage", 19.0, 20.0, 0.0), ("Cottage", 17.5, 8.0, 0.0), ("Shop", 36.5, 17.5, 0.0)]
BRIDGE = (34.4, 26.5, 74.0, -1.8)          # x, y, turn, height (m): the kit's deck is 2 m up; lowered to the banks
PROPS = [("Barrel", 38.8, 15.6, 0.0), ("Barrel", 39.6, 16.2, 30.0), ("Crate", 33.8, 16.0, 15.0),
         ("Fence", 15.0, 11.5, 90.0), ("Fence", 15.0, 13.5, 90.0), ("Fence", 21.5, 23.5, 0.0),
         ("Fence", 23.5, 23.5, 0.0), ("Lamp post", 25.0, 10.2, 0.0), ("Lamp post", 29.4, 13.8, 0.0),
         ("Lamp post", 32.6, 23.6, 0.0), ("Lamp post", 21.2, 18.3, 0.0)]
LAMPS = [(25.0, 10.2), (29.4, 13.8), (32.6, 23.6), (21.2, 18.3)]  # the lamp posts' lanterns: lights 2.5 m up
# where the scatter brush's Small trees go: clusters round (x, y) (the third value: unused)
TREES = [(8.5, 33.0, 2.8), (14.5, 40.5, 3.2), (6.0, 41.5, 2.6), (19.0, 37.5, 2.4), (2.5, 27.0, 2.9),
         (52.0, 44.5, 3.0), (58.5, 38.0, 2.7), (61.5, 45.0, 3.1), (47.5, 45.5, 2.5), (60.5, 26.0, 2.6),
         (60.0, 8.0, 2.9), (54.0, 5.5, 2.4), (62.0, 17.0, 2.7), (5.5, 4.5, 2.8), (3.5, 13.5, 2.5),
         (26.5, 33.5, 2.3), (41.0, 21.0, 2.2)]   # (x, y, scale): ~5-6 m trees, round the edges, hills and pond
DOORWAYS = [[(19.5, 15.5), (19.2, 17.2), (19.0, 18.4)],                    # cottage (north-west)
            [(29.5, 5.0), (24.0, 5.6), (19.5, 6.3), (17.5, 6.6)],           # cottage (south-west)
            [(35.0, 14.5), (36.0, 15.6)]]                                  # shop


def build(project: Path, out: Path) -> dict[str, Any]:
    """Phase 4: the village, in Studio. Models: the cottages, the shop, the bridge (lowered to the banks) and props,
    each placed and then set exactly in its inspector; buildings see-through in play. Paint: the paths to their doors.
    Saved. (Trees come from the scatter brush: the kit's only tree is a trunk model whose canopy is scatter sprites,
    so placed as a model it is a bare trunk; see docs/reviews/lakeside_village.md.)"""
    import m20c_material_study as m20c

    d = StudioDriver(project)
    k = d.arcade.key
    report: dict[str, Any] = {"placed": []}
    try:
        d.button(ROOM)
        d.frame(3)
        for name, x, y, turn in BUILDINGS:
            placed = _place_model(d, name, x, y, turn=turn)
            _right_button(d, "See-through in play: Off")
            report["placed"].append(placed)
        bx, by, bturn, bheight = BRIDGE
        report["placed"].append(_place_model(d, "Bridge", bx, by, turn=bturn, height=bheight))
        for name, x, y, turn in PROPS:
            report["placed"].append(_place_model(d, name, x, y, turn=turn))
        d.key(k.ESCAPE)
        d.button("Paint")
        d.button("Earth")
        d.type_into("paint_radius", "0.9")
        report["doorway_strokes"] = [_paint_line(d, line) for line in DOORWAYS]
        d.button("Paint")  # (off)
        _save(d)
        report["message"] = d.studio.message
        for name, (x, y, dist) in {"04_square": (27.0, 14.0, 30.0), "04_bridge": (34.4, 26.5, 16.0),
                                   "04_overview": (32.0, 22.0, 75.0)}.items():
            m20c._look_at(d, x, y, dist)
            d.picture(out / f"{name}.png")
    finally:
        d.close()
    return report


def _rows(x0: float, y0: float, x1: float, y1: float, gap: float) -> list[tuple[float, float]]:
    """A zigzag over a rectangle, rows ``gap`` m apart: one brush pass fills a band as wide as the brush."""
    out: list[tuple[float, float]] = []
    y, east = y0, True
    while y <= y1 + 1e-6:
        out += [(x0, y), (x1, y)] if east else [(x1, y), (x0, y)]
        y, east = y + gap, not east
    return out


def _scatter(d: Any, collection: str, lines: list[list[tuple[float, float]]], *, radius: float,
             density: str | None = None, singles: bool = False, off: tuple[str, ...] = ()) -> dict[str, Any]:
    """Scatter: choose the collection (one asset: One thing at a time...), its radius and density, and draw."""
    if singles and not d.studio.hd2d.sculpt.get("singles"):
        d.button("One thing at a time...")
    d.button(collection)
    for material in off:  # (Studio's material toggles: not on the paths)
        if material in d.studio.hd2d.sculpt["on"]:
            d.button(material.capitalize())
    d.type_into("scatter_radius", f"{radius:g}")
    if density is not None:
        d.type_into("scatter_density", density)
    brush = dict(d.studio.hd2d.sculpt)
    strokes = sum(_paint_line(d, line, chunk_m=8.0) for line in lines)
    return {"collection": collection, "on": sorted(brush.get("on") or []), "density": brush.get("density"),
            "strokes": strokes}


def nature(project: Path, out: Path) -> dict[str, Any]:
    """Phase 5: the land's growth and its wind, in Studio. Scatter: a meadow over the open land, wildflowers, the
    pond's reeds, shrubs by the houses, rocks on the slopes, deadfall in the woods, small trees in clusters (One
    thing at a time... > Small tree). Wind and motion: Breeze, animation on. Saved."""
    import m20c_material_study as m20c

    d = StudioDriver(project)
    report: dict[str, Any] = {"scatter": []}
    try:
        d.button(ROOM)
        d.frame(3)
        d.button("Scatter")
        sc = report["scatter"]
        # Big things first: two scattered things keep apart by the mean of their spacings, so after a meadow a
        # tree (3 m) or a rock has no room left ("The stroke changed nothing"); see docs/reviews/lakeside_village.md.
        sc.append(_scatter(d, "Small tree", [_circle((x, y), 1.5, 6) for x, y, _r in TREES], radius=3.0,
                           density="0.25", singles=True, off=("earth",)))
        sc.append(_scatter(d, "Rocks", [_circle((12.0, 37.0), 6.0, 10, wobble=0.3),
                                        _circle((56.0, 42.0), 5.0, 10, wobble=0.3),
                                        [(51.0, 26.0), (52.5, 32.0), (51.5, 37.0)]],
                           radius=1.2, off=("earth",)))
        sc.append(_scatter(d, "Deadfall", [_circle((58.0, 41.0), 4.0, 8), _circle((6.0, 40.0), 3.5, 8)], radius=2.0,
                           off=("earth",)))
        sc.append(_scatter(d, "Shrubs", [[(14.0, 18.0), (14.0, 23.0)], [(23.5, 18.0), (24.5, 22.0)],
                                         [(13.5, 5.5), (13.5, 10.0)], [(41.0, 16.0), (41.0, 19.5)],
                                         [(1.5, 2.0), (1.5, 46.0)], [(62.5, 2.0), (62.5, 46.0)],
                                         [(2.0, 46.5), (62.0, 46.5)]], radius=1.5))
        sc.append(_scatter(d, "Meadow", [_rows(1.0, 1.0, 63.0, 47.0, 7.0)], radius=4.0))
        sc.append(_scatter(d, "Wildflowers", [_circle(c, r, 8, wobble=0.2) for c, r in
                                              (((15.0, 25.0), 2.5), ((24.0, 40.0), 3.0), ((52.0, 20.0), 2.5),
                                               ((8.0, 8.0), 2.0), ((40.0, 8.0), 2.5), ((58.0, 33.0), 2.0))],
                           radius=1.8))
        sc.append(_scatter(d, "Pond edge", [_circle(POND, 7.3, 40, wobble=0.12), _circle(POND, 8.4, 40, wobble=0.12),
                                            [(31.5, 24.8), (35.0, 26.0), (38.5, 28.0)],
                                            [(33.5, 28.6), (37.0, 30.2)]], radius=1.0))
        d.button("Scatter")  # (off)
        d.button("Breeze")
        d.button("Animation: off")
        _save(d)
        report["message"] = d.studio.message
        hd = d.studio.hd2d.renderer
        report["instances"] = hd.scatter.count() if hd and hd.scatter else 0
        report["wind"] = list(hd.wind.vector) if hd else None
        for name, (x, y, dist) in {"05_square": (27.0, 14.0, 30.0), "05_pond": (44.0, 31.0, 26.0),
                                   "05_overview": (32.0, 22.0, 75.0), "05_hill": (12.0, 34.0, 26.0)}.items():
            m20c._look_at(d, x, y, dist)
            d.picture(out / f"{name}.png")
    finally:
        d.close()
    return report


PLAYER_START = (29.5, 4.0)
ENTRANCE = (30.0, 1.0)  # the door to the Village: where the south road leaves the room


def _panel_to_top(d: Any) -> None:
    """Scroll Studio's right panel back to its top with the mouse wheel (a person scrolls up to the buttons there)."""
    for _ in range(40):
        if not d.studio.panel_scroll:
            return
        d.window.dispatch_event("on_mouse_scroll", d.window.width - 100, d.window.height / 2, 0, 1)
        d.frame()


def _save(d: Any) -> None:
    """Studio's Save button (Ctrl+S after typing in a field goes to the field), and Studio said it saved."""
    d.key(d.arcade.key.ESCAPE)
    d.button("Save")
    assert d.studio.message.startswith("Saved") or not d.studio.project.dirty, d.studio.message


def _player(d: Any) -> dict[str, Any]:
    return next(e for e in d.studio.project.scene().get("entities") or [] if e.get("tag") == "player")


def _entity(d: Any, entity_id: str) -> dict[str, Any]:
    return next(e for e in d.studio.project.scene().get("entities") or [] if e.get("id") == entity_id)


def _drag_player_to(d: Any, target: tuple[float, float], hop: float = 4.0) -> int:
    return _drag_to(d, lambda: _player(d), target, hop)


def _drag_to(d: Any, find: Any, target: tuple[float, float], hop: float = 4.0) -> int:
    """Drag an object there in short hops, the view on it each time, as a person drags, pans and drags again."""
    import math

    import m20c_material_study as m20c

    hops = 0
    for _ in range(30):
        player = find()
        here = (float(player["x"]) / PX, float(player["y"]) / PX)
        gap = math.dist(here, target)
        if gap < 0.6:
            break
        step = min(1.0, hop / gap)
        to = (here[0] + (target[0] - here[0]) * step, here[1] + (target[1] - here[1]) * step)
        z = float(player.get("elevation", 0.0) or 0.0) / PX
        m20c._look_at(d, (here[0] + to[0]) / 2, (here[1] + to[1]) / 2, 12.0)
        d.drag(d.screen((here[0], here[1], z + 0.6)), d.screen((to[0], to[1], z + 0.6)), steps=10)
        hops += 1
    return hops


def finish(project: Path, out: Path) -> dict[str, Any]:
    """Phase 6: lights, the player and the way in, in Studio. Lighting: a warm lamp at each lamp post's lantern
    (+ Add light, a click; More settings: size and height), then the room's lighting back to the project's (adding
    the first light turns the room's 2D lighting on at Night). The player dragged to the south road; a right-click at
    the road's end: Add door to Village (and one back). Saved."""
    import m20c_material_study as m20c

    d = StudioDriver(project)
    k = d.arcade.key
    report: dict[str, Any] = {}
    try:
        d.button(ROOM)
        d.frame(3)
        d.button("Lighting")
        for i, (x, y) in enumerate(LAMPS):
            m20c._look_at(d, x, y, 16.0)
            _panel_to_top(d)
            d.button("+ Add light")
            d.click(*d.screen((x, y, _ground_at(d, x, y))))
            if d.studio.expanded != "light_more":  # (it stays open from one light to the next)
                d.button("> More settings")
            d.type_into("light_radius", "224")
            d.type_into("light_height", "2.4")
        report["lights_message"] = d.studio.message
        _panel_to_top(d)
        d.button("As project")
        _right_button(d, "Project's")  # (the room light row's: no Night ambient left over in the room)
        scene = d.studio.project.scene()
        report["lights"] = scene.get("lights")
        report["room_lighting"] = {k2: v for k2, v in (scene.get("settings") or {}).items() if k2.startswith("lighting")}
        d.button("Lighting")  # (panel closed)
        d.key(k.ESCAPE)
        report["player_hops"] = _drag_player_to(d, PLAYER_START)
        player = _player(d)
        report["player"] = [float(player["x"]) / PX, float(player["y"]) / PX]
        m20c._look_at(d, ENTRANCE[0], ENTRANCE[1] + 3.0, 14.0)
        d.click(*d.screen((ENTRANCE[0], ENTRANCE[1], _ground_at(d, *ENTRANCE))), button=d.arcade.MOUSE_BUTTON_RIGHT)
        d.button("Add door to Village")
        report["door_message"] = d.studio.message
        _save(d)
        report["message"] = d.studio.message
        report["doors"] = [{k2: e.get(k2) for k2 in ("id", "tag", "x", "y", "target_scene", "spawn_id")}
                           for e in d.studio.project.scene().get("entities") or [] if e.get("tag") in ("door", "spawn_point")]
        m20c._look_at(d, 29.0, 8.0, 22.0)
        d.picture(out / "06_entrance.png")
    finally:
        d.close()
    return report


VILLAGE_PASSAGE, VILLAGE_ARRIVAL = (37.5, 7.0), (35.0, 7.0)  # the Village's east road end: on to Lakeside


def doors(project: Path, out: Path) -> dict[str, Any]:
    """Phase 7: the way between the rooms as roads, not doors in a meadow, in Studio. Village: its door to Lakeside
    and its arrival spot dragged to the east road's end; the door shown as a Passage (an invisible area) across the
    road. Lakeside: its door shown as a Passage across the south road. Saved."""
    import m20c_material_study as m20c

    d = StudioDriver(project)
    report: dict[str, Any] = {}
    try:
        d.button("Village")
        d.frame(3)
        scene = d.studio.project.scene()
        door = next(e["id"] for e in scene["entities"] if e.get("tag") == "door" and "lakeside" in e["id"])
        arrival = next(e["id"] for e in scene["entities"] if e.get("tag") == "spawn_point" and "lakeside" in e["id"])
        report["village_hops"] = [_drag_to(d, lambda i=i: _entity(d, i), to)
                                  for i, to in ((door, VILLAGE_PASSAGE), (arrival, VILLAGE_ARRIVAL))]
        e = _entity(d, door)
        m20c._look_at(d, *VILLAGE_PASSAGE, 12.0)
        d.click(*d.screen((float(e["x"]) / PX, float(e["y"]) / PX, 0.6)))
        _right_button(d, "Passage")
        d.type_into("door_width", "64")
        d.type_into("door_height", "160")
        report["village_door"] = {k2: _entity(d, door).get(k2) for k2 in ("x", "y", "behaviour_config")}
        report["village_arrival"] = {k2: _entity(d, arrival).get(k2) for k2 in ("x", "y")}
        _save(d)
        d.button(ROOM)
        d.frame(3)
        scene = d.studio.project.scene()
        door = next(e["id"] for e in scene["entities"] if e.get("tag") == "door")
        e = _entity(d, door)
        m20c._look_at(d, float(e["x"]) / PX, float(e["y"]) / PX + 3.0, 12.0)
        d.click(*d.screen((float(e["x"]) / PX, float(e["y"]) / PX, 0.6)))
        _right_button(d, "Passage")
        d.type_into("door_width", "160")
        d.type_into("door_height", "64")
        report["lakeside_door"] = {k2: _entity(d, door).get(k2) for k2 in ("x", "y", "behaviour_config")}
        _save(d)
        report["message"] = d.studio.message
    finally:
        d.close()
    return report


ROUTES = [  # (name, start (m) or None to go on from where the last stopped, legs: (key, axis, target m), expected)
    ("south road to the crossroads", PLAYER_START, [("UP", 1, 11.5)], True),
    ("over the bridge (steering along its deck, as a player does)", (33.9, 22.0),
     [("UP", 1, 25.0), ("RIGHT", 0, 34.4), ("UP", 1, 27.0), ("RIGHT", 0, 34.95), ("UP", 1, 29.6)], True),
    ("round the pond's north side", (35.5, 33.0), [("UP", 1, 39.5), ("RIGHT", 0, 53.0), ("DOWN", 1, 24.0)], True),
    ("into the pond (stops at its shore)", (46.5, 21.0), [("UP", 1, 31.0)], False),
    ("up the hill path", (13.0, 24.0), [("UP", 1, 36.5)], True),
    ("into a cottage wall (stops)", (21.0, 13.0), [("UP", 1, 21.0)], False),
    ("up the south-east mound", (45.0, 12.5), [("RIGHT", 0, 56.5)], True),
]
PICTURES = {"07_start": PLAYER_START, "07_crossroads": (28.5, 11.0), "07_shop": (35.0, 13.5),
            "07_pond_north": (43.0, 39.5), "07_pond_south": (47.5, 21.5),
            "07_hilltop": (12.0, 36.5), "07_cottages": (18.0, 13.0), "07_east_mound": (57.0, 12.0)}


def play(project: Path, out: Path, *, prefix: str = "") -> dict[str, Any]:
    """Phase 8: the game itself (the runtime an exported game runs; a hidden window). Walks each route with the
    arrow keys and records where the feet go and stand (on the ground: never floating or sunk; on the bridge's deck
    over the water), what stopped them, the vegetation moving while the player stands still, GPU objects across
    reloads; pictures from the game's camera."""
    import math

    from hd2d_demo import HiddenGame
    from hd2d_floors_demo import _feet, hold_key
    from m20a_terrain_study import _put

    from engine.hd2d.world import elevation_of

    game = HiddenGame(project, size=(1280, 720))
    report: dict[str, Any] = {"routes": []}
    try:
        game.load(ROOM_FILE)
        game.step(20)
        keys = game.arcade.key
        hd = game.window.hd2d_renderer
        report["start"] = [round(v, 2) for v in _feet(game.player())]

        def ground(x: float, y: float) -> float:
            return (hd.terrain.height(x * PX, y * PX) or 0.0) / PX if hd.terrain else 0.0

        for name, start, legs, expect in ROUTES:
            player = _put(game, *start) if start else game.player()
            trace: list[tuple[float, float, float]] = []

            def each() -> None:
                fx, fy = _feet(player)
                trace.append((fx, fy, elevation_of(player)))  # (m)

            reached = []
            for i, (k, axis, target) in enumerate(legs):
                reached.append(hold_key(game, player, getattr(keys, k), axis, target, 1500, each_frame=each))
                if name.startswith("over the bridge") and i == 2:  # (mid-deck: the bridge's picture)
                    game.step(30)
                    game.draw().convert("RGB").save(out / f"{prefix}07_bridge.png")
            off = [abs(z - ground(x, y)) for x, y, z in trace if not (32.5 <= x <= 36.0 and 23.5 <= y <= 29.5)]
            on_bridge = [z for x, y, z in trace if 33.0 <= x <= 35.5 and 25.0 <= y <= 28.0]
            fx, fy = _feet(player)
            report["routes"].append({
                "route": name, "reached": reached, "as_expected": all(reached) == expect,
                "end_m": [round(fx, 2), round(fy, 2)], "end_elevation_m": round(elevation_of(player), 2),
                "highest_m": round(max((t[2] for t in trace), default=0.0), 2),
                "worst_feet_off_ground_m": round(max(off, default=0.0), 3),
                "lowest_on_bridge_m": round(min(on_bridge), 2) if on_bridge else None,
                "steps": len(trace)})
        # still standing in the meadow: the wind moves the plants (pixels change with nobody moving)
        _put(game, 24.0, 6.0)
        game.step(180)  # (the camera settles on the player)
        a = game.draw().convert("L")
        game.step(1)
        a2 = game.draw().convert("L")
        game.step(30)
        b = game.draw().convert("L")
        report["still_frames_changed_pixels"] = {
            "1_frame_apart": sum(1 for p, q in zip(a.getdata(), a2.getdata()) if abs(p - q) > 8),
            "30_frames_apart": sum(1 for p, q in zip(a.getdata(), b.getdata()) if abs(p - q) > 8),
            "of": a.width * a.height}
        report["motion_on"] = bool(hd.motion.enabled) if hd else None
        report["wind"] = [round(v, 2) for v in hd.wind.vector] if hd else None
        report["water_bodies"] = len(__import__("engine.water", fromlist=["x"]).bodies_of(game.window))
        for name, (x, y) in PICTURES.items():
            _put(game, x, y)
            game.step(20)
            game.draw().convert("RGB").save(out / f"{prefix}{name}.png")
        counts = []
        for _ in range(3):  # room changes: GPU objects stay as they were
            game.load("packs/core_regions/scenes/start.json")
            game.step(3)
            game.load(ROOM_FILE)
            game.step(3)
            game.window.dispatch_event("on_draw")
            game.window.ctx.gc()
            st = game.window.ctx.stats
            counts.append({k: getattr(st, k)[0] - getattr(st, k)[1] for k in ("buffer", "texture", "framebuffer", "program")})
        report["gl_objects_after_room_changes"] = counts
        report["gl_stable"] = counts[1:] == counts[:-1]
        report["all_routes_as_expected"] = all(r["as_expected"] for r in report["routes"])
        world = game.window.hd2d_world  # navigation: the engine's planner finds a walkable way between the places
        stops = {"start": PLAYER_START, "crossroads": (27.0, 12.0), "bridge's north end": (35.2, 29.6),
                 "pond's east bank": (54.0, 30.0), "hilltop": (12.0, 36.5), "mound": (56.5, 12.7),
                 "cottage door": (19.0, 17.6)}
        report["navigation"] = {f"start -> {name}": len(world.path((*PLAYER_START, 0.0), (x, y, ground(x, y)))) > 0
                                for name, (x, y) in stops.items() if name != "start"}
        report["max_feet_off_ground_m"] = max(r["worst_feet_off_ground_m"] for r in report["routes"])
        _ = math
    finally:
        game.close()
    return report


BREEZE = {"direction": 0.0, "gust": 0.3, "speed": 3.0}  # Studio's Breeze button, as saved in settings.wind


def _as_saved(scene: dict[str, Any], saved: dict[str, Any], shared: dict[str, Any] | None) -> dict[str, Any]:
    """The room as Studio holds it with its one known difference from the file folded back: Studio holds the shared
    player filled in from the project's player prefab; the file keeps a reference (``ops.thin_player``, what Studio
    stores it as)."""
    from engine import project_ops as ops

    players = set(ops.shared_player_ids(saved))
    entities = [ops.thin_player(e, shared) if e.get("id") in players else e for e in scene.get("entities") or []]
    return {**scene, "entities": entities}


def _differences(a: Any, b: Any, at: str = "") -> list[str]:
    """Where two JSON values differ (paths; at most 20)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = [f"{at}.{k}" for k in sorted(set(a) ^ set(b))]
        for k in sorted(set(a) & set(b)):
            out += _differences(a[k], b[k], f"{at}.{k}")
        return out[:20]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in _differences(x, y, f"{at}[{i}]")][:20]
    return [] if a == b else [at or "."]


def reopen(project: Path, out: Path) -> dict[str, Any]:
    """Phase 9: closed and reopened in Studio. The room as saved (structures, water, lights, scatter, wind, motion,
    doors: everything but the shared player, which Studio holds filled in, compared with the file); nothing unsaved
    after opening it; Play (F4) and Stop five times with GPU objects unchanged; a picture."""
    import m20c_material_study as m20c

    from engine import project_ops as ops

    saved = json.loads((project / ROOM_FILE).read_text(encoding="utf-8"))
    d = StudioDriver(project)
    k = d.arcade.key
    try:
        d.button(ROOM)
        d.frame(5)
        scene = d.studio.project.scene()
        hd = (scene.get("settings") or {}).get("hd2d") or {}
        renderer = d.studio.hd2d.renderer
        saved_settings = saved.get("settings") or {}
        report: dict[str, Any] = {
            "same_as_saved": scene == saved, "shared_player_filled_in": sorted(ops.shared_player_ids(saved)),
            "differences_apart_from_the_player": _differences(_as_saved(scene, saved, d.studio.project.player), saved),
            "unsaved_after_opening": sorted(d.studio.project.dirty),
            "structures": len(hd.get("structures") or []), "scatter": sum(len(v) for v in (hd.get("scatter") or {}).values()),
            "water": sum(1 for e in scene["entities"] if "WaterSurface" in (e.get("behaviours") or [])),
            "lamps": sum(1 for lt in scene.get("lights") or [] if lt.get("type") != "ambient"),
            # wind is the room's (settings.wind); motion is settings.hd2d.motion, where {} is "on, as the kit sets it"
            "wind_saved": saved_settings.get("wind"), "wind_reopened": (scene.get("settings") or {}).get("wind"),
            "wind_drawn": [round(v, 2) for v in renderer.wind.vector] if renderer is not None else None,
            "motion_saved": (saved_settings.get("hd2d") or {}).get("motion"), "motion_reopened": hd.get("motion"),
            "motion_drawn_on": bool(renderer.motion.enabled) if renderer is not None else None,
            "drawn": renderer is not None and renderer.scatter is not None}
        assert not report["differences_apart_from_the_player"], report["differences_apart_from_the_player"]
        assert report["wind_saved"] == report["wind_reopened"] == BREEZE, report
        assert report["motion_saved"] == report["motion_reopened"] is not None and report["motion_drawn_on"], report
        counts, modes = [], []
        for _ in range(5):
            for _press in range(2):
                d.key(k.F4)
                d.frame(10)
                modes.append(d.studio.mode)
            counts.append(d.gl_counts())
        report["play_stop_modes"] = modes
        report["play_stop_gl_stable"] = counts[1:] == counts[:-1]
        m20c._look_at(d, 32.0, 22.0, 72.0)
        d.picture(out / "09_reopened.png")
        report["unsaved_at_end"] = sorted(d.studio.project.dirty)
    finally:
        d.close()
    return report


def export(project: Path, out: Path) -> dict[str, Any]:
    """Phase 10: exported with ``mesh export build`` and run outside Studio, with the bundle's own engine (a hidden
    window): it starts in the Village; walking east along its road goes through the passage into Lakeside; pictures."""
    import shutil
    import subprocess

    bundle = out / "export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    report: dict[str, Any] = {"export_code": built.returncode, "export_tail": (built.stdout + built.stderr)[-400:]}
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from hd2d_floors_demo import _feet, hold_key
from m20a_terrain_study import _put
from pathlib import Path
game = HiddenGame(Path({str(bundle)!r}), size=(1280, 720))
row = {{"engine_from": engine.__file__}}
try:
    game.window.load_scene(game.window.engine_config.start_scene or "packs/core_regions/scenes/start.json")
    game.step(20)
    row["started_in"] = game.window.scene_controller.current_scene_path
    p = _put(game, 33.0, 7.0)
    hold_key(game, p, game.arcade.key.RIGHT, 0, 39.5, 400)
    game.step(40)
    row["after_walking_east"] = game.window.scene_controller.current_scene_path
    p = game.player()
    row["arrived_at_m"] = [round(v, 2) for v in _feet(p)]
    hold_key(game, p, game.arcade.key.UP, 1, 11.0, 600)
    row["walked_to_m"] = [round(v, 2) for v in _feet(p)]
    game.step(30)
    game.draw().convert("RGB").save({str(out / "10_exported_game.png")!r})
finally:
    game.close()
print(json.dumps(row))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k2: v for k2, v in os.environ.items() if k2 not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        report["bundle_run"] = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        report["bundle_run"] = {"failed": (ran.stdout[-600:] + ran.stderr[-1500:])}
    report["bundle_files"] = sum(1 for f in bundle.rglob("*") if f.is_file())
    return report


ORDER = ["room", "ground", "water", "build", "nature", "finish", "doors"]


def everything(project: Path, out: Path) -> dict[str, Any]:
    """Every authoring phase in order, on a project fresh from ``mesh new --template hd2d_rpg``."""
    report = {}
    for name in ORDER:
        report[name] = PHASES[name](project, out)
        _write(out / f"{name}.json", report[name])
    return report


PHASES: dict[str, Callable[[Path, Path], dict[str, Any]]] = {"room": room, "ground": ground, "water": water, "build": build, "nature": nature, "finish": finish,
          "doors": doors, "play": play, "reopen": reopen, "export": export, "all": everything}


def main() -> None:
    phase, project, out = sys.argv[1], Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = PHASES[phase](project, out)
    _write(out / f"{phase}.json", report)
    print(json.dumps(report, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
