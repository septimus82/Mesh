"""Cost of the particle layer's per-frame SpriteList.clear() (5 GL buffers made, the old 5 deleted at ctx.gc())."""
import sys, time
from pathlib import Path
if "--mesa" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent)); import mesa_preload  # noqa
import arcade
w = arcade.Window(64, 64, visible=False); ctx = w.ctx
sl = arcade.SpriteList(); [sl.append(arcade.SpriteSolidColor(4, 4, color=arcade.color.RED)) for _ in range(40)]
sl.draw(); ctx.finish()
for label, op in (("clear()+ctx.gc()", lambda: (sl.clear(), ctx.gc())), ("baseline: ctx.gc() only", lambda: ctx.gc())):
    ts = []
    for _ in range(5):
        t = time.perf_counter()
        for _ in range(200):
            op()
        ctx.finish(); ts.append((time.perf_counter() - t) / 200 * 1e6)
    print(f"{ctx.info.RENDERER[:28]:28} {label:26} median {sorted(ts)[2]:7.1f} us/frame")
w.close()
