"""Frames of rooms without waterfalls, from one checkout (argv[1]) into argv[2]: the same steps, the water's and the
motion's clocks set, so two checkouts' frames can be compared byte for byte. Rooms: R1's two streams, R4's stream into
a pond (carved), the template village, M23B's campfire at night (its embers and smoke), and Lakeside-like weather
(the village in the rain)."""
import hashlib
import json
import sys
from pathlib import Path

REPO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
OUT.mkdir(parents=True, exist_ok=True)

import hd2d_visual_study as study  # noqa: E402
import m23b_fire_study as fire  # noqa: E402
import r1_river_study as r1  # noqa: E402
import r4_river_mouth_study as r4  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402


rooms = {
    "r1_streams": lambda: r1.make_project(OUT / "p", "r1"),
    "r4_mouth": lambda: r4.make_project(OUT / "p", "r4", carved=True),
    "village": lambda: study.new_project(OUT / "p", "village", stage6a=False),
    "campfire_night": lambda: fire.make_project(OUT / "p", "fire", night=True),
}
CAMERAS = {"near": ((20.0, 30.0, 0.0), 40.0, 30.0), "far": ((20.0, 22.0, 0.0), 120.0, 30.0),
           "top": ((19.0, 34.0, 0.0), 40.0, 80.0)}
report = {}
import engine
report["engine"] = engine.__file__
for name, make in rooms.items():
    project = make()
    game = HiddenGame(project)
    try:
        from engine.hd2d.renderer import Camera
        game.load(f"{SCENES}/start.json")
        game.step(30)
        hd = game.window.hd2d_renderer
        w, h = game.window.get_framebuffer_size()
        for cname, (target, dist, pitch) in CAMERAS.items():
            for k, t in enumerate((1.25, 7.5)):
                game.window.water_time, game.window.motion_time = t, t
                cam = Camera(pitch, 12.0, dist, False, 0.0)
                cam.target = target
                data = bytes(hd.draw(camera=cam, viewport=(0, 0, w, h), read_final=True))
                key = f"{name}/{cname}/{k}"
                report[key] = hashlib.sha256(data).hexdigest()
                (OUT / f"{name}_{cname}_{k}.raw").write_bytes(data)
        report[f"{name}/draw_calls"] = hd.draw_calls
    finally:
        game.close()
(OUT / "hashes.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print(json.dumps(report, indent=1))
