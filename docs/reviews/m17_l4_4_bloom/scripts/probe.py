"""Emission and glow statistics for a Lakeside shot. Usage: probe.py WORKTREE SHOT TIME [bloom spec]"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

WT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
ARGS = sys.argv[2:]
sys.path.insert(0, str(HERE))
sys.argv = [sys.argv[0], str(WT), str(HERE / "probe_out")] + sys.argv[2:]
import capture as C  # noqa: E402
import numpy as np  # noqa: E402


def read_float(tex, comps=3):
    from pyglet import gl
    w, h = tex.size
    buf = (gl.GLfloat * (w * h * comps))()
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex.glo)
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, gl.GL_FLOAT, buf)
    return np.frombuffer(buf, dtype=np.float32).reshape(h, w, comps)


def main():
    from hd2d_demo import HiddenGame
    shot, time = ARGS[0], ARGS[1]
    spec = ARGS[2] if len(ARGS) > 2 else "warm"
    game = HiddenGame(C.LAKE, size=(C.W, C.H))
    game.window.audio.set_muted(True)
    try:
        base, feet = C.SHOTS[shot]
        game.load(f"{C.SC}/{base}{C.TIMES[time]}.json")
        game.step(5)
        p = game.player(); p.center_x, p.bottom = feet
        game.window.motion_time = 0.0
        game.step(60)
        hd = game.window.hd2d_renderer
        hd.settings = C.variants()[spec](hd.settings)
        game.draw()
        e = read_float(hd._bloom.emission)
        y = e @ np.array([0.2126, 0.7152, 0.0722])
        print("lamps", [(l.intensity, l.color) for l in hd.lighting.lamps][:4])
        print("emission px>0", int((y > 0).sum()), "max", float(y.max()), "p99 of nonzero",
              float(np.percentile(y[y > 0], 99)) if (y > 0).any() else 0, "sum", float(y.sum()))
        glow = read_float(hd._bloom._chain[2][0][1])
        gy = glow @ np.array([0.2126, 0.7152, 0.0722])
        scale = (C.W * C.H) / (gy.shape[0] * gy.shape[1])
        print("glow base", gy.shape, "max", float(gy.max()), "sum*area", float(gy.sum() * scale), "last", hd.last_bloom)
    finally:
        game.close()


main()
