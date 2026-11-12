"""M17-W1 evidence: real engine frames of the waterfall glen (hidden windows), into OUT/frames, and labelled sheets
into OUT/sheets. Every picture is Hd2dRenderer's own output (the final picture, as the game shows it, before the HUD,
unless noted 'game window', which is the whole window with its HUD)."""
import json
import math
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-w1")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
OUT = Path(sys.argv[1])
FR = OUT / "frames"
FR.mkdir(parents=True, exist_ok=True)

import w1_waterfall_checks as c  # noqa: E402
import w1_waterfall_study as glen  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SIZE = (1280, 720)
LIP_Y, FOOT_Y = glen.Y(612.0) / 32, glen.Y(676.0) / 32
CAMS = {
    "front": ((20.0, 23.9, 1.4), 48.0, 25.0, 0.0),
    "side_east": ((20.0, 23.6, 1.4), 54.0, 25.0, 70.0),
    "side_west": ((20.0, 23.6, 1.4), 54.0, 25.0, -60.0),
    "high": ((20.0, 23.6, 1.0), 66.0, 55.0, 0.0),
    "low": ((20.0, 22.5, 1.2), 40.0, 12.0, 0.0),
    "behind": ((20.0, 23.9, 1.4), 54.0, 30.0, 180.0),
    "lip": ((20.0, LIP_Y - 0.2, 2.7), 20.0, 38.0, 0.0),
    "foot": ((20.0, FOOT_Y - 0.6, 0.4), 22.0, 24.0, 0.0),
    "boulder": ((21.2, 22.9, 0.8), 26.0, 14.0, 28.0),
    "wide": ((20.0, 16.0, 1.0), 110.0, 30.0, 0.0),
}
report: dict = {}


class Shots(c.Frames):
    def __init__(self, project: Path) -> None:
        self.game = HiddenGame(project, size=SIZE)
        self.game.load(f"{SCENES}/start.json")
        self.game.step(60)
        self.hd = self.game.window.hd2d_renderer
        self.size = self.game.window.get_framebuffer_size()
        self.rivers = self.hd.settings.rivers

    def save(self, name: str, spec: tuple, t: float, rivers: tuple | None = None) -> Path:
        path = FR / f"{name}.png"
        Image.fromarray(self.shot(spec, t, rivers)).save(path)
        return path


def run_room(variant: str, plan: list) -> None:
    project = glen.make_project(OUT / "projects", variant, variant=variant)
    s = Shots(project)
    try:
        report[variant] = {"errors": [s.hd.water_error, s.hd.settings.rivers_error], "falls": len(s.hd.water.feet)
                           if s.hd.water else None}
        for item in plan:
            item(s)
    finally:
        s.close()


def stills(prefix: str, names: list, t: float = 3.0):
    def go(s: Shots) -> None:
        for n in names:
            s.save(f"{prefix}_{n}", CAMS[n], t)
    return go


def sequence(prefix: str, cam: str, count: int, dt: float, t0: float = 2.0, moving: bool = False):
    def go(s: Shots) -> None:
        for k in range(count):
            spec = CAMS[cam]
            if moving:
                (tx, ty, tz), d, p, y = spec
                spec = ((tx - 3.0 + 6.0 * k / (count - 1), ty, tz), d, p, y)
            s.save(f"{prefix}_{k}", spec, t0 + dt * k)
    return go


def game_window(prefix: str):
    def go(s: Shots) -> None:
        s.game.window.water_time = s.game.window.motion_time = 3.0
        s.game.draw().convert("RGB").save(FR / f"{prefix}_game_window.png")
    return go


def without_fall(prefix: str):
    def go(s: Shots) -> None:
        s.save(f"{prefix}_front_no_waterfall", CAMS["front"], 3.0, s.without_falls())
    return go


def character_in_front(s: Shots) -> None:
    p = s.game.player()
    home = (p.center_x, p.center_y, p.mesh_entity_data.get("elevation", 0.0))
    p.center_x, p.center_y = 600.0, glen.Y(706.0)
    p.mesh_entity_data["elevation"] = 0.0
    s.save("day_character_in_front", CAMS["foot"], 3.0)
    p.center_x, p.center_y = home[0], home[1]
    p.mesh_entity_data["elevation"] = home[2]


run_room("day", [stills("day", ["front", "side_east", "side_west", "high", "low", "behind", "lip", "foot", "boulder",
                                 "wide"]),
                 game_window("day"), without_fall("day"), sequence("day_anim", "front", 8, 1 / 20),
                 sequence("day_lip_anim", "lip", 6, 1 / 30), sequence("day_foot_anim", "foot", 6, 1 / 30),
                 sequence("day_moving", "front", 6, 1 / 30, moving=True), character_in_front])
run_room("evening", [stills("evening", ["front", "wide", "side_east", "foot"]), game_window("evening")])
run_room("haze_bloom", [stills("haze_bloom", ["front", "wide", "side_east"]), game_window("haze_bloom")])
run_room("many", [stills("many", ["wide", "high"])])
(OUT / "evidence_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------- sheets
SH = OUT / "sheets"
SH.mkdir(exist_ok=True)


def label(img: Image.Image, text: str) -> Image.Image:
    img = img.copy()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, min(img.width, 9 * len(text) + 16), 22), fill=(0, 0, 0))
    d.text((8, 5), text, fill=(255, 255, 255))
    return img


def sheet(name: str, cells: list, cols: int = 2, scale: float = 0.5, crop: tuple | None = None) -> None:
    ims = []
    for file, text in cells:
        im = Image.open(FR / f"{file}.png").convert("RGB")
        if crop is not None:
            im = im.crop(crop).resize((int((crop[2] - crop[0]) * scale * 2), int((crop[3] - crop[1]) * scale * 2)),
                                      Image.NEAREST)
        else:
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        ims.append(label(im, text))
    w, h = ims[0].size
    rows = math.ceil(len(ims) / cols)
    out = Image.new("RGB", (w * cols, h * rows), (24, 24, 24))
    for i, im in enumerate(ims):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    out.save(SH / f"{name}.png")


sheet("01_day_evening_haze_bloom", [("day_front", "day: the fall from the pool"),
                                     ("evening_front", "evening: low warm sun"),
                                     ("haze_bloom_wide", "evening + haze + warm bloom (lamps glow, water doesn't)"),
                                     ("day_game_window", "day: the game window (player camera, HUD)")])
sheet("02_angles", [("day_front", "front (pitch 25)"), ("day_side_east", "from the east (yaw 70)"),
                    ("day_side_west", "from the west (yaw -60)"), ("day_high", "high (pitch 55)"),
                    ("day_low", "low (pitch 12)"), ("day_behind", "from behind, over the lip (yaw 180)")], cols=3)
sheet("03_lip_and_foot", [("day_lip", "the lip: stream to crest to curtain"), ("day_foot", "the foot: boil, foam, ripples"),
                          ("evening_foot", "the foot at evening"), ("day_front_no_waterfall", "the same river, no waterfall")])
sheet("04_occlusion", [("day_character_in_front", "a character in front of the curtain"),
                       ("day_boulder", "the boulder and rocks in front of its foot"),
                       ("day_behind", "from behind: the cliff top hides the curtain"),
                       ("many_wide", "five waterfalls in one room")])
sheet("05_animation_front", [(f"day_anim_{k}", f"t + {k}/20 s") for k in range(8)], cols=4,
      crop=(500, 120, 780, 520), scale=0.5)
sheet("06_animation_lip", [(f"day_lip_anim_{k}", f"lip, t + {k}/30 s") for k in range(6)], cols=3,
      crop=(440, 160, 840, 560), scale=0.5)
sheet("07_animation_foot", [(f"day_foot_anim_{k}", f"foot, t + {k}/30 s") for k in range(6)], cols=3,
      crop=(400, 200, 880, 600), scale=0.5)
sheet("08_moving_camera", [(f"day_moving_{k}", f"camera panning, frame {k}") for k in range(6)], cols=3)
frames = [Image.open(FR / f"day_anim_{k}.png").convert("RGB").crop((420, 80, 860, 560)) for k in range(8)]
frames[0].save(SH / "09_curtain_animation.gif", save_all=True, append_images=frames[1:], duration=50, loop=0)
print(json.dumps(report, indent=1))
