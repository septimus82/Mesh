"""GPU-object lifetime across scene loads and Mesh Studio Play / Stop (post-M16 health check), in hidden windows.

    py -3.13 tooling/gpu_lifetime_probe.py OUT.json

Builds three throwaway projects in a temporary folder (a 2D room without lights, the same room with two lights,
and the lit HD-2D crossing), then for each: loads the room repeatedly, and runs Mesh Studio's Edit -> Play -> Stop
repeatedly. Live GL objects (created minus freed, after arcade's own ``ctx.gc()``) are counted with Python's cyclic
garbage collector switched off (what explicit ownership frees) and again after ``gc.collect()`` (what only the
cycle collector frees). Ends by closing the window. Nothing is shown, nothing outside the temporary folder is
written.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

KINDS = ("texture", "framebuffer", "program", "buffer")
SCENE = "packs/core_regions/scenes/start.json"
LIGHTS = [{"id": "a", "x": 200, "y": 200, "radius": 150, "color": "#ffb060", "mode": "soft"},
          {"id": "b", "x": 500, "y": 300, "radius": 150, "color": "#5a8cff", "mode": "soft"}]


def _counts(ctx: Any) -> dict[str, int]:
    ctx.gc()
    return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}


def _projects(work: Path) -> dict[str, Path]:
    import hd2d_floors_demo

    from engine.project_scaffold import create_project

    plain, lit = work / "plain_2d", work / "lit_2d"
    create_project(plain, "plain", "blank")
    create_project(lit, "lit", "blank")
    scene_file = lit / SCENE
    scene = json.loads(scene_file.read_text(encoding="utf-8"))
    scene["lights"] = LIGHTS
    scene.setdefault("settings", {})["lighting_enabled"] = True
    scene_file.write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return {"2d_no_lights": plain, "2d_with_lights": lit, "hd2d_with_lights": hd2d_floors_demo.build(work / "hd2d")}


def _run(project: Path, rounds: int) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    out: dict[str, Any] = {}
    d = StudioDriver(project)
    ctx = d.window.ctx
    k = d.arcade.key
    try:
        gc.collect()
        gc.disable()  # from here, only explicit releases (and plain reference counting) free GL objects
        try:
            start = _counts(ctx)
            for _ in range(rounds):
                d.studio._reload()  # what every Studio edit, undo or room switch does
                d.frame()
            reloads = _counts(ctx)
            for _ in range(rounds):
                d.key(k.F4)
                d.frame(2)
                d.key(k.F4)
            plays = _counts(ctx)
        finally:
            gc.enable()
        gc.collect()
        after_gc = _counts(ctx)
        out = {"start": start, f"after_{rounds}_reloads": reloads, f"after_{rounds}_play_stop": plays,
               "after_gc_collect": after_gc,
               "growth_without_cycle_gc": {k: plays[k] - start[k] for k in KINDS},
               "growth_after_gc": {k: after_gc[k] - start[k] for k in KINDS}}
    finally:
        d.close()
    return out


def main(out_path: Path, rounds: int = 4) -> dict[str, Any]:
    report: dict[str, Any] = {"rounds": rounds}
    with tempfile.TemporaryDirectory(prefix="mesh_gpu_probe_") as tmp:
        work = Path(tmp)
        os.environ.setdefault("MESH_USER_DIR", str(work / "user"))
        os.environ.setdefault("MESH_PROJECTS_DIR", str(work / "projects"))
        os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(work / "user_settings.json"))
        os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
        for name, project in _projects(work).items():
            report[name] = _run(project, rounds)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]).resolve()), indent=1))
