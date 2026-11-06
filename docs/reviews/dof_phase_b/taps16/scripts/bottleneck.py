"""Scratch: what the ~1.2 ms in-frame step is (Lakeside shop/bridge, 1080p, RTX 4070). Paired off/on, whole renderer
draw timed, variants of the composite (product code untouched; the module's FRAGMENT swapped in this process only):
  taps16      the product shader, 16 samples
  taps0       no samples: the centre colour + the centre depth read only (the pass's fixed cost)
  colour_only no depth read at all (the colour copied through the DoF program, depth still bound)
  taps16_x2   16 samples, the pass drawn twice in the frame (is the step paid once per frame or per pass?)
Usage: bottleneck.py PROJECT OUT CYCLES
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-dof")
sys.path.insert(0, r"D:\Games\Mesh-dof\tooling")
import dof_study  # noqa: E402
from dof_study import Study  # noqa: E402

import engine.hd2d.dof as dof  # noqa: E402
import engine.hd2d.renderer as rmod  # noqa: E402

project, out, cycles = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

PRODUCT = dof.FRAGMENT
COLOUR_ONLY = PRODUCT.replace("float zc = lin(texelFetch(u_depth, px, 0).r);", "float zc = u_focus;")
assert COLOUR_ONLY != PRODUCT
original_composite = rmod.Hd2dRenderer._composite_dof


def twice(self, frame, cam, viewport):
    original_composite(self, frame, cam, viewport)
    original_composite(self, frame, cam, viewport)


original_render = dof.DofPass.render


def no_depth_bound(self, quad, colour, depth, **kw):
    original_render(self, quad, colour, colour, **kw)  # the colour texture on unit 1: the depth texture never bound


VARIANTS = {"taps16": (PRODUCT, 16, 12, original_composite, original_render),
            "taps0": (PRODUCT, 0, 0, original_composite, original_render),
            "colour_only": (COLOUR_ONLY, 0, 0, original_composite, original_render),
            "colour_only_depth_unbound": (COLOUR_ONLY, 0, 0, original_composite, no_depth_bound),
            "taps16_x2": (PRODUCT, 16, 12, twice, original_render)}


def q(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))] / 1e6, 4)


st = Study(project, out, (1920, 1080))
res = {}
try:
    with dof_study.warnings.catch_warnings():
        dof_study.warnings.filterwarnings("ignore", message="draw_text is an extremely slow function")
        for view, place in (("lakeside_shop", (1168.0, 456.0)), ("lakeside_bridge", (1040.0, 900.0))):
            st._timing = False
            st.game.load("packs/core_regions/scenes/lakeside.json")
            st.game.step(5)
            p = st.game.player()
            p.center_x, p.center_y = place
            st.game.step(90)
            st._timed_draw()
            st._timing = True
            for rnd in range(2):  # each variant twice, in turn (drift falls on all)
                for name, (frag, tmax, tmin, comp, rend) in VARIANTS.items():
                    dof.FRAGMENT, dof.TAPS_MAX, dof.TAPS_MIN = frag, tmax, tmin
                    rmod.Hd2dRenderer._composite_dof = comp
                    dof.DofPass.render = rend
                    if st.hd._dof_pass is not None:
                        st.hd._dof_pass.release()
                        st.hd._dof_pass = None
                    inc = []
                    for c in range(30 + cycles):
                        st.game.step(1)
                        st.set_dof(None)
                        st.draw_ns = []
                        st.window.dispatch_event("on_draw")
                        off = st.draw_ns[-1]
                        st.set_dof(dof.SUBTLE)
                        st.draw_ns = []
                        st.window.dispatch_event("on_draw")
                        if c >= 30:
                            inc.append(st.draw_ns[-1] - off)
                    key = f"{view}/{name}"
                    res.setdefault(key, []).append({"p50": q(inc, .5), "p95": q(inc, .95),
                                                    "over_1ms": sum(1 for x in inc if x > 1e6), "n": len(inc)})
            (out / "bottleneck.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
finally:
    dof.FRAGMENT, dof.TAPS_MAX, dof.TAPS_MIN = PRODUCT, 24, 12
    rmod.Hd2dRenderer._composite_dof = original_composite
    dof.DofPass.render = original_render
    st.close()
print(json.dumps(res, indent=1))
