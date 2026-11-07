"""M17-L3 scratch: the HD-2D renderer's whole draw, GPU time (timer query), base engine or a prototype, at night on
four lit shots. One process per variant; run variants alternating (clocks are not locked).
Usage: perf.py PROJECT OUT_JSON [--patch NAME] [--suffix em]"""
import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3c")
sys.path.insert(0, r"D:\Games\Mesh-l3c\tooling")
sys.path.insert(0, str(Path(__file__).parent))
project, out = Path(sys.argv[1]), Path(sys.argv[2])
patch = sys.argv[sys.argv.index("--patch") + 1] if "--patch" in sys.argv else None
suffix = sys.argv[sys.argv.index("--suffix") + 1] if "--suffix" in sys.argv else ""
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env_perf" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
import engine.hd2d.renderer as R  # noqa: E402

assert R.__file__.startswith(r"D:\Games\Mesh-l3c"), R.__file__
if patch:
    import protos  # noqa: E402

    protos.apply(patch)
from hd2d_demo import HiddenGame  # noqa: E402

SHOTS = {"village": ("start", (640, 240)), "lk_shadow": ("lakeside", (870, 300)), "lk_plain": ("lakeside", (860, 640)),
         "cottage": ("cottage", (294, 200))}
game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
q = game.window.ctx.query(samples=False, time=True, primitives=False)
res = {}
for name, (base, feet) in SHOTS.items():
    game.load(f"packs/core_regions/scenes/{base}__l3_night{'_' + suffix if suffix else ''}.json")
    game.step(5)
    p = game.player()
    p.center_x, p.bottom = feet
    window = game.window
    window.motion_time = 0.0
    if hasattr(window, "water_time"):
        window.water_time = 0.0
    game.step(120)
    scene = window.scene_controller.current_scene_path.replace("\\", "/")
    assert scene.endswith(f"{base}__l3_night{'_' + suffix if suffix else ''}.json"), scene
    hd = window.hd2d_renderer
    draw = type(hd).draw
    target = [round(c, 3) for c in hd.camera.target]
    t = []
    for _ in range(660):  # the same settled frame, drawn again (no update between): only the shaders' cost varies
        with q:
            draw(hd)
        t.append(q.time_elapsed / 1e6)
    t = t[60:]
    res[name] = {"n": len(t), "p50_ms": round(statistics.median(t), 4), "p10_ms": round(sorted(t)[int(0.10 * len(t))], 4), "p95_ms": round(sorted(t)[int(0.95 * len(t))], 4),
                 "camera_target": target, "shadow_lamps": hd.lighting.point_rows, "shadow_map_mb": round(hd.lighting.memory_bytes() / 2 ** 20, 2)}
game.close()
out.write_text(json.dumps({"patch": patch, "suffix": suffix, "shots": res}, indent=1), encoding="utf-8")
print("done", patch, res)
