"""H6.1 diagnostic (temporary, removed before review): evidence for the five GL tests failing on CI's Mesa.

    python .github/diag/h61_diag.py OUT.json [fonts] [labels] [motion] [resize]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tooling"), str(REPO)]
os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
OUT, PARTS = Path(sys.argv[1]), set(sys.argv[2:]) or {"fonts", "labels", "motion", "resize"}
REPORT: dict = {"platform": sys.platform}


def save() -> None:
    OUT.write_text(json.dumps(REPORT, indent=1, default=str) + "\n", encoding="utf-8")


def fonts() -> None:
    import pyglet

    from engine.studio_ui import FONT

    REPORT["fonts"] = {"have": {name: pyglet.font.have_font(name) for name in FONT},
                       "loaded_for_studio": pyglet.font.load(FONT, 10).name}


def labels() -> None:
    import hd2d_studio_demo

    seen: list[str] = []
    original = hd2d_studio_demo.StudioDriver.labels

    def recording(self):  # noqa: ANN001, ANN202
        out = original(self)
        seen.extend(out)
        return out

    setattr(hd2d_studio_demo.StudioDriver, "labels", recording)  # noqa: B010
    keys = ("lights it", "can show", "would", "nowhere", "starting", "This world")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(root / "settings.json")
        import m23d_start_music_studio as start

        REPORT["start_rows"] = start.older(root / "start")["rows"]
        import m23b_fire_study as fire

        REPORT["fire_eight"] = fire.edges(root / "fire")["eight_lamps"]
        import hd2d_asset_pipeline_demo as pipeline

        steps = {s["step"]: s for s in pipeline.check(root / "pipeline")["steps"]}
        REPORT["reimport_plan"] = steps["reimport"]["plan"]
    REPORT["label_texts_with_keys"] = sorted({t for t in seen if any(k in t.replace("\n", " ") for k in keys)})
    save()


def motion() -> None:
    import m20e_motion_study as study
    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        game = study.open_room(Path(tmp), "foot", wind={"speed": 12.0, "direction": 0.0, "gust": 0.8},
                               motion={"enabled": True, "sway": 2.0})
        try:
            layer = game.window.hd2d_renderer.scatter
            x, y = 15.0, 4.0
            layer.set_instances({})
            plain = np.asarray(study.at(game, 3.0, x, y))
            layer.set_instances({"reeds": [(round(x * 32), round(y * 32), 0, 160)]})
            rows = []
            for t in (3.0, 3.3, 3.6, 4.1, 4.7):
                mask = np.any(np.asarray(study.at(game, t, x, y)) != plain, axis=2)
                ys, xs = np.nonzero(mask)
                bottom = int(ys.max())
                rows.append({"t": t, "bottom_y": bottom,
                             "bottom_rows": {int(r): [int(v) for v in sorted(xs[ys == r])] for r in range(bottom - 3, bottom + 1)},
                             "top_mean_x": float(xs[ys == ys.min()].mean())})
            REPORT["motion_rows"] = rows
        finally:
            game.close()
    save()


def resize() -> None:
    import pyglet

    screen = pyglet.display.get_display().get_default_screen()
    window = pyglet.window.Window(960, 540, visible=False)
    try:
        before = window.get_size()
        window.set_size(1280, 720)
        window.dispatch_events()
        REPORT["resize"] = {"screen": [screen.width, screen.height], "before": list(before),
                            "after_set_size_1280x720": list(window.get_size()),
                            "framebuffer": list(window.get_framebuffer_size())}
    finally:
        window.close()
    save()


for name in ("fonts", "resize", "motion", "labels"):
    if name in PARTS:
        try:
            globals()[name]()
        except Exception as exc:  # noqa: BLE001  # REASON: a diagnostic records every part it can
            REPORT[f"{name}_error"] = f"{type(exc).__name__}: {exc}"
        save()
print(json.dumps(REPORT, indent=1, default=str)[:6000])
