import dataclasses
import os
import sys
from pathlib import Path

WT = Path(r"D:\Games\Mesh-l4h")
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
import numpy as np  # noqa: E402

import hd2d_haze_study as st  # noqa: E402
from engine.hd2d.haze import Haze  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

OUT = Path(sys.argv[1])
game = HiddenGame(OUT / "game", size=(960, 540))
try:
    hd = st.settle(game, "packs/core_regions/scenes/start.json")
    base = hd.settings
    off = st.picture(game, hd)
    z = st.metres(st.depth_of(hd), False)
    w, h = game.window.get_framebuffer_size()
    focus, band = hd.dof_focus(hd.camera, True)
    print("focus", round(focus, 2), "band", round(band, 2), "followed", getattr(hd.followed(), "mesh_id", None))
    for name in ("daytime", "evening"):
        hd.settings = dataclasses.replace(base, haze=Haze(name))
        img = st.picture(game, hd)
        print(name, "onset", round(hd.last_haze["onset"], 2))
        for sp in hd._sprites():
            game.window.use()
            m = np.frombuffer(hd.draw(solid=sp, read=True), dtype=np.uint8).reshape(h, w, 3)[..., 0] > 128
            if m.sum() < 40:
                continue
            a, b = st.readability(off, m), st.readability(img, m)
            zz = z[m]
            print("  ", getattr(sp, "mesh_id", "?"), "px", int(m.sum()), "z", round(float(np.median(zz)), 2),
                  "beyond focus", round(float(np.median(zz)) - focus, 2), "weber", round(a[0], 3), "->", round(b[0], 3),
                  "edge", round(a[1], 2), "->", round(b[1], 2))
        hd.settings = base
finally:
    game.close()
