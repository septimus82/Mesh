"""Lamp-fixture fix: cost on the real Lakeside room (scratch copy), for the engine checkout given (base or fix)."""
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(sys.argv[1])
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg")})
import hd2d_demo  # noqa: E402

game = hd2d_demo.HiddenGame(M17 / "projects" / "lakeside", size=(1280, 720))
try:
    game.load("packs/core_regions/scenes/lakeside_night.json")
    game.step(30)
    hd = game.window.hd2d_renderer
    light, ctx = hd.lighting, game.window.ctx
    game.draw()
    first = light.shadow_draws
    created_before = {k: getattr(ctx.stats, k)[0] for k in ("texture", "framebuffer", "buffer", "program", "vertex_array")}
    times = []
    for _ in range(60):
        t = time.perf_counter()
        game.draw()
        ctx.finish()
        times.append((time.perf_counter() - t) * 1000)
    created = {k: getattr(ctx.stats, k)[0] - created_before[k] for k in created_before}
    print(json.dumps({"engine": str(REPO), "fixtures": [sorted(f) for f in getattr(light, "fixtures", [])],
                      "first_frame_shadow_draws": first, "steady_frame_shadow_draws": light.shadow_draws,
                      "lamp_map_renders_after_61_frames": light.lamp_map_renders,
                      "gl_objects_created_in_60_frames": created,
                      "frame_ms_median": round(statistics.median(times), 2), "frame_ms_p95": round(sorted(times)[56], 2),
                      "static_draws": len(hd.static), "spans": len(getattr(hd, "static_spans", {}))}))
finally:
    game.close()
