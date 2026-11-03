"""Runner calibration (#422): how fast this machine is, measured the same way on every run.

CI's GL is Mesa's llvmpipe, which draws on the CPU, so a GPU lane's time and every frame time in it depend on the
runner as much as on the engine: the same commit's Windows gpu lane took 22-38 min on different runners. This
measures the runner with fixed work, so a slow run can be told from a slower engine:

* ``cpu``, ``vcpus``: the processor and how many logical CPUs the runner has;
* ``cpu_ms``: a fixed pure-Python loop (one core), median of 5;
* ``gl_frame_ms``: a fixed full-screen fragment shader drawn into a 960x540 framebuffer and finished, median of 15
  frames after 3 warm-up frames, in a hidden window: what llvmpipe's rasterising costs on this runner.

Reporting only: nothing is judged against these numbers. ``python -m tooling.test_tiers gpu`` runs this before and
after its tests and puts both in the lane summary; it also runs alone and prints the JSON:

    python -m tooling.runner_calibration
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from typing import Any

FRAME = (960, 540)
VS = """#version 330
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""
FS = """#version 330
uniform float t;
out vec4 colour;
void main() {
    vec2 p = gl_FragCoord.xy / 64.0;
    float v = 0.0;
    for (int i = 0; i < 24; i++) { v += sin(p.x * float(i) + t) * cos(p.y + v); }
    colour = vec4(fract(v), 0.0, 0.0, 1.0);
}
"""


def cpu_model() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def cpu_ms() -> float:
    times = []
    for _ in range(5):
        start = time.perf_counter()
        sum(i * i % 7 for i in range(300_000))
        times.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(times), 2)


def gl_frame_ms() -> float:
    import arcade
    from arcade.gl import geometry

    window = arcade.Window(64, 64, visible=False)
    try:
        ctx = window.ctx
        program = ctx.program(vertex_shader=VS, fragment_shader=FS)
        quad = geometry.quad_2d_fs()
        fbo = ctx.framebuffer(color_attachments=[ctx.texture(FRAME, components=4)])
        times = []
        for frame in range(3 + 15):
            start = time.perf_counter()
            with fbo.activate():
                program["t"] = float(frame)
                quad.render(program)
            ctx.finish()
            if frame >= 3:
                times.append((time.perf_counter() - start) * 1000)
        return round(statistics.median(times), 2)
    finally:
        window.close()


def calibrate() -> dict[str, Any]:
    out: dict[str, Any] = {"cpu": cpu_model(), "vcpus": os.cpu_count(), "cpu_ms": cpu_ms()}
    try:
        out["gl_frame_ms"] = gl_frame_ms()
    except Exception as exc:  # noqa: BLE001 - reporting only: a calibration that can't draw says why, never fails
        out["gl_error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


if __name__ == "__main__":
    print(json.dumps(calibrate()))
