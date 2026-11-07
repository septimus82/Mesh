"""Visual polish check (Milestone 12.2): one small room as the game draws it and as Mesh Studio shows it, rendered
in hidden windows (tooling/scene_snapshot.py): no mouse, no keyboard, nothing on the owner's screen.

The disposable room: a door (its picture), an invisible passage through a gap in the left wall, a "map artwork"
door over an opening painted in the top wall, a villager, a rock and a bush on the walls layer, an L of wall tiles
and two lamps. Checked:

* in the game, the door is drawn with no round shadow under it; the passage and the map-artwork door are not
  drawn at all (they still work: tests/test_door_presentation.py) and leave their areas exactly as the same room
  without them; the villager and the player keep their shadows under their feet;
* the rock and the bush cast their outlines (polygon occluders), the walls as rectangles;
* in Mesh Studio, the passage's area is outlined (editor only).

Run from the repo root:  py -3.13 tooling/visual_polish_check.py [--out DIR]   Writes DIR/report.json and pictures.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ROWS = 15
LAMPS = [((6, 7), "Warm", 260), ((14, 8), "Cold", 240)]
L_WALL = [(9, r) for r in range(3, 7)] + [(c, 6) for c in range(10, 13)]
ROCK, BUSH, PATH = 13, 14, 3  # starter gids
PASSAGE_GAP = [(0, 7), (0, 8)]  # in the left border wall
ART_GAP = [(4, 0)]  # in the top border wall: the "map artwork" door goes over it


def world(cell: tuple[float, float]) -> tuple[float, float]:
    return cell[0] * 32 + 16.0, (ROWS - cell[1]) * 32 - 16.0


def _lamp(scene: dict[str, Any], *, x: float, y: float, colour: str, radius: float) -> dict[str, Any]:
    from engine import project_ops as ops

    out: dict[str, Any] = ops.add_light(scene, x, y, color=colour, radius=radius)[0]
    return out


def _styled(scene: dict[str, Any], *, door: str, style: str, size: tuple[int, int]) -> dict[str, Any]:
    from engine import project_ops as ops

    return ops.set_door(ops.set_door(scene, door, style=style), door, width=size[0], height=size[1])


def _door_colour_pixels(image: Any) -> int:
    """Pixels in Studio's door-outline colour."""
    pixels: Any = image.getdata()
    return len([px for px in pixels if abs(px[0] - 240) <= 12 and abs(px[1] - 210) <= 12 and abs(px[2] - 140) <= 12])


def build(root: Path, *, passages: bool = True) -> str:
    from engine import project_ops as ops
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    create_project(root, "Yard", template_id="blank")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    yard, cellar, garden, attic = (project.add_room(name) for name in ("Yard", "Cellar", "Garden", "Attic"))
    project.edit_scene(lambda s: ops.set_room_lighting(s, enabled=True, ambient=[60, 70, 110, 255], shadows="hard"), yard)
    for cell, colour, radius in LAMPS:
        x, y = world(cell)
        project.edit_scene(partial(_lamp, x=x, y=y, colour=colour, radius=radius), yard)

    def paint(layer: str, cells: list[tuple[int, int]], gid: int) -> None:
        project.edit_scene(lambda s: ops.paint_tiles(s, layer, cells, gid), yard)

    paint(ops.WALLS, L_WALL, ops.STARTER_WALL)
    paint(ops.WALLS, [(5, 10)], ROCK)
    paint(ops.WALLS, [(16, 5)], BUSH)
    paint(ops.WALLS, PASSAGE_GAP + ART_GAP, 0)
    paint(ops.GROUND, PASSAGE_GAP + ART_GAP, PATH)
    prefab = next(p for p in json.loads((root / "assets" / "prefabs.json").read_text(encoding="utf-8"))
                  if p.get("id") == "player")["entity"]

    def people(scene: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = json.loads(json.dumps(scene))
        for entity in out.get("entities", []):
            if entity.get("prefab_id") == "player" or entity.get("tag") == "player":
                entity["x"], entity["y"] = world((8, 9))
        npc = json.loads(json.dumps(prefab))
        x, y = world((12, 10))
        npc.update({"id": "yard_villager", "name": "Villager", "tag": "npc", "x": x, "y": y, "behaviours": ["Animator"]})
        npc["behaviour_config"] = {"Animator": npc["behaviour_config"]["Animator"]}
        out["entities"].append(npc)
        return out

    project.edit_scene(people, yard)
    project.link_rooms(yard, world((17, 3)), cellar, world((10, 7)))
    if passages:
        for target, at, style, size in ((garden, (0, 7.5), "passage", (32, 64)), (attic, (4, 0), "map_art", (32, 32))):
            project.link_rooms(yard, world(at), target, world((10, 7)))
            door = next(e for e in project.scene(yard)["entities"]
                        if ((e.get("behaviour_config") or {}).get("SceneTransition") or {}).get("target_scene") == target)
            project.edit_scene(partial(_styled, door=door["id"], style=style, size=size), yard)
    project.save()
    world_doc = json.loads((root / config["world_file"]).read_text(encoding="utf-8"))
    return str(world_doc["scenes"][yard]["path"])


def render(project: Path, scene: str, out: Path, *extra: str) -> dict[str, Any]:
    """One hidden-window render in its own process (a GL window per process; nothing is shown)."""
    done = subprocess.run([sys.executable, str(REPO / "tooling" / "scene_snapshot.py"), str(project), scene, str(out), *extra],
                          cwd=REPO, capture_output=True, text=True, env=os.environ.copy())
    text = done.stdout[done.stdout.find("{"):]
    if done.returncode != 0 or not text:
        raise RuntimeError(f"render failed: {done.stderr[-800:]}")
    info: dict[str, Any] = json.loads(text)
    return info


def run(out: Path) -> int:
    from PIL import Image, ImageChops

    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    os.environ.update({"MESH_USER_DIR": str(work / "user"), "MESH_PROJECTS_DIR": str(work / "projects")})
    scene = build(work / "yard")
    build(work / "yard_plain", passages=False)
    results: dict[str, Any] = {}
    failures: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(f"[{'PASS' if ok else 'FAIL'}] {what}", flush=True)
        if not ok:
            failures.append(what)

    game = render(work / "yard", scene, out / "game.png")
    render(work / "yard_plain", scene, out / "game_without_passages.png")
    studio = render(work / "yard", scene, out / "studio.png", "--studio", "--seconds", "0.5", "--size", "1280", "720")
    selected = render(work / "yard", scene, out / "studio_passage_selected.png", "--studio", "--select", "Door to Garden",
                      "--tab", "look", "--seconds", "0.5", "--size", "1280", "720")
    sprites = {s["name"]: s for s in game["sprites"]}
    results["game_sprites"] = sprites
    check(sprites["Door to Cellar"]["drawn"] and not sprites["Door to Cellar"]["ground_shadow"],
          "the door is drawn, with no round shadow under it")
    for name in ("Door to Garden", "Door to Attic"):
        check(sprites[name]["visible"] and not sprites[name]["drawn"] and not sprites[name]["ground_shadow"],
              f"{name}: there to walk into, not drawn, no shadow")
    check(all(sprites[n]["ground_shadow"] for n in ("Player", "Villager")), "the player and the villager keep their shadows")
    check(all(not s["drawn"] for s in game["sprites"] if str(s["name"]).startswith("Arrival")), "arrival spots aren't drawn")
    stats = game["lighting"]
    results["lighting"] = stats
    check(stats.get("character_shadows", 0) >= 2 and stats.get("characters") == 2,
          "lamp shadows from the player and the villager only (no door or passage among the casters)")
    from engine.lighting.occluders import OCCLUDER_CACHE, build_occluders_from_scene_payload

    OCCLUDER_CACHE.invalidate()
    room = json.loads((work / "yard" / scene).read_text(encoding="utf-8"))
    occluders = build_occluders_from_scene_payload(room, scene_path=str(work / "yard" / scene), revision=1)
    OCCLUDER_CACHE.invalidate()
    polys = [o for o in occluders if o["type"] == "poly"]
    check(len(polys) == 2, f"the rock and the bush cast their outlines ({len(polys)} outline occluders)")
    # The passage areas look exactly as the same room without the passages (camera follows the same player).
    a, b = Image.open(out / "game.png").convert("RGB"), Image.open(out / "game_without_passages.png").convert("RGB")
    zoom, (cx, cy) = game["zoom"], game["camera"]
    biggest = {}
    for name, cell, (w, h) in (("passage", (0, 7.5), (32, 64)), ("map artwork", (4, 0), (32, 32))):
        wx, wy = world(cell)
        sx, sy = a.width / 2 + (wx - cx) * zoom, a.height / 2 - (wy - cy) * zoom
        box = (int(sx - w * zoom / 2 - 4), int(sy - h * zoom / 2 - 4), int(sx + w * zoom / 2 + 4), int(sy + h * zoom / 2 + 4))
        diff: Any = ImageChops.difference(a.crop(box), b.crop(box)).getextrema()
        biggest[name] = max(high for _low, high in diff)
        check(biggest[name] <= 2, f"nothing of the {name} is drawn in the game (differs by up to {biggest[name]})")
    results["passage_area_difference"] = biggest
    # In the Studio its area is outlined (the door colour), in the game it is not.
    s_img = Image.open(out / "studio_passage_selected.png").convert("RGB")
    outline, in_game = _door_colour_pixels(s_img), _door_colour_pixels(a)
    check(outline > 100 and in_game < outline / 10, f"door areas outlined in Studio ({outline} px), not in the game ({in_game} px)")
    results["studio"] = {"selected": selected.get("lighting", {}).get("renderer"), "plain": studio.get("lighting", {}).get("renderer")}
    results["failures"] = failures
    (out / "report.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(f"{'all checks passed' if not failures else f'{len(failures)} failed'}; pictures and report in {out}")
    return 0 if not failures else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "visual_polish_check")
    raise SystemExit(run(parser.parse_args().out))
