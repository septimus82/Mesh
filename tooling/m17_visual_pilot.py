"""Milestone 17 Stage 1: the HD-2D visual-quality pilot, compared in Mesh's own renderer (hidden windows only).

    py -3.13 tooling/m17_visual_pilot.py compare OUT

Three projects from the HD-2D RPG (Preview) template, identical except for the assets under test:

- ``A`` the template as it ships (procedural starter cottage, the HD-2D hero sheet);
- ``B`` the pilot cottage (tooling/hd2d_assets/pilot_m17/models/cottage_m17.glb) in place of the starter cottage: the
  same structure id, position and turn, so its floors, door and navigation are where they were;
- ``C`` B plus the pilot hero (tooling/hd2d_assets/pilot_m17/characters/hero_m17.png) as the player.

Each is played with the same key-driven walk and photographed at the same spots, with the same camera, sun, lamps,
resolution and character placement: gameplay distance (the template's 12 degree camera, 2x at 720 lines) and close up
(the same camera at 4x). It also records a short walking clip of each, the frame cost, GL objects before and after,
and the visible pixels of the player at the cottage. Side-by-side pictures and OUT/pilot.json.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402  # the walk, the shots, the grids
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PILOT = REPO / "tooling" / "hd2d_assets" / "pilot_m17"
COTTAGE_GLB = PILOT / "models" / "cottage_m17.glb"
HERO_SHEET = PILOT / "characters" / "hero_m17.png"
CLOSE_VIEW = 5.625  # m top to bottom at the player: 128 px per m at 720 lines, 4x the art (the close-up)
SPOTS = {  # name: (description, route of (key, axis, target m))
    "cottage": ("beside the cottage door", [("UP", 1, 8.5), ("LEFT", 0, 11.5)]),
    "path": ("on the path south-east of the cottage", [("RIGHT", 0, 13.5), ("DOWN", 1, 7.0)]),
    "centre": ("the village centre", [("RIGHT", 0, 20.0), ("UP", 1, 15.0)]),
}
VARIANTS = {"A": "Starter cottage, starter hero (as shipped)", "B": "Pilot cottage, starter hero",
            "C": "Pilot cottage, pilot hero"}


def _set_cottage(project: Path) -> dict[str, Any]:
    """Put the pilot cottage where the starter one stands (same id, so the same floor names and door)."""
    shutil.copyfile(COTTAGE_GLB, project / "assets" / "models" / "cottage_m17.glb")
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    entry = next(st for st in scene["settings"]["hd2d"]["structures"] if st["id"] == "cottage")
    entry["model"] = "assets/models/cottage_m17.glb"
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return dict(entry)


def _set_hero(project: Path) -> None:
    """The pilot hero drawn as the player: its sheet in place of this project's copy of the HD-2D hero (same 4x4
    sheet of 32x48 frames, so the player's Animator clips are unchanged). The engine's own sheet is untouched."""
    shutil.copyfile(HERO_SHEET, project / "assets" / "sprites" / "hd2d_hero.png")


def make_variant(out: Path, name: str) -> Path:
    project: Path = study.new_project(out, f"project_{name}", stage6a=False)
    if name in ("B", "C"):
        _set_cottage(project)
    if name == "C":
        _set_hero(project)
    return project


def _close_up(game: HiddenGame, path: Path) -> None:
    """The same camera (pitch, lens, follow) brought in to 4x, for one picture."""
    hd = game.window.hd2d_renderer
    camera = hd.camera
    distance = camera.distance
    camera.distance = CLOSE_VIEW / 2 / math.tan(math.radians(camera.fov) / 2)
    try:
        game.draw().convert("RGB").save(path)
    finally:
        camera.distance = distance


def run_variant(out: Path, name: str, project: Path) -> dict[str, Any]:
    game = HiddenGame(project, size=study.SIZE)
    result: dict[str, Any] = {"label": VARIANTS[name]}
    try:
        ctx = game.window.ctx
        game.load(f"{SCENES}/start.json")
        game.step(90)
        result["gl_after_load"] = _gl_counts(ctx)
        result["hd2d_error"] = getattr(game.window, "hd2d_error", None)
        walk = study.Walk(game, out, name)
        for spot, (_text, route) in SPOTS.items():
            for key, axis, target in route:
                walk.go(key, axis, target, film=spot == "cottage")
            walk.shot(spot)
            _close_up(game, out / f"{name}_{spot}_close.png")
        result["frame"] = study.frame_cost(game, 120)
        result["renderer"] = {k: game.window.hd2d_renderer.stats()[k] for k in ("draw_calls", "triangles", "texture_bytes")}
        game.load(f"{SCENES}/start.json")  # a room reload must not grow GL objects
        game.step(30)
        game.draw()
        ctx.gc()
        result["gl_after_reload"] = _gl_counts(ctx)
        result["spots"] = walk.spots
        result["_clip"] = walk.clip
    finally:
        game.close()
    return result


def compare(out: Path) -> dict[str, Any]:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    results = {name: run_variant(out, name, make_variant(out, name)) for name in VARIANTS}
    for pair, names in (("cottage", ("A", "B")), ("character", ("B", "C")), ("before_after", ("A", "C"))):
        for spot in SPOTS:
            for suffix in ("", "_close"):
                pictures = [Image.open(out / f"{n}_{spot}{suffix}.png") for n in names]
                study.grid(pictures, [VARIANTS[n] for n in names], (study.SIZE[0] // 2, study.SIZE[1] // 2)).save(
                    out / f"compare_{pair}_{spot}{suffix}.png")
    clips = [results[n].pop("_clip") for n in VARIANTS]
    length = min(len(c) for c in clips)
    frames = [study.grid([c[i] for c in clips], [VARIANTS[n] for n in VARIANTS], (study.SIZE[0] // 4, study.SIZE[1] // 4))
              for i in range(length)]
    if frames:
        frames[0].save(out / "walk_compare.webp", save_all=True, append_images=frames[1:], duration=67, loop=0, quality=85)
    report = {"size": list(study.SIZE), "spots": {k: v[0] for k, v in SPOTS.items()}, "variants": results}
    (out / "pilot.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["compare"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report = compare(args.out)
    print(json.dumps({n: {k: v for k, v in r.items() if k != "spots"} for n, r in report["variants"].items()}, indent=1,
                     default=str))


if __name__ == "__main__":
    main()
