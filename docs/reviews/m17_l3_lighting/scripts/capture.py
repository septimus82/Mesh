"""M17-L3 scratch: matched lighting frames (hidden window, scratch project). Per shot x preset x control: the frame,
and per lamp the mean luminance of a ground disc (1.5 m) round the lamp's foot, projected with the frame's own
view-projection (hd.last_vp), so pools can be compared between controls and prototypes.
Usage: capture.py PROJECT OUT [--patch NAME] [--shots a,b] [--presets noon,evening,night] [--controls ,noshadow,roomoff]
"""
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3")
sys.path.insert(0, r"D:\Games\Mesh-l3\tooling")
sys.path.insert(0, str(Path(__file__).parent))
project, out = Path(sys.argv[1]), Path(sys.argv[2])


def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


patch = opt("--patch", None)
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
import engine.hd2d.renderer as R  # noqa: E402

assert R.__file__.startswith(r"D:\Games\Mesh-l3"), R.__file__
if patch:
    import protos  # noqa: E402

    protos.apply(patch)
import numpy as np  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

SHOTS = {
    "lk_shadow_lamps": ("lakeside", (870, 300), "lamps 0 + 1: the two that cast shadows"),
    "lk_plain_lamps": ("lakeside", (860, 640), "lamps 2 + 3: no shadow maps (MAX_SHADOW_LIGHTS = 2)"),
    "village_lamps": ("start", (640, 240), "the village's two lamp posts (both cast shadows)"),
    "cottage": ("cottage", (294, 200), "the interior's one lamp (casts shadows; walls round it)"),
    "village_offset25": ("start25", (640, 240), "the village's west lamp 25 cm off its lantern centre (C1)"),
}
DEFAULT_SHOTS = ["lk_shadow_lamps", "lk_plain_lamps", "village_lamps", "cottage"]
shots = opt("--shots", ",".join(DEFAULT_SHOTS)).split(",")
presets = opt("--presets", "noon,evening,night").split(",")
controls = opt("--controls", ",noshadow,roomoff").split(",")
PX = 32.0
game = HiddenGame(project, size=(1280, 720))
window = game.window
window.audio.set_muted(True)


def project_px(vp, p):
    m = np.asarray(vp, dtype=np.float64)  # rows (renderer.last_vp)
    c = m @ np.array([*p, 1.0])
    if c[3] <= 0:
        return None
    return ((c[0] / c[3] * 0.5 + 0.5) * 1280, (1 - (c[1] / c[3] * 0.5 + 0.5)) * 720)


res = {}
for shot in shots:
    base, feet, note = SHOTS[shot]
    for preset in presets:
        for control in controls:
            suffix = opt("--suffix", "")
            scene = f"packs/core_regions/scenes/{base}__l3_{preset}{'_' + control if control else ''}{'_' + suffix if suffix else ''}.json"
            game.load(scene)
            game.step(5)
            p = game.player()
            p.center_x, p.bottom = feet
            window.motion_time = 0.0
            if hasattr(window, "water_time"):
                window.water_time = 0.0
            game.step(120)
            now = window.scene_controller.current_scene_path.replace("\\", "/")
            assert now.endswith(scene.split("/")[-1]), (shot, now)
            img = game.draw().convert("RGB")
            hd = window.hd2d_renderer
            a = np.asarray(img).astype(np.float64)
            lumi = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
            name = f"{shot}__{preset}{'__' + control if control else ''}{'__' + patch if patch else ''}{'__' + suffix if suffix else ''}"
            img.save(out / f"{name}.png")
            pools = []
            for i, lamp in enumerate(hd.lighting.lamps):
                lx, ly = lamp.x / PX, lamp.y / PX
                gz = hd.ground_height(lamp.x, lamp.y) / PX
                ring = [project_px(hd.last_vp, (lx + 1.5 * math.cos(t), ly + 1.5 * math.sin(t), gz))
                        for t in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
                centre = project_px(hd.last_vp, (lx, ly, gz))
                if centre is None or any(q is None for q in ring):
                    continue
                xs, ys = np.array([q[0] for q in ring]), np.array([q[1] for q in ring])
                if xs.min() < 0 or ys.min() < 0 or xs.max() >= 1280 or ys.max() >= 720:
                    continue
                # the projected ellipse: pixels whose ground point lies within 1.5 m (approximate via the ring's hull)
                yy, xx = np.mgrid[int(ys.min()):int(ys.max()) + 1, int(xs.min()):int(xs.max()) + 1]
                cx, cy = centre
                rx, ry = (xs.max() - xs.min()) / 2, (ys.max() - ys.min()) / 2
                inside = ((xx - (xs.min() + xs.max()) / 2) / rx) ** 2 + ((yy - (ys.min() + ys.max()) / 2) / ry) ** 2 <= 1
                vals = lumi[yy[inside], xx[inside]]
                head = project_px(hd.last_vp, (lx, ly, lamp.elevation / PX))
                head_lum = None
                if head is not None and 4 <= head[0] < 1276 and 4 <= head[1] < 716:
                    hx, hy = int(head[0]), int(head[1])
                    head_lum = round(float(lumi[hy - 3:hy + 4, hx - 3:hx + 4].mean()), 2)
                pools.append({"lamp_head_lum": head_lum, "lamp": i, "shadow_slot": hd.lighting.lamp_slots[i], "px": [round(cx), round(cy)],
                              "pool_mean_lum": round(float(vals.mean()), 2), "pixels": int(inside.sum())})
            res[name] = {"scene": scene, "note": note, "frame_mean_lum": round(float(lumi.mean()), 2), "pools": pools}
            (out / f"frames{'_' + patch if patch else ''}{'_' + suffix if suffix else ''}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
game.close()
print("done", len(res))
