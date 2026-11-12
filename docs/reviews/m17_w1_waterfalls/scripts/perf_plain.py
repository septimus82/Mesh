"""A room without waterfalls on one checkout (argv[1]): the glen's plain stream (no fall, no mouth) and R4's stream into
its pond, GPU (timer query) and CPU per frame, for comparing the base engine with the branch's (the same project
files, made beforehand). py -3.13 perf_plain.py WORKTREE PROJECTS_DIR OUT.json [--rounds N]"""
import json
import statistics
import sys
import time
from pathlib import Path

WT, PROJ, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
ROUNDS = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 400
sys.path.insert(0, str(WT))
sys.path.insert(1, str(WT / "tooling"))
import engine.optional_arcade  # noqa: E402,F401
import engine.hd2d.renderer as R  # noqa: E402

assert Path(R.__file__).resolve().is_relative_to(WT.resolve()), R.__file__
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

CAMS = {"front": ((20.0, 23.9, 1.4), 48.0, 25.0, 0.0), "r4": ((19.0, 34.0, 0.0), 40.0, 45.0, 0.0)}


def stats(t: list[float]) -> dict[str, float]:
    t = sorted(t[len(t) // 10:])
    return {"p50_ms": round(statistics.median(t), 4), "p95_ms": round(t[int(0.95 * len(t))], 4), "n": len(t)}


res: dict = {"worktree": str(WT)}
for name, cam in (("glen_plain", "front"), ("r4_mouth", "r4")):
    game = HiddenGame(PROJ / name, size=(1280, 720))
    try:
        ctx = game.window.ctx
        game.load(f"{SCENES}/start.json")
        game.step(30)
        game.window.water_time = game.window.motion_time = 3.0
        hd = game.window.hd2d_renderer
        tex = ctx.texture((1280, 720), components=4)
        fbo = ctx.framebuffer(color_attachments=[tex])
        q = ctx.query(samples=False, time=True, primitives=False)
        (target, d, p, y) = CAMS[cam]
        camera = R.Camera(p, 12.0, d, False, y)
        camera.target = target
        gpu, cpu = [], []
        for k in range(ROUNDS + 5):
            fbo.use()
            with q:
                t0 = time.perf_counter()
                hd.draw(camera=camera, viewport=(0, 0, 1280, 720))
                c = time.perf_counter() - t0
            if k >= 5:
                gpu.append(q.time_elapsed / 1e6)
                cpu.append(c * 1000)
        res[name] = {"gpu": stats(gpu), "cpu": stats(cpu), "draw_calls": hd.draw_calls, "gl": str(ctx.info.RENDERER)}
    finally:
        game.close()
OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res))
