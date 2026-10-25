"""Milestone 17: the HD-2D visual-quality pilot, compared in Mesh's own renderer (hidden windows only).

    py -3.13 tooling/m17_visual_pilot.py compare OUT --set cottage
    py -3.13 tooling/m17_visual_pilot.py compare OUT --set hero [--hero KEY LABEL SHEET ...]

Every variant is a project from the HD-2D RPG (Preview) template, identical except for the assets under test, played
with the same key-driven walk and photographed at the same spots with the same camera, sun, lamps, resolution and
character placement.

- ``cottage``: A the starter cottage; B the pilot geometry with the starter textures only
  (pilot_m17/models/cottage_m17_geo.glb); C the same geometry with the PixelLab materials (models/cottage_m17.glb).
  Each is swapped in under the same structure id, position and turn, so floors, door and navigation are unchanged.
- ``hero``: H0 the starter hero; H1 the Stage 1 PixelLab hero as generated; then each ``--hero`` sheet (the same 4x4
  sheet of 32x48 frames), all beside the starter cottage.
- ``combined``: as shipped, against B and C each with the Stage 1B repaired hero (characters/hero_m17_h4.png).

Gameplay first: the composites ``{set}_{spot}.png`` and the walking clip are 1:1 crops of the 720-line game picture
(the art at 2x), never resampled. ``{set}_{spot}_close.png`` are 1:1 crops of the same camera brought in to 4x.
``{set}_hero_{spot}.png`` puts the player of every variant side by side at 1:1, with a 4x enlargement below (labelled).
OUT/{set}.json holds, per variant: the player's pixels and edge contrast against what is behind it at every spot,
the frame cost, renderer stats and GL objects after load and after a room reload.
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
CLOSE_VIEW = 5.625  # m top to bottom at the player: 128 px per m at 720 lines, 4x the art (the close-up)
CROP = (640, 360)  # the composites: this much of each picture around the player, at 1:1
CLOSE_CROP = {"cottage": ((800, 600), (-140, -230)), "combined": ((800, 600), (-140, -230)),
              "hero": ((640, 360), (0, -80))}  # size; centre from the feet
WALK_CROP = (384, 216)
FILMED = ("cottage", "path")  # the walking clip: these routes walk up, left, right and down
HERO_CROP = (64, 96)
SPOTS = {  # name: (description, route of (key, axis, target m))
    "cottage": ("beside the cottage door", [("UP", 1, 8.5), ("LEFT", 0, 11.5)]),
    "path": ("on the path south-east of the cottage", [("RIGHT", 0, 13.5), ("DOWN", 1, 7.0)]),
    "centre": ("the village centre", [("RIGHT", 0, 20.0), ("UP", 1, 15.0)]),
}
Variant = tuple[str, str, Path | None, Path | None]  # key, label, cottage model, hero sheet (None: the starter's)
SETS: dict[str, list[Variant]] = {
    "cottage": [("A", "A: starter cottage", None, None),
                ("B", "B: new geometry, starter textures", PILOT / "models" / "cottage_m17_geo.glb", None),
                ("C", "C: new geometry, PixelLab materials", PILOT / "models" / "cottage_m17.glb", None)],
    "hero": [("H0", "H0: starter hero", None, None),
             ("H1", "H1: Stage 1 PixelLab hero", None, PILOT / "characters" / "hero_m17.png")],
    "combined": [("A_H0", "A + H0: as shipped", None, None),
                 ("B_H4", "B + H4: geometry, starter textures, repaired hero",
                  PILOT / "models" / "cottage_m17_geo.glb", PILOT / "characters" / "hero_m17_h4.png"),
                 ("C_H4", "C + H4: geometry, PixelLab materials, repaired hero",
                  PILOT / "models" / "cottage_m17.glb", PILOT / "characters" / "hero_m17_h4.png")],
}


def _set_cottage(project: Path, model: Path) -> None:
    """The pilot cottage where the starter one stands (same id, so the same floor names and door)."""
    shutil.copyfile(model, project / "assets" / "models" / model.name)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    entry = next(st for st in scene["settings"]["hd2d"]["structures"] if st["id"] == "cottage")
    entry["model"] = f"assets/models/{model.name}"
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")


def _set_hero(project: Path, sheet: Path) -> None:
    """A hero sheet in place of this project's copy of the HD-2D hero (the same 4x4 sheet of 32x48 frames, so the
    player's Animator clips are unchanged). The engine's own sheet is untouched."""
    shutil.copyfile(sheet, project / "assets" / "sprites" / "hd2d_hero.png")


def make_variant(out: Path, variant: Variant) -> Path:
    key, _label, model, sheet = variant
    project: Path = study.new_project(out, f"project_{key}", stage6a=False)
    if model:
        _set_cottage(project, model)
    if sheet:
        _set_hero(project, sheet)
    return project


def _crop(image: Any, x: float, y: float, size: tuple[int, int]) -> Any:
    """``size`` of ``image`` centred on (x, y) px from the top-left, kept inside the picture; no resampling."""
    left = min(max(0, round(x - size[0] / 2)), image.width - size[0])
    top = min(max(0, round(y - size[1] / 2)), image.height - size[1])
    return image.crop((left, top, left + size[0], top + size[1]))


class Walk1x(study.Walk):
    """The study's walk, filmed as 1:1 crops around the player (the game picture at its own scale)."""

    def _film(self) -> None:
        hd = self.game.window.hd2d_renderer
        fx, fy = study._feet(self.player)
        sx, sy = self._screen(fx, fy, hd.elevation_of(self.player) / 32)
        self.track.append({"screen": [sx, sy]})
        if len(self.track) % 4 == 1:  # 15 pictures a second
            self.clip.append(_crop(self.game.draw().convert("RGB"), sx, study.SIZE[1] - sy - 40, WALK_CROP))


def _player_mask(game: HiddenGame) -> Any:
    """The player's own pixels in the last picture (True where the sprite is drawn), rows from the top."""
    import numpy as np

    hd = game.window.hd2d_renderer
    static, ground = hd.static, hd.ground
    hd.static, hd.ground = [], None
    try:
        data = hd.draw(solid=game.player(), read=True)
    finally:
        hd.static, hd.ground = static, ground
    rgb = np.frombuffer(data, dtype=np.uint8).reshape(study.SIZE[1], study.SIZE[0], 3)[::-1]
    return (rgb[..., 0] > 200) & (rgb[..., 1] < 60)


def legibility(image: Any, mask: Any) -> dict[str, Any]:
    """How well the player stands out: its pixels, and the mean luminance (0-255) and colour (RGB distance) step
    across its outline, from each edge pixel of the sprite to each 4-neighbour outside it."""
    import numpy as np

    rgb = np.asarray(image, dtype=np.float64)
    luma = rgb @ np.array([0.299, 0.587, 0.114])
    steps_l, steps_c = [], []
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        inside = mask & ~np.roll(mask, (-dy, -dx), axis=(0, 1))  # sprite pixels whose neighbour is background
        ys, xs = np.nonzero(inside)
        ny, nx = ys + dy, xs + dx
        keep = (ny >= 0) & (ny < mask.shape[0]) & (nx >= 0) & (nx < mask.shape[1])
        ys, xs, ny, nx = ys[keep], xs[keep], ny[keep], nx[keep]
        steps_l.append(np.abs(luma[ys, xs] - luma[ny, nx]))
        steps_c.append(np.linalg.norm(rgb[ys, xs] - rgb[ny, nx], axis=1))
    ls, cs = np.concatenate(steps_l), np.concatenate(steps_c)
    ys, xs = np.nonzero(mask)
    return {"pixels": int(mask.sum()), "edge_luma_step": round(float(ls.mean()), 1) if ls.size else None,
            "edge_colour_step": round(float(cs.mean()), 1) if cs.size else None,
            "edge_luma_below_12_pct": round(100 * float((ls < 12).mean()), 1) if ls.size else None,
            "screen_centre": [round(float(xs.mean()), 1), round(float(ys.mean()), 1)] if xs.size else None}


def _close_up(game: HiddenGame, walk: Walk1x) -> tuple[Any, list[float]]:
    """The same camera (pitch, lens, follow) brought in to 4x, for one picture; and the player's feet in it."""
    camera = game.window.hd2d_renderer.camera
    distance = camera.distance
    camera.distance = CLOSE_VIEW / 2 / math.tan(math.radians(camera.fov) / 2)
    try:
        image = game.draw().convert("RGB")
        fx, fy = study._feet(walk.player)
        sx, sy = walk._screen(fx, fy, game.window.hd2d_renderer.elevation_of(walk.player) / 32)
    finally:
        camera.distance = distance
    return image, [sx, study.SIZE[1] - sy]


def run_variant(out: Path, variant: Variant, project: Path) -> dict[str, Any]:
    from PIL import Image

    key, label = variant[0], variant[1]
    game = HiddenGame(project, size=study.SIZE)
    result: dict[str, Any] = {"label": label, "cottage": variant[2].name if variant[2] else "starter",
                              "hero": variant[3].name if variant[3] else "starter", "spots": {}}
    try:
        ctx = game.window.ctx
        game.load(f"{SCENES}/start.json")
        game.step(90)
        result["gl_after_load"] = _gl_counts(ctx)
        result["hd2d_error"] = getattr(game.window, "hd2d_error", None)
        walk = Walk1x(game, out, key)
        for spot, (_text, route) in SPOTS.items():
            for keyname, axis, target in route:
                walk.go(keyname, axis, target, film=spot in FILMED)
            walk.shot(spot)
            image = Image.open(out / f"{key}_{spot}.png").convert("RGB")
            spot_result = {**walk.spots[spot], **legibility(image, _player_mask(game))}
            close, feet = _close_up(game, walk)
            close.save(out / f"{key}_{spot}_close.png")
            spot_result["close_feet_px"] = [round(v, 1) for v in feet]
            result["spots"][spot] = spot_result
        result["frame"] = study.frame_cost(game, 120)
        stats = game.window.hd2d_renderer.stats()
        result["renderer"] = {k: stats[k] for k in ("draw_calls", "triangles", "texture_bytes")}
        game.load(f"{SCENES}/start.json")  # a room reload must not grow GL textures, framebuffers or programs
        game.step(30)
        game.draw()
        ctx.gc()
        result["gl_after_reload"] = _gl_counts(ctx)
        result["_clip"] = walk.clip
    finally:
        game.close()
    return result


def _hero_strip(out: Path, variants: list[Variant], results: dict[str, Any], spot: str) -> Any:
    """The player of every variant at 1:1 (top row) and enlarged 4x without filtering (bottom row)."""
    from PIL import Image, ImageDraw

    w, h = HERO_CROP
    big = 4
    cell = w * big + 16
    sheet = Image.new("RGB", (cell * len(variants), 24 + h + 8 + h * big), (20, 22, 28))
    draw = ImageDraw.Draw(sheet)
    for i, (key, label, _m, _s) in enumerate(variants):
        image = Image.open(out / f"{key}_{spot}.png").convert("RGB")
        cx, cy = results[key]["spots"][spot]["screen_centre"]
        crop = _crop(image, cx, cy, HERO_CROP)
        sheet.paste(crop, (i * cell + (cell - w) // 2, 24))
        sheet.paste(crop.resize((w * big, h * big), Image.Resampling.NEAREST), (i * cell + 8, 24 + h + 8))
        draw.text((i * cell + 4, 4), label.split(":")[0] + ": 1:1 above, 4x below", fill=(230, 230, 230))
    return sheet


def compare(out: Path, set_name: str, extra: list[Variant]) -> dict[str, Any]:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    variants = SETS[set_name] + extra
    results = {v[0]: run_variant(out, v, make_variant(out, v)) for v in variants}
    labels = [v[1] for v in variants]
    for spot in SPOTS:
        for suffix in ("", "_close"):
            crops = []
            for key, *_ in variants:
                image = Image.open(out / f"{key}_{spot}{suffix}.png")
                at = results[key]["spots"][spot]
                size, (dx, dy) = CLOSE_CROP[set_name] if suffix else (CROP, (0, 0))
                cx, cy = (at["close_feet_px"][0] + dx, at["close_feet_px"][1] + dy) if suffix else at["screen_centre"]
                crops.append(_crop(image, cx, cy, size))
            study.grid(crops, labels, size).save(out / f"{set_name}_{spot}{suffix}.png")
        _hero_strip(out, variants, results, spot).save(out / f"{set_name}_hero_{spot}.png")
    clips = [results[v[0]].pop("_clip") for v in variants]
    length = min(len(c) for c in clips)
    frames = [study.grid([c[i] for c in clips], labels, WALK_CROP) for i in range(length)]
    if frames:
        frames[0].save(out / f"{set_name}_walk.webp", save_all=True, append_images=frames[1:], duration=67, loop=0,
                       lossless=True)
    report = {"set": set_name, "size": list(study.SIZE), "spots": {k: v[0] for k, v in SPOTS.items()},
              "variants": results}
    (out / f"{set_name}.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["compare"])
    parser.add_argument("out", type=Path)
    parser.add_argument("--set", dest="set_name", choices=sorted(SETS), default="cottage")
    parser.add_argument("--hero", nargs=3, action="append", default=[], metavar=("KEY", "LABEL", "SHEET"),
                        help="another hero sheet to compare (the hero set)")
    args = parser.parse_args()
    extra: list[Variant] = [(k, f"{k}: {label}", None, Path(sheet).resolve()) for k, label, sheet in args.hero]
    report = compare(args.out, args.set_name, extra)
    summary = {k: {"spots": {s: {m: v[m] for m in ("pixels", "edge_luma_step", "edge_colour_step", "player_height_px")}
                             for s, v in r["spots"].items()}, "frame_ms": r["frame"]["frame_ms"],
                   "renderer": r["renderer"]} for k, r in report["variants"].items()}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
