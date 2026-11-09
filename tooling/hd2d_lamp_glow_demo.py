"""M17-L3 E2: a lamp lights its own lamp head, checked in real frames of the game (a hidden window).

The four rooms of the E2 investigation, rebuilt from the hd2d_rpg template's starter kit (no Lakeside file is read):

- ``village``: the template village as shipped (its two lamp posts lit);
- ``lakeside``: Lakeside Village's kit cottage and four lamp posts at Lakeside's positions, its lamps on (Lakeside
  ships them off); lamp 4 stands 0.2 m inside the cottage's south-east corner;
- ``fixtures``: #459's fixture room (tooling/hd2d_lighting_demo.fixture_room), with its independent panel 0.23 m
  from lamp A;
- ``cottage``: the template cottage interior, its ceiling lamp hung in no fixture.

``check`` draws each room twice, as E2 draws it and with the lamp-head association switched off (E1's frame), and
reports what changed: only the lamp heads' own pixels may differ. Then the village with every lamp off, in other
colours and intensities, and through Mesh Studio (an edit, Ctrl+S, reopen).

    py tooling/hd2d_lamp_glow_demo.py <new folder>
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

SCENES = "packs/core_regions/scenes"
LAKESIDE_POSTS = {"lamp_post": (800.0, 326.4), "lamp_post_2": (940.8, 441.6), "lamp_post_3": (1043.2, 755.2),
                  "lamp_post_4": (678.4, 585.6)}  # px, as Lakeside Village places them
LAKESIDE_LAMPS = ((800.0, 326.0), (941.0, 442.0), (1043.0, 755.0), (678.0, 586.0))  # px; elevation 76.8, #ffcc88
LAKESIDE_COTTAGE = {"cutaway": True, "id": "cottage", "model": "assets/models/cottage.glb", "x": 608.0, "y": 640.0}
ROOMS = ("village", "lakeside", "fixtures", "cottage")


def build(project: Path) -> dict[str, str]:
    """A new hd2d_rpg project at ``project`` with the four rooms written; room -> scene path."""
    import hd2d_lighting_demo

    from engine.project_scaffold import create_project

    create_project(project, "Lamp glow", "hd2d_rpg")
    scenes = project / SCENES
    village = json.loads((scenes / "start.json").read_text(encoding="utf-8"))
    lake = json.loads(json.dumps(village))
    lake["settings"]["hd2d"]["structures"] = [dict(LAKESIDE_COTTAGE)] + [
        {"id": key, "model": "assets/models/lamp_post.glb", "x": x, "y": y} for key, (x, y) in LAKESIDE_POSTS.items()]
    lake["lights"] = [{"color": "#9aa6d0", "id": "sky", "mode": "soft", "type": "ambient"}] + [
        {"color": "#ffcc88", "elevation": 76.8, "mode": "soft", "radius": 224.0, "x": x, "y": y}
        for x, y in LAKESIDE_LAMPS]
    for e in lake["entities"]:
        if e.get("prefab_id") == "player":
            e["x"], e["y"] = 560.0, 480.0
    (scenes / "glow_lakeside.json").write_text(json.dumps(lake, indent=2), encoding="utf-8")
    return {"village": f"{SCENES}/start.json", "lakeside": f"{SCENES}/glow_lakeside.json",
            "fixtures": hd2d_lighting_demo.fixture_room(project), "cottage": f"{SCENES}/cottage.json"}


def room_settings(project: Path, scene_path: str) -> tuple[Any, dict[str, Any]]:
    """A room's HD-2D settings with its lights, as the game reads them (engine.hd2d.runtime), and its models."""
    from engine.hd2d.glb import load_glb
    from engine.hd2d.settings import parse_hd2d, parse_scene_lights

    scene = json.loads((project / scene_path).read_text(encoding="utf-8"))
    settings = scene["settings"]
    hd2d = dataclasses.replace(parse_hd2d(settings["hd2d"]), **parse_scene_lights(scene.get("lights"), settings))
    models = {st.model: load_glb(project / st.model) for st in hd2d.structures}
    return hd2d, models


def heads(project: Path, scene_path: str) -> list[dict[str, Any]]:
    """Per lamp the room draws: where it is and its lamp head (lighting.lamp_head): structure, node, materials."""
    from engine.hd2d.lighting import lamp_head
    from engine.hd2d.settings import MAX_LIGHTS
    from engine.hd2d.settings import PIXELS_PER_METRE as PPM

    hd2d, models = room_settings(project, scene_path)
    out = []
    for lamp in hd2d.lights[:MAX_LIGHTS]:
        head = lamp_head((lamp.x / PPM, lamp.y / PPM, lamp.elevation / PPM), hd2d.structures, models)
        row: dict[str, Any] = {"at_px": [lamp.x, lamp.y, lamp.elevation], "head": None}
        if head is not None:
            st = next(s for s in hd2d.structures if s.id == head[0])
            parts = models[st.model].parts
            row["head"] = {"structure": head[0], "parts": sorted(head[1]),
                           "nodes": sorted({parts[i].node for i in head[1]}),
                           "materials": sorted({parts[i].material.name for i in head[1]})}
        out.append(row)
    return out


@contextlib.contextmanager
def without_lamp_heads() -> Iterator[None]:
    """E1's frame: the renderer finds no lamp head (so it splits nothing and adds no glow)."""
    import engine.hd2d.renderer as renderer

    original = renderer.lamp_head
    renderer.lamp_head = lambda *_args, **_kw: None
    try:
        yield
    finally:
        renderer.lamp_head = original


def head_boxes(game: Any) -> list[tuple[int, int, int, int]]:
    """Each lamp head's box on the last frame (px, image rows from the top), a pixel round it."""
    from engine.hd2d.lighting import lamp_head
    from engine.hd2d.settings import MAX_LIGHTS
    from engine.hd2d.settings import PIXELS_PER_METRE as PPM

    r = game.window.hd2d_renderer
    vp, (w, h) = r.last_vp, game.window.get_framebuffer_size()
    boxes = []
    for lamp in r.settings.lights[:MAX_LIGHTS]:
        head = lamp_head((lamp.x / PPM, lamp.y / PPM, lamp.elevation / PPM), r.settings.structures, r.models)
        if head is None:
            continue
        st = next(s for s in r.settings.structures if s.id == head[0])
        from engine.hd2d.renderer import _placement

        m = _placement(st.x / PPM, st.y / PPM, st.elevation / PPM, st.rotation, st.scale)
        xs, ys = [], []
        for i in head[1]:
            v = r.models[st.model].parts[i].vertices
            for k in range(0, len(v), 8):
                p = [sum(m[row][c] * (v[k + c] if c < 3 else 1.0) for c in range(4)) for row in range(3)] + [1.0]
                clip = [sum(vp[row][c] * p[c] for c in range(4)) for row in range(4)]
                xs.append((clip[0] / clip[3] * 0.5 + 0.5) * w)
                ys.append((1.0 - (clip[1] / clip[3] * 0.5 + 0.5)) * h)
        boxes.append((int(min(xs)) - 1, int(min(ys)) - 1, int(max(xs)) + 2, int(max(ys)) + 2))
    return boxes


def frame(game: Any, scene_path: str) -> Any:
    """The room's 3D world as the renderer draws it (no HUD: a room's name card or a fade shows over it for a while
    after a room is entered), settled: loaded, 30 updates, its motion at the same moment every time."""
    from PIL import Image

    game.load(scene_path)
    game.step(30)
    game.window.motion_time = 0.0
    if hasattr(game.window, "water_time"):
        game.window.water_time = 0.0
    game.draw()
    w, h = game.window.get_framebuffer_size()
    data = game.window.hd2d_renderer.draw(read=True)
    return Image.frombytes("RGB", (w, h), bytes(data)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def changed(a: Any, b: Any, boxes: list[tuple[int, int, int, int]]) -> dict[str, Any]:
    """Pixels that differ between two frames: how many, how many outside every lamp head's box, and per head box the
    changed pixels' count, mean colour in ``b`` and mean luma before and after."""
    pa, pb = a.load(), b.load()
    w, h = a.size
    outside = 0
    heads: list[dict[str, Any]] = [{"changed": 0, "rgb": [0, 0, 0], "luma": [0.0, 0.0], "lumas": []} for _ in boxes]
    for y in range(h):
        for x in range(w):
            if pa[x, y] == pb[x, y]:
                continue
            k = next((i for i, (x0, y0, x1, y1) in enumerate(boxes) if x0 <= x < x1 and y0 <= y < y1), None)
            if k is None:
                outside += 1
                continue
            head = heads[k]
            head["changed"] += 1
            for c in range(3):
                head["rgb"][c] += pb[x, y][c]
            head["luma"][0] += 0.299 * pa[x, y][0] + 0.587 * pa[x, y][1] + 0.114 * pa[x, y][2]
            head["luma"][1] += 0.299 * pb[x, y][0] + 0.587 * pb[x, y][1] + 0.114 * pb[x, y][2]
            head["lumas"].append(0.299 * pb[x, y][0] + 0.587 * pb[x, y][1] + 0.114 * pb[x, y][2])
    for head in heads:
        n = head["changed"]
        head["rgb"] = [round(c / n, 1) for c in head["rgb"]] if n else None
        head["luma"] = [round(v / n, 1) for v in head["luma"]] if n else None
        lumas = sorted(head.pop("lumas"))  # its darkest and brightest tenth: the frame and the glass
        head["luma_p10_p90"] = [round(lumas[n // 10], 1), round(lumas[(9 * n) // 10], 1)] if n else None
    return {"changed": outside + sum(hd["changed"] for hd in heads), "outside_heads": outside, "per_head": heads}


def village_variant(project: Path, name: str, change: Any) -> str:
    """The village with its lights changed by ``change(lights)``; its scene path."""
    from engine import project_ops as ops

    scene = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    scene["lights"] = change(scene["lights"])
    if name.endswith(("_noon", "_evening", "_night")):
        scene = ops.set_hd2d_sun(scene, preset=name.rsplit("_", 1)[1])
    path = f"{SCENES}/glow_{name}.json"
    (project / path).write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return path


def _lamps(lights: list[dict], **change: Any) -> list[dict]:
    return [li if li.get("type") == "ambient" else {**li, **change} for li in lights]


VARIANTS = {  # village lights -> (name, change)
    "off": lambda li: _lamps(li, enabled=False),
    "blue_east": lambda li: [li[0], li[1], {**li[2], "color": "#5080ff"}],
    "dim_west": lambda li: [li[0], {**li[1], "intensity": 0.5}, li[2]],
    "bright_west": lambda li: [li[0], {**li[1], "intensity": 3.0}, li[2]],
    "zero_west": lambda li: [li[0], {**li[1], "intensity": 0.0}, li[2]],
    "west_off": lambda li: [li[0], {**li[1], "enabled": False}, li[2]],
}


def check(folder: Path) -> dict[str, Any]:
    import hd2d_demo

    folder.mkdir(parents=True, exist_ok=False)
    project = folder / "game"
    rooms = build(project)
    report: dict[str, Any] = {"heads": {room: heads(project, path) for room, path in rooms.items()}}
    paths = {f"variant_{name}": village_variant(project, name, change) for name, change in VARIANTS.items()}
    game = hd2d_demo.HiddenGame(project, size=(960, 540))
    try:
        for label, path in [*rooms.items(), *paths.items()]:
            glowing = frame(game, path)
            boxes = head_boxes(game)
            stats = game.window.hd2d_renderer.stats()
            with without_lamp_heads():
                plain = frame(game, path)
                plain_stats = game.window.hd2d_renderer.stats()
            report[label] = {**changed(plain, glowing, boxes), "boxes": boxes,
                             "lamp_head_draws": stats["lamp_head_draws"], "static_draws": stats["static_draws"],
                             "static_draws_e1": plain_stats["static_draws"], "buffer_bytes": stats["buffer_bytes"],
                             "buffer_bytes_e1": plain_stats["buffer_bytes"]}
    finally:
        game.close()
    report["studio"] = studio_check(project)
    return report


def studio_check(project: Path) -> dict[str, Any]:
    """Mesh Studio: the village's heads glow in the edit view; switching the east lamp off (an edit) leaves one; saved
    with Ctrl+S and reopened, still one."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    out: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        d.frame()
        out["heads_in_edit_view"] = d.renderer.stats()["lamp_head_draws"]
        d.studio._edit(lambda s: ops.set_light(s, 2, enabled=False), "East lamp off.")
        d.frame()
        out["heads_after_edit"] = d.renderer.stats()["lamp_head_draws"]
        d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
        out["saved"] = not d.studio.project.is_dirty
        d.key(d.arcade.key.Z, d.arcade.key.MOD_CTRL)
        d.frame()
        out["heads_after_undo"] = d.renderer.stats()["lamp_head_draws"]
        d.key(d.arcade.key.Y, d.arcade.key.MOD_CTRL)
        d.frame()
        out["heads_after_redo"] = d.renderer.stats()["lamp_head_draws"]
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        d.frame()
        out["heads_after_reopen"] = d.renderer.stats()["lamp_head_draws"]
    finally:
        d.close()
    return out


if __name__ == "__main__":
    result = check(Path(sys.argv[1]))
    (Path(sys.argv[1]) / "report.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
