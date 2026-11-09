import os, sys
from pathlib import Path
sys.path.insert(0, r"D:\Games\Mesh-l4c"); sys.path.insert(1, r"D:\Games\Mesh-l4c\tooling")
os.chdir(r"D:\Games\Mesh-l4c")
import numpy as np
from PIL import Image
from hd2d_studio_demo import StudioDriver
import hd2d_composite_study as cs
out = Path(sys.argv[1])
d = StudioDriver(out / "game")
view = d.studio.hd2d
view.advance_motion = view.advance_weather = lambda dt: None
d.advance(5); d.window.motion_time = 0.0
hd = d.renderer; ctx = hd.ctx
x, y, w, h = (int(v) for v in view.viewport())
def draw(camera):
    tex = ctx.texture((w, h), components=4); fbo = ctx.framebuffer(color_attachments=[tex])
    fbo.use(); b = cs.picture(hd, camera=camera); vp = [list(r) for r in hd.last_vp]
    d.window.use(); fbo.delete(); tex.delete()
    return np.flipud(np.frombuffer(b, dtype=np.uint8).reshape(h, w, 3)), vp
studio_pic, vp_s = draw(view.camera)
gc, sc = hd.camera, view.camera
print("studio cam", sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho, sc.yaw)
print("game cam  ", gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw, "ready", hd._camera_ready)
gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw = sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho, sc.yaw
game_pic, vp_g = draw(None)
print("game cam after", gc.target, "vp equal", np.allclose(vp_s, vp_g), "particles", hd.particles is not None, "weather_preview", hd.weather_preview, "stage", hd.last_stage)
Image.fromarray(np.hstack([studio_pic, game_pic])).save(out / "probe_gamepath.png")
d.close()
