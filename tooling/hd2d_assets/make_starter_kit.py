"""Build Mesh's HD-2D starter kit into assets/hd2d_starter/ (what the HD-2D project template copies into a new
project): the models (Blender, headless), their preview pictures, the ground textures and the kit's catalogue.

    py -3.13 tooling/hd2d_assets/make_starter_kit.py [--blender D:/program/blender.exe]

Everything is made here from Mesh's own scripts (pixel_textures.py, build_starter_kit.py); nothing else is used, so
the kit is original and ships under the repository's licence (provenance: assets/hd2d_starter/PROVENANCE.md).
Running it again writes the same files.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
KIT = REPO / "assets" / "hd2d_starter"
HERE = Path(__file__).resolve().parent
LICENSE = "Mesh HD-2D starter kit: original, made by Mesh's own scripts; ships with Mesh"

# id -> (name, category, notes): what the model browser shows. Defaults turn 0, scale 1.
MODELS = {
    "cottage": ("Cottage", "Buildings", "A timber-and-plaster cottage with a doorway; walk inside."),
    "shop": ("Shop", "Buildings", "A stall-shop with a counter and awning; walk in at the counter's east end."),
    "wall_2m": ("Wall (2 m)", "Building parts", "A wall module, 2.5 m high: line several up."),
    "roof_4m": ("Roof (4 x 4 m)", "Building parts", "A gable roof: place it 2.5 m up on four wall modules."),
    "interior": ("Cottage interior", "Building parts", "A room with no roof, for an inside room."),
    "platform_4m": ("Platform (4 x 4 m)", "Terrain", "A 2 m cliff section with grass on top: join several."),
    "platform_2m": ("Platform (2 x 4 m)", "Terrain", "A narrower 2 m cliff section."),
    "stairs": ("Staircase", "Terrain", "Climbs 2 m (a platform's height) to a landing."),
    "bridge_6m": ("Bridge (6 m)", "Terrain", "A deck 2 m up between two platforms; walk under it too."),
    "path_2m": ("Path tile (2 m)", "Terrain", "Earth path on the grass; nothing to collide with."),
    "fence_2m": ("Fence (2 m)", "Props", "A 1 m high fence section."),
    "crate": ("Crate", "Props", "A 1 m wooden crate."),
    "barrel": ("Barrel", "Props", "A 1 m barrel."),
    "lamp_post": ("Lamp post", "Props", "Add a lamp light at its lantern, 2.5 m up."),
}
GROUND_TEXTURES = ("grass", "dirt")


def main(blender: Path) -> None:
    from engine.hd2d.glb import inspect_glb
    from engine.hd2d.thumbnail import render

    subprocess.run([sys.executable, str(HERE / "pixel_textures.py")], check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix="mesh_kit_") as tmp:
        subprocess.run([str(blender), "--factory-startup", "-noaudio", "--background", "--python",
                        str(HERE / "build_starter_kit.py"), "--", tmp], check=True, capture_output=True, timeout=900)
        for folder in ("models", "previews", "textures"):
            (KIT / folder).mkdir(parents=True, exist_ok=True)
        entries = []
        for model_id, (name, category, notes) in MODELS.items():
            built = Path(tmp) / f"{model_id}.glb"
            shutil.copyfile(built, KIT / "models" / f"{model_id}.glb")
            model, report = inspect_glb(KIT / "models" / f"{model_id}.glb")
            assert not report.warnings, (model_id, report.warnings)
            render(model).save(KIT / "previews" / f"{model_id}.png")
            entries.append({"id": model_id, "model": f"models/{model_id}.glb", "name": name, "category": category,
                            "preview": f"previews/{model_id}.png", "notes": notes, "license": LICENSE,
                            "collision": report.collision, "floors": report.floors})
    for texture in GROUND_TEXTURES:
        shutil.copyfile(HERE / "textures" / f"{texture}.png", KIT / "textures" / f"{texture}.png")
    (KIT / "catalog.json").write_text(json.dumps({"schema_version": 1, "kit": "Mesh HD-2D starter kit", "version": 1,
                                                  "models": entries}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} models to {KIT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blender", type=Path, default=Path("D:/program/blender.exe"))
    main(parser.parse_args().blender)
