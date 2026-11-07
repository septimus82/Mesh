"""M17-L2 scratch (investigation): the roof cutaway measured in the real renderer (hidden window, scratch project copy).

Per shot (player's FEET put at a fixed spot, clocks reset, 150 frames): the frame as drawn (cutaway as the engine does it,
or with --proto the PROPOSED rule, patched into this process only), the same frame with the cutaway off, and three
read-backs of the player drawn flat against the world's depth: unoccluded (structures removed), with the cut, without.
Records: player visible with/without the cut; pixels the cut changed; how many of those lie OUTSIDE the player's
on-screen box grown by 16 px (the over-cut: roof removed where it hides nothing of the player).
Usage: cut_capture.py PROJECT OUT SHOTS_JSON [--proto]
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, r"D:\Games\Mesh-cut")
sys.path.insert(0, r"D:\Games\Mesh-cut\tooling")
project, out, shots_file = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
proto = "--proto" in sys.argv
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

import engine.hd2d.renderer as R  # noqa: E402

assert "Mesh-cut" in R.__file__ and hasattr(R, "cutaway_cuts"), R.__file__  # (the implementation under test)
assert "--proto" not in sys.argv

if proto:  # ---- the PROPOSED rule (scratch prototype; no engine file changed)
    old = R.MESH_FS
    R.MESH_FS = old.replace(
        "uniform int u_cut; uniform vec4 u_cut_at; uniform vec3 u_cut_eye; uniform float u_cut_floor;",
        "uniform int u_cut; uniform vec4 u_cut_at; uniform vec3 u_cut_eye; uniform float u_cut_floor;\n"
        "uniform vec3 u_cut_right; uniform vec2 u_cut_half; uniform float u_cut_round;").replace(
        """        if (along < reach - 0.2 && distance(v_world, u_cut_eye + dir * along) < u_cut_at.w) discard;""",
        """        if (along > 0.0 && along < reach - 0.2) {
            // the cone from the eye through the player's on-screen box: offsets across and up, scaled to the
            // player's distance (what the picture shows), against the box (sprite + margin), rounded corners
            vec3 off = v_world - (u_cut_eye + dir * along);
            vec3 up = cross(u_cut_right, dir);
            vec2 q = abs(vec2(dot(off, u_cut_right), dot(off, up)) * (reach / along)) - u_cut_half + u_cut_round;
            if (length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - u_cut_round < 0.0) discard;
        }""")
    assert R.MESH_FS.count("u_cut_half") == 2, "prototype patch did not apply"
    MARGIN, ROUND = 0.25, 0.3  # m: around the sprite's box; its corners' radius

    def bind(self, program, game_camera):
        import math
        sprite = self.followed() if game_camera is not None and self._cutaway else None
        if sprite is None or game_camera is None:
            program["u_cut_at"] = (0.0, 0.0, 0.0, 0.0)
            return
        floor = self.elevation_of(sprite) / R.PIXELS_PER_METRE
        stretch = 1.0 / max(0.5, math.cos(math.radians(self.camera.pitch)))
        w, h = abs(sprite.width) / R.PIXELS_PER_METRE, abs(sprite.height) / R.PIXELS_PER_METRE
        program["u_cut_at"] = (sprite.center_x / R.PIXELS_PER_METRE, sprite.bottom / R.PIXELS_PER_METRE,
                               floor + h * stretch / 2, 1.0)  # the billboard's middle; w: on
        program["u_cut_eye"] = game_camera.eye()
        program["u_cut_floor"] = floor + 0.05
        program["u_cut_right"] = game_camera.right()
        program["u_cut_half"] = (w / 2 + MARGIN, h / 2 + MARGIN)  # (an upright billboard seen at the pitch: h tall)
        program["u_cut_round"] = ROUND

    R.Hd2dRenderer._bind_cutaway = bind

from hd2d_demo import HiddenGame  # noqa: E402

shots = json.loads(Path(shots_file).read_text(encoding="utf-8"))
game = HiddenGame(project, size=(1280, 720))
window = game.window
window.audio.set_muted(True)


def solid(hd, sprite):
    data = hd.draw(solid=sprite, read=True)
    a = np.frombuffer(bytes(data), dtype=np.uint8).reshape(720, 1280, 3)[::-1]  # (GL rows bottom-up)
    return (a[..., 0] > 200) & (a[..., 1] < 60)


res = {}
for shot in shots:
    game.load(shot["scene"])
    game.step(5)
    p = game.player()
    p.center_x = shot["player"][0]
    p.bottom = shot["player"][1]  # (the FEET: HD-2D stands a sprite on its bottom edge)
    window.motion_time = 0.0
    if hasattr(window, "water_time"):
        window.water_time = 0.0
    game.step(150)
    now_in = window.scene_controller.current_scene_path
    assert now_in.replace("\\", "/").endswith(shot["scene"].split("/")[-1]), (shot["name"], now_in)  # (no door taken)
    hd = window.hd2d_renderer
    keep = hd._cutaway
    cut = np.asarray(game.draw().convert("RGB")).astype(np.int16)
    m_cut = solid(hd, p)
    hd._cutaway = set()
    try:
        plain = np.asarray(game.draw().convert("RGB")).astype(np.int16)
        m_plain = solid(hd, p)
    finally:
        hd._cutaway = keep
    static, ground = hd.static, hd.ground
    hd.static, hd.ground = [], None
    try:
        m_full = solid(hd, p)
    finally:
        hd.static, hd.ground = static, ground
    from PIL import Image
    Image.fromarray(cut.astype(np.uint8)).save(out / f"{shot['name']}__{'proto' if proto else 'cut'}.png")
    Image.fromarray(plain.astype(np.uint8)).save(out / f"{shot['name']}__nocut.png")
    changed = np.abs(cut - plain).max(axis=2) > 0
    ys, xs = np.nonzero(m_full)
    box = None
    outside = int(changed.sum())
    if len(xs):
        x0, x1, y0, y1 = xs.min() - 16, xs.max() + 16, ys.min() - 16, ys.max() + 16
        box = [int(x0), int(y0), int(x1), int(y1)]
        inside = np.zeros_like(changed)
        inside[max(0, y0):y1 + 1, max(0, x0):x1 + 1] = True
        outside = int((changed & ~inside).sum())
    total = int(m_full.sum())
    res[shot["name"]] = {
        "scene": shot["scene"], "player_feet_px": shot["player"], "player_size_px": [abs(p.width), abs(p.height)],
        "note": shot.get("note", ""), "scene_after_settling": now_in,
        "floor": getattr(p, "mesh_hd2d_floor", None), "camera": {"pitch": hd.camera.pitch, "distance": round(hd.camera.distance, 2),
                                                               "fov": hd.camera.fov},
        "player_pixels": total,
        "visible_with_cut": round(float(m_cut.sum()) / total, 3) if total else None,
        "visible_without_cut": round(float(m_plain.sum()) / total, 3) if total else None,
        "cut_changed_px": int(changed.sum()), "cut_changed_outside_player_box_px": outside,
        "player_box_grown_16px": box}
    (out / f"report{'_proto' if proto else ''}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
game.close()
print("done", len(res))
