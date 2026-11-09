"""#484 minimal reproduction, arcade only (no Mesh): arcade's default gc_mode "context_gc" queues every garbage GL
object in ctx.objects and deletes it only in ctx.gc(), which arcade calls from Window.flip(). A loop that never flips
(a hidden-window test harness dispatching on_update/on_draw) keeps every dropped buffer alive in the driver.

    py -3.13 -I minimal_repro.py [--mesa]
"""
import sys
from pathlib import Path

if "--mesa" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mesa_preload  # noqa: F401

import arcade
from pyglet import gl

w = arcade.Window(64, 64, visible=False)
ctx = w.ctx
print("GL:", ctx.info.RENDERER, "| gc_mode:", ctx.gc_mode)


def state(label: str) -> None:
    queued = [o for o in ctx.objects if type(o).__name__ == "OpenGLBuffer"]
    in_driver = sum(1 for o in queued if gl.glIsBuffer(o._glo.value))
    print(f"{label:46} live buffers {ctx.stats.buffer[0] - ctx.stats.buffer[1]:5}  queued {len(queued):5}"
          f"  queued still in driver {in_driver:5}")


def scene() -> arcade.SpriteList:
    """What a room load does: new SpriteLists (the old ones dropped)."""
    sl = arcade.SpriteList()
    sl.append(arcade.SpriteSolidColor(4, 4, color=arcade.color.RED))
    return sl


sl = scene()
state("start")
for _ in range(20):
    sl = scene()  # 20 'room loads'
state("20 SpriteLists replaced, no flip")
for _ in range(100):
    sl.clear()  # what a particle layer does each frame
state("+100 SpriteList.clear(), no flip")
w.flip()
state("one Window.flip() (calls ctx.gc())")
for _ in range(100):
    sl = scene(); sl.clear(); w.flip()
state("100 x (replace + clear + flip)")
w.close()
