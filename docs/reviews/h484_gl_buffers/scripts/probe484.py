"""#484: live GL objects across HD-2D room transitions (start <-> cottage), with every arcade.gl buffer's creation and
deletion traced. Diagnostic only: nothing here changes Mesh.

    py -3.13 -I probe484.py WORKTREE PROJECT OUT.json [--mode harness|loop] [--visits 21] [--gl mesa]

--mode harness: the hidden-window harness as #484's probe ran it (on_update x30 + one hd2d draw per visit; no flip).
--mode real:    arcade.run() (pyglet's event loop) drives it; transitions every 30 ticks.
--mode loop:    each frame as the real event loop runs it: on_update, on_draw, flip() (arcade's flip calls ctx.gc()).
Per visit: counts right after load_scene, after settling, the dead-but-unfreed objects queued in ctx.objects, then
(measurement only, on a copy of the state via stats) what ctx.gc() and gc.collect()+ctx.gc() would leave.
"""
from __future__ import annotations

import collections
import ctypes
import gc
import json
import os
import sys
import time
import traceback
from ctypes import wintypes
from pathlib import Path

WT, PROJ, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
ARGS = sys.argv[4:]


def _opt(name: str, default: str) -> str:
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


MODE, VISITS, GLK = _opt("--mode", "harness"), int(_opt("--visits", "21")), _opt("--gl", "hw")
ROOMS = tuple(_opt("--rooms", "start,cottage").split(","))
if GLK == "mesa":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mesa_preload  # noqa: F401  (Mesa's opengl32.dll before pyglet)
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
os.chdir(WT)
import engine.optional_arcade  # noqa: E402,F401
from arcade.gl.backends.opengl.buffer import OpenGLBuffer  # noqa: E402
from pyglet import gl  # noqa: E402

KINDS = ("texture", "framebuffer", "program", "buffer", "geometry", "vertex_array")
live: dict[int, tuple[int, str]] = {}  # glo id -> (bytes, creation site)
created_by: collections.Counter[str] = collections.Counter()
deleted_by: collections.Counter[str] = collections.Counter()
_init, _delete_glo = OpenGLBuffer.__init__, OpenGLBuffer.delete_glo


def _site() -> str:
    """The creating call chain: the first two frames outside arcade.gl/pyglet, plus the first Mesh frame."""
    frames = traceback.extract_stack()[:-3]
    outside = [f for f in frames if "arcade\\gl" not in f.filename and "arcade/gl" not in f.filename
               and "pyglet" not in f.filename and "probe484" not in f.filename]
    def short(f: traceback.FrameSummary) -> str:
        p = f.filename.replace("\\", "/")
        p = p.split("site-packages/")[-1] if "site-packages/" in p else p.split("Mesh-h484/")[-1].split("Mesh-")[-1]
        return f"{p}:{f.lineno} {f.name}"
    near = [short(f) for f in outside[-2:]][::-1]
    mesh = next((short(f) for f in reversed(outside) if "/engine/" in f.filename.replace("\\", "/")), "-")
    return " <- ".join(near) + ("" if mesh in near else f" <= {mesh}")


def _traced_init(self, ctx, data=None, reserve=0, usage="static"):  # type: ignore[no-untyped-def]
    _init(self, ctx, data, reserve, usage)
    s = _site()
    live[self._glo.value] = (self._size, s)
    created_by[s] += 1


def _traced_delete(ctx, glo):  # type: ignore[no-untyped-def]
    if glo.value != 0 and glo.value in live:
        deleted_by[live.pop(glo.value)[1]] += 1
    return _delete_glo(ctx, glo)


OpenGLBuffer.__init__ = _traced_init  # type: ignore[method-assign]
OpenGLBuffer.delete_glo = staticmethod(_traced_delete)  # type: ignore[method-assign]


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                       "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                       "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def _proc_mb() -> dict[str, float]:
    c = PMC(); c.cb = ctypes.sizeof(c)
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    assert k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return {"working_set_mb": round(c.WorkingSetSize / 2**20, 1), "private_mb": round(c.PrivateUsage / 2**20, 1)}


def _gpu_free_mb() -> float | None:
    n = gl.GLint(); gl.glGetIntegerv(gl.GL_NUM_EXTENSIONS, n)
    names = {ctypes.cast(gl.glGetStringi(gl.GL_EXTENSIONS, i), ctypes.c_char_p).value for i in range(n.value)}
    if b"GL_NVX_gpu_memory_info" not in names:
        return None
    v = gl.GLint(); gl.glGetIntegerv(0x9049, v)  # GPU_MEMORY_INFO_CURRENT_AVAILABLE_VIDMEM_NVX (KiB)
    return round(v.value / 1024, 1)


def main() -> None:
    from hd2d_demo import HiddenGame

    game = HiddenGame(PROJ, size=(960, 540))
    game.window.audio.set_muted(True)
    w, ctx = game.window, game.window.ctx
    renderer_info = ctx.info.RENDERER

    def counts() -> dict[str, int]:
        return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}

    def pending() -> dict[str, int]:
        return dict(collections.Counter(type(o).__name__ for o in ctx.objects))

    def frame() -> None:
        w.dispatch_event("on_update", 1 / 60)
        if MODE == "loop":
            w.dispatch_event("on_draw")
            w.flip()

    def driver_check() -> dict[str, int]:
        ids = list(live)
        alive = sum(1 for i in ids if gl.glIsBuffer(i))
        return {"traced_live": len(ids), "glIsBuffer_true": alive,
                "traced_bytes": sum(b for b, _ in live.values())}

    def key(site: str) -> str:
        return site.split(" <= ")[-1] if " <= " in site else site.split(" <- ")[-1]

    def pending_sites() -> collections.Counter[str]:
        return collections.Counter(key(live.get(o._glo.value, (0, "untraced"))[1])
                                   for o in ctx.objects if type(o).__name__ == "OpenGLBuffer")

    flips = [0]
    _flip = w.flip

    def counted_flip() -> None:
        flips[0] += 1
        _flip()

    w.flip = counted_flip
    rows: list[dict] = []
    prev = [collections.Counter()]
    t0 = time.perf_counter()

    def record(v: int, name: str, after_load: dict) -> None:
        ps = pending_sites()
        row = {"visit": v, "room": name, "after_load": after_load, "settled": counts(), "pending": pending(),
               "pending_new_by_site": dict((ps - prev[0]).most_common(8)), "driver": driver_check(),
               "py_objects": len(gc.get_objects()), "flips": flips[0], **_proc_mb(), "gpu_free_mb": _gpu_free_mb()}
        prev[0] = ps
        rows.append(row)
        print(v, name, row["settled"], "pending", row["pending"], row["driver"], row["private_mb"],
              row["py_objects"], "flips", flips[0], flush=True)

    def load(v: int) -> tuple[str, dict]:
        name = ROOMS[v % 2]
        w.load_scene(f"packs/core_regions/scenes/{name}.json")
        return name, counts()

    if MODE == "real":  # arcade's own event loop (pyglet.app.run): it updates, draws and flips the window itself
        import arcade
        import pyglet

        state = {"v": 0, "f": 0}
        state["name"], state["after"] = load(0)

        def tick(_dt: float) -> None:
            state["f"] += 1
            if state["f"] % 30:
                return
            record(state["v"], state["name"], state["after"])
            state["v"] += 1
            if state["v"] == VISITS:
                pyglet.clock.unschedule(tick)
                pyglet.app.exit()
                return
            state["name"], state["after"] = load(state["v"])

        pyglet.clock.schedule_interval(tick, 1 / 60)
        arcade.run()
    else:
        for v in range(VISITS):
            name, after_load = load(v)
            for _ in range(30):
                frame()
            w.use()
            if MODE == "harness":
                if w.hd2d_renderer is not None:
                    w.hd2d_renderer.draw()
                else:
                    w.dispatch_event("on_draw")
            else:
                w.dispatch_event("on_draw"); w.flip()
            record(v, name, after_load)
    # what would be freed: arcade's own deferred deletion, then the cycle collector
    snap = {"before": counts(), "pending": pending(), "driver": driver_check()}
    ctx.gc()
    snap["after_ctx_gc"], snap["driver_after_ctx_gc"] = counts(), driver_check()
    gc.collect(); ctx.gc()
    snap["after_collect_ctx_gc"], snap["driver_after_collect"] = counts(), driver_check()
    survivors = collections.Counter(s for _b, s in live.values())
    renderer = w.hd2d_renderer
    if renderer is not None:
        renderer.release()
    gc.collect(); ctx.gc()
    snap["after_renderer_release"] = counts()
    snap.update(_proc_mb())
    report = {"worktree": str(WT), "mode": MODE, "gl": GLK, "renderer": renderer_info, "visits": rows, "end": snap,
              "seconds": round(time.perf_counter() - t0, 1),
              "survivor_sites": survivors.most_common(30),
              "created_sites": created_by.most_common(40), "deleted_sites": deleted_by.most_common(40)}
    game.close()
    report["after_window_close"] = counts()
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("END", json.dumps(snap), flush=True)


main()
