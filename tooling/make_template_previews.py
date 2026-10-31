"""Draw the launcher's template pictures from what each template actually builds.

Creates every launcher template in a temporary folder and draws its first room: the
tiles of each layer, then characters (circles) and doors (brown blocks). An HD-2D
template's room is drawn instead by the game's own HD-2D renderer, in a hidden window.
Run it after changing a template:  py -3.13 tooling/make_template_previews.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from engine import project_ops as ops  # noqa: E402
from engine.project_scaffold import create_project  # noqa: E402
from engine.project_templates import list_templates  # noqa: E402

CELL = 12  # preview pixels per map tile
CARD = (288, 192)  # the launcher's card (engine.launcher.CARD_W, CARD_H)
HD2D_VIEW = (20.0, 13.5, 0.8)  # m: where the HD-2D picture looks (the village between the cottage, shop and hills)


def render(root: Path) -> Image.Image:
    scene = json.loads((root / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
    info = ops.map_info(scene)
    if info is None:
        raise SystemExit(f"{root}: the start room has no map to preview")
    sheet = Image.open(root / ops.TILESET_SOURCE.replace(".json", ".png")).convert("RGBA")
    columns = sheet.width // ops.TILE_SIZE
    image = Image.new("RGBA", (info["width"] * CELL, info["height"] * CELL), (30, 32, 38, 255))
    for layer, _z, _collision in ops.MAP_LAYERS:
        for index, gid in enumerate(info["layers"].get(layer) or []):
            if gid:
                local = gid - 1
                x, y = (local % columns) * ops.TILE_SIZE, (local // columns) * ops.TILE_SIZE
                tile = sheet.crop((x, y, x + ops.TILE_SIZE, y + ops.TILE_SIZE)).resize((CELL, CELL), Image.Resampling.LANCZOS)
                image.alpha_composite(tile, ((index % info["width"]) * CELL, (index // info["width"]) * CELL))
    draw = ImageDraw.Draw(image)
    scale = CELL / ops.TILE_SIZE
    for entity in scene.get("entities") or []:
        x = float(entity.get("x", 0)) * scale
        y = image.height - float(entity.get("y", 0)) * scale
        if entity.get("tag") == "door":
            draw.rectangle([x - 6, y - 8, x + 6, y + 8], fill=(120, 72, 36), outline=(60, 36, 18))
        elif entity.get("tag") in ("player", "npc"):
            colour = (70, 140, 245) if entity["tag"] == "player" else (245, 170, 40)
            draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=colour, outline=(20, 20, 24), width=2)
    return image


def render_hd2d(root: Path) -> Image.Image:
    """An HD-2D template's first room as its gameplay camera draws it: a hidden window, 3x the card, scaled down."""
    sys.path.insert(0, str(REPO / "tooling"))
    from hd2d_demo import SCENES, HiddenGame  # noqa: PLC0415  # the Stage 2 hidden-window harness

    size = (CARD[0] * 3, CARD[1] * 3)
    game = HiddenGame(root, size=size)
    try:
        game.load(f"{SCENES}/start.json")
        game.step(90)  # past the room's fade-in
        hd = game.window.hd2d_renderer
        hd.camera.target = HD2D_VIEW
        data = hd.draw(read=True)
    finally:
        game.close()
    image = Image.frombytes("RGB", size, data).transpose(Image.Transpose.FLIP_TOP_BOTTOM)  # GL rows run bottom-up
    return image.resize(CARD, Image.Resampling.LANCZOS)


def main() -> None:
    for template in list_templates(launcher_only=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "game"
            create_project(root, template.title, template_id=template.id)
            out = REPO / template.preview
            out.parent.mkdir(parents=True, exist_ok=True)
            scene = json.loads((root / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
            picture = render_hd2d(root) if (scene.get("settings") or {}).get("hd2d") else render(root)
            picture.convert("RGB").save(out)
            print(f"wrote {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
