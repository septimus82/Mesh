"""M2-2: render ``build_character.py`` in headless Blender and assemble its frames into one PNG sprite sheet plus a
JSON sidecar (Pillow). From the repo root:

    py -3.13 tooling/hd2d_assets/character_sheet.py OUT_DIR [--blender D:\\program\\blender.exe] [--frames DIR]
        [--evidence DIR]

Writes ``OUT_DIR/character_8dir.png`` and ``OUT_DIR/character_8dir.json``. Without ``--frames`` it runs Blender
(``--factory-startup -noaudio --background``) into a temporary folder; with it, it only assembles frames already
rendered there. ``--evidence`` also writes a 3x contact sheet and an animated walk preview (GIF) there.

Layout: one row per facing, in the sidecar's ``facings`` order (row 0 at the top); in each row the animations side by
side in ``animations`` order (idle, then walk), each from its ``first`` column for ``frames`` columns. Every frame is
``frame_width`` x ``frame_height``; ``pivot`` is the feet point in each frame, in pixels from its top-left corner.
The sheet is written by Pillow from the pixels alone (no metadata), so the same frames give the same bytes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
NAME = "character_8dir"
# Mirrors build_character.py (which runs inside Blender and can't be imported here); assemble() checks every frame.
FACINGS = ("down", "down_left", "left", "up_left", "up", "up_right", "right", "down_right")
COMPASS = ("S", "SW", "W", "NW", "N", "NE", "E", "SE")
ANIMATIONS = {"idle": (2, 2), "walk": (8, 10)}  # frames, fps
FRAME_W, FRAME_H, PIVOT, PITCH, PX_PER_M = 32, 52, (16, 45), 32, 32
OUTLINE = (27, 24, 20, 255)  # the PixelLab reference's outline colour (build_character.py)


def render(blender: Path, frames: Path) -> str:
    """Run the Blender script into ``frames``; returns Blender's version line."""
    cmd = [str(blender), "--factory-startup", "-noaudio", "--background", "--python",
           str(HERE / "build_character.py"), "--", str(frames)]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return next(line for line in out.splitlines() if line.startswith("Blender "))


def outlined(frame: Image.Image) -> Image.Image:
    """``frame`` with a 1 px OUTLINE on every transparent pixel beside (not diagonally) an opaque one; fully
    transparent pixels become (0, 0, 0, 0)."""
    solid = frame.getchannel("A").point(lambda a: 255 if a else 0)
    grown = Image.new("L", (frame.width + 2, frame.height + 2), 0)
    for at in ((0, 1), (2, 1), (1, 0), (1, 2)):
        shifted = Image.new("L", grown.size, 0)
        shifted.paste(solid, at)
        grown = ImageChops.lighter(grown, shifted)
    ring = ImageChops.subtract(grown.crop((1, 1, frame.width + 1, frame.height + 1)), solid)
    out = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", frame.size, OUTLINE), mask=ring)
    out.paste(frame, mask=solid)
    return out


def manifest(blender_version: str) -> dict:
    first, animations = 0, {}
    for name, (count, fps) in ANIMATIONS.items():
        animations[name] = {"first": first, "frames": count, "fps": fps, "loop": True}
        first += count
    columns = first
    return {
        "sheet": f"{NAME}.png", "frame_width": FRAME_W, "frame_height": FRAME_H,
        "columns": columns, "rows": len(FACINGS),
        "facings": list(FACINGS), "compass": list(COMPASS),
        "row_order": "one row per facing in 'facings' order, row 0 at the top",
        "animations": animations,
        "pivot": list(PIVOT), "pivot_note": "the feet point in every frame, px from the frame's top-left",
        "camera": {"projection": "orthographic", "pitch_deg": PITCH, "pixels_per_metre": PX_PER_M,
                   "facing_turn_deg": -45},
        "source": {"script": "tooling/hd2d_assets/build_character.py", "blender": blender_version},
    }


def assemble(frames: Path, out_dir: Path, blender_version: str) -> tuple[Path, Path]:
    meta = manifest(blender_version)
    sheet = Image.new("RGBA", (meta["columns"] * FRAME_W, meta["rows"] * FRAME_H), (0, 0, 0, 0))
    for row, facing in enumerate(FACINGS):
        for name, anim in meta["animations"].items():
            for i in range(anim["frames"]):
                with Image.open(frames / f"{facing}_{name}_{i}.png") as frame:
                    frame = frame.convert("RGBA")
                    if frame.size != (FRAME_W, FRAME_H) or frame.getbbox() is None:
                        raise SystemExit(f"{facing}_{name}_{i}: {frame.size}, empty={frame.getbbox() is None}")
                    sheet.paste(outlined(frame), ((anim["first"] + i) * FRAME_W, row * FRAME_H))
    out_dir.mkdir(parents=True, exist_ok=True)
    png, sidecar = out_dir / f"{NAME}.png", out_dir / f"{NAME}.json"
    sheet.save(png, optimize=True)
    sidecar.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return png, sidecar


def evidence(png: Path, out: Path) -> None:
    """A 3x contact sheet on grey, and the walk from all eight facings side by side as a looping GIF."""
    meta = json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    with Image.open(png) as sheet:
        sheet = sheet.convert("RGBA")
    grey = Image.new("RGBA", sheet.size, (150, 156, 150, 255))
    grey.alpha_composite(sheet)
    big = grey.resize((sheet.width * 3, sheet.height * 3), Image.Resampling.NEAREST)
    big.convert("RGB").save(out / "contact_sheet.png", optimize=True)
    walk, w, h = meta["animations"]["walk"], meta["frame_width"], meta["frame_height"]
    gif = []
    for i in range(walk["frames"]):
        strip = Image.new("RGBA", (w * meta["rows"], h), (150, 156, 150, 255))
        for row in range(meta["rows"]):
            x = (walk["first"] + i) * w
            strip.alpha_composite(sheet.crop((x, row * h, x + w, (row + 1) * h)), (row * w, 0))
        gif.append(strip.resize((strip.width * 3, h * 3), Image.Resampling.NEAREST).convert("RGB"))
    gif[0].save(out / "walk_8_facings.gif", save_all=True, append_images=gif[1:], duration=1000 // walk["fps"],
                loop=0, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--blender", type=Path, default=Path(r"D:\program\blender.exe"))
    parser.add_argument("--frames", type=Path, help="assemble frames already rendered here (no Blender run)")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.frames is not None:
        version = "(frames rendered beforehand)"
        png, sidecar = assemble(args.frames, args.out_dir, version)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            version = render(args.blender, Path(tmp))
            png, sidecar = assemble(Path(tmp), args.out_dir, version)
    if args.evidence is not None:
        evidence(png, args.evidence)
    print(png, sidecar, sep="\n")


if __name__ == "__main__":
    main()
