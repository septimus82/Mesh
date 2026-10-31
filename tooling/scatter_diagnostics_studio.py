"""Milestone 22C: Lakeside Village's scatter problem in Mesh Studio, with its own input events in a hidden window:
a dense meadow dragged over an HD-2D room, then small trees and rocks dragged over it, the meadow again, and a
thinning stroke where nothing was scattered; what Studio says each time, and whether the room changed.

    py -3.13 tooling/scatter_diagnostics_studio.py studio OUT

Nothing is played aloud (the project's master volume is 0); the player's settings file is OUT's own."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
from hd2d_room_studio import _write  # noqa: E402


def _scatter_rows(d: Any) -> int:
    hd2d = (d.studio.project.scene().get("settings") or {}).get("hd2d") or {}
    return sum(len(v) for v in (hd2d.get("scatter") or {}).values())


def _drag_rows(d: Any, rows: list[float], x0: float = 12.0, x1: float = 28.0, *, held: int | None = None) -> None:
    """One stroke: the brush dragged to and fro across the room along each row (m north), without letting go, as a
    person would; ``held``: a key held all the while (Ctrl thins)."""
    points = [d.screen((x, y, 0.0)) for k, y in enumerate(rows) for x in ((x0, x1) if k % 2 == 0 else (x1, x0))]
    assert all(d.studio._in_map(*p) for p in points), "the stroke is in the 3D view"
    left = d.arcade.MOUSE_BUTTON_LEFT
    if held is not None:
        d.window.dispatch_event("on_key_press", held, 0)
    d.window.dispatch_event("on_mouse_motion", *points[0], 0, 0)
    d.window.dispatch_event("on_mouse_press", *points[0], left, 0)
    last = points[0]
    for a, b in zip(points, points[1:]):
        for i in range(1, 25):
            p = (a[0] + (b[0] - a[0]) * i / 24, a[1] + (b[1] - a[1]) * i / 24)
            d.window.dispatch_event("on_mouse_drag", p[0], p[1], p[0] - last[0], p[1] - last[1], left, 0)
            last = p
            d.frame()
    d.window.dispatch_event("on_mouse_release", *last, left, 0)
    if held is not None:
        d.window.dispatch_event("on_key_release", held, 0)
    d.frame()


def _step(d: Any, undo_before: int, rows_before: int) -> dict[str, Any]:
    return {"message": d.studio.message, "message_ok": d.studio.message_ok, "rows": _scatter_rows(d),
            "rows_changed": _scatter_rows(d) != rows_before, "undo_steps_added": len(d.studio.project._undo) - undo_before}


def studio(out: Path) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver
    from studio_workflow_polish import _press_left, _project

    project = _project(out)
    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        k = d.arcade.key
        _press_left(d, "Meadow")
        d.button("Scatter")
        d.button("Meadow")
        d.type_into("scatter_radius", "3")

        def stroke(name: str, collection: str, rows: list[float], **kw: Any) -> None:
            if collection:
                if collection not in [getattr(w, "text", None) for w in d.studio.ui.walk_widgets()]:
                    d.button("One thing at a time...")
                d.button(collection)
            undo, before = len(d.studio.project._undo), _scatter_rows(d)
            _drag_rows(d, rows, **kw)
            report[name] = _step(d, undo, before)
            d.picture(pics / f"{len(report):02d}_{name}.png")

        stroke("meadow", "", [11.0, 13.0, 15.0, 17.0, 19.0])
        stroke("trees_over_meadow", "Small tree", [13.0, 15.0, 17.0])
        stroke("rocks_over_meadow", "Rocks", [13.0, 15.0, 17.0])
        stroke("meadow_again", "Meadow", [13.0, 15.0])
        stroke("thin_where_nothing_is", "", [3.5], held=k.LCTRL)
    finally:
        d.close()
    return report


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = {"studio": lambda: studio(out)}[phase]()
    _write(out / f"{phase}.json", report)
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
