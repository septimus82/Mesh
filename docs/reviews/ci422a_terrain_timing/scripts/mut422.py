"""CI-422A fault injection (scratch, never committed): MUT422=<name> patches Studio at runtime.

reload_on_release   Studio._reload() after every committed stroke
reload_per_flush    Studio._reload() on every in-stroke ground flush (a reload while sculpting)
load_scene_direct   window.load_scene(current room) after every committed stroke, bypassing Studio._reload
rebuild_all         every flush rebuilds every terrain chunk, not just the touched ones
cpu_work            ~MUT422_MS (default 15) ms of extra CPU work in every Studio tick
"""
import os
import time

MUT = os.environ.get("MUT422", "")


def pytest_configure(config):
    if not MUT:
        return
    from engine.studio_hd2d import Hd2dView

    end, flush, tick = Hd2dView.end_stroke, Hd2dView._flush_stroke, Hd2dView.tick
    if MUT == "reload_on_release":
        def end_stroke(self):
            had = self.stroke is not None
            end(self)
            if had:
                self.studio._reload()
        Hd2dView.end_stroke = end_stroke
    elif MUT == "load_scene_direct":
        def end_stroke(self):
            had = self.stroke is not None
            end(self)
            if had:
                self.studio.window.load_scene(self.studio.project.path(self.studio.project.current))
                self.studio.hd2d.room_loaded(False)
        Hd2dView.end_stroke = end_stroke
    elif MUT == "reload_per_flush":
        def _flush_stroke(self):
            pending = self.stroke is not None and bool(self.stroke.get("pending"))
            flush(self)
            if pending and self.stroke is not None:
                self.studio._reload()
        Hd2dView._flush_stroke = _flush_stroke
    elif MUT == "rebuild_all":
        def _flush_stroke(self):
            s, r = self.stroke, self.renderer
            if s is not None and r is not None and r.terrain is not None and s["tool"] not in ("paint", "scatter") \
                    and s["pending"]:
                nx, ny = r.terrain.chunk_count()
                s["pending"] = {(i, j) for j in range(ny) for i in range(nx)}
            flush(self)
        Hd2dView._flush_stroke = _flush_stroke
    elif MUT == "cpu_work":
        ms = float(os.environ.get("MUT422_MS", "15")) / 1000

        def tick_(self, dt):
            t = time.perf_counter()
            while time.perf_counter() - t < ms:
                pass
            tick(self, dt)
        Hd2dView.tick = tick_
    else:
        raise ValueError(MUT)
