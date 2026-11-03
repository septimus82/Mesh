"""M17 audit (scratch): scene-configuration variants made with the engine's own op, and a real walk capture.

variants: copies of the scratch Lakeside room with set_hd2d_sun(preset=evening|night) - scene settings only, new
files in the scratch project; the original scene file and the owner's projects are untouched.
walk:     the real game in a hidden window; the player holds a movement key (the same key events the OS sends) and
          frames are drawn while the key is still held, so the character is mid-walk.
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh")
M17 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg")})
PROJECT = M17 / "projects" / "lakeside"
SCENES = PROJECT / "packs" / "core_regions" / "scenes"


def variants() -> None:
    from engine.project_ops import set_hd2d_sun

    base = json.loads((SCENES / "lakeside.json").read_text(encoding="utf-8"))
    for preset in ("evening", "night"):
        (SCENES / f"lakeside_{preset}.json").write_text(json.dumps(set_hd2d_sun(base, preset=preset)), encoding="utf-8")
        print("wrote", f"lakeside_{preset}.json")


def walk() -> None:
    import hd2d_demo

    game = hd2d_demo.HiddenGame(PROJECT, size=(1280, 720))
    try:
        arcade = game.arcade
        game.load("packs/core_regions/scenes/lakeside.json")
        game.step(90)
        player = game.player()
        player.center_x, player.center_y = 960.0, 300.0
        game.step(10)
        before = (round(player.center_x, 1), round(player.center_y, 1))
        game.window.dispatch_event("on_key_press", arcade.key.D, 0)  # walk east along the path
        shots = []
        for k in range(3):
            game.step(8)
            image = game.draw()
            out = M17 / "shots" / f"10_walk_frame{k + 1}.png"
            image.convert("RGB").save(out)
            shots.append((out.name, round(player.center_x, 1), round(player.center_y, 1)))
        game.window.dispatch_event("on_key_release", arcade.key.D, 0)
        print("walk from", before, "frames", shots)
    finally:
        game.close()


if __name__ == "__main__":
    {"variants": variants, "walk": walk}[sys.argv[1]]()
