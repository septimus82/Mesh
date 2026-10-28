"""Milestone 23A: Mesh Studio's workspace at different window sizes, in hidden windows with Studio's own input events.

    py -3.13 tooling/studio_workspace.py shots OUT      fresh HD-2D and 2D projects: Studio at 640 x 480, 1280 x 720,
                                                        1920 x 1080 and 2560 x 1440; a picture of each, the 3D/2D
                                                        view's size, what the top bar and the panels can't show

The projects are made in OUT; nothing is played aloud (their master volume is 0); the player's settings file is OUT's
own."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
from hd2d_room_studio import _silent, _write  # noqa: E402

SIZES = ((640, 480), (1280, 720), (1920, 1080), (2560, 1440))


def make(out: Path, name: str, template: str) -> Path:
    project = out / name
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", name, "--dest", str(out), "--template", template],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    return project


def resize(d: Any, w: int, h: int) -> None:
    d.window.set_size(w, h)
    d.window.dispatch_event("on_resize", d.window.width, d.window.height)  # (as big as the desktop allows)
    d.frame(3)


def layout(d: Any) -> dict[str, Any]:
    """The workspace as it is: the view's size, the top bar's buttons past the window's edge, the panels' rows."""
    studio = d.studio
    left, right, bottom, top = studio._map_rect()
    w = d.window.width
    bar = [x for x in studio.ui.walk_widgets() if hasattr(x, "on_click") and isinstance(getattr(x, "text", None), str)
           and x.rect.bottom >= d.window.height - 44]
    past = [x.text for x in bar if x.rect.right > w]
    return {"window": [w, d.window.height], "view": [round(right - left), round(top - bottom)],
            "view_share": round((right - left) * (top - bottom) / (w * d.window.height), 3),
            "top_bar_past_edge": past, "left_more": list(getattr(studio, "_left_more", (0, 0))),
            "right_more": list(getattr(studio, "_panel_more", (0, 0)))}


def shots(out: Path, *, tag: str = "") -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    report: dict[str, Any] = {}
    for kind, template in (("hd2d", "hd2d_rpg"), ("2d", "starter")):
        project = make(out, f"ws_{kind}", template)
        d = StudioDriver(project)
        try:
            for w, h in SIZES:
                resize(d, w, h)
                d.picture(pics / f"{tag}{kind}_{w}x{h}.png")
                report[f"{kind} {w}x{h}"] = layout(d)
        finally:
            d.close()
    return report


def _click(d: Any, text: str) -> None:
    """Click a button in view (no scrolling, no switching): a person's click on what they see."""
    d.frame()
    w = next(x for x in d.studio.ui.walk_widgets() if getattr(x, "text", None) == text and hasattr(x, "on_click"))
    r = w.rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)


def _shown(d: Any, text: str) -> bool:
    return any(getattr(x, "text", None) == text for x in d.studio.ui.walk_widgets())


def creator(out: Path) -> dict[str, Any]:
    """What a creator does, at 1280 x 720 unless said: the categories in turn, an object's inspector kept through
    them, a focused box saved with Ctrl+S, Undo and Redo, Play and Stop, the panels hidden and shown, Focus, every
    window size in turn, and a 2D project's tiles."""
    from hd2d_studio_demo import StudioDriver
    from studio_workflow_polish import _ctrl, _type_only

    from engine import project_ops as ops

    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    report: dict[str, Any] = {}
    project = make(out, "ws_creator", "hd2d_rpg")
    d = StudioDriver(project)
    try:
        k = d.arcade.key
        resize(d, 1280, 720)
        studio = d.studio
        # the categories: Terrain shows Sculpt, Paint and Scatter at once; Paint's and Scatter's brushes
        steps: dict[str, Any] = {}
        _click(d, "Terrain")
        steps["terrain"] = {"sculpt_paint_scatter_in_view": all(_shown(d, t) for t in ("Sculpt", "Paint", "Scatter"))}
        d.picture(pics / "creator_terrain_1280x720.png")
        _click(d, "Paint")
        steps["paint"] = {"tool": (studio.hd2d.sculpt or {}).get("tool"), "materials_in_view": _shown(d, "Earth")}
        d.picture(pics / "creator_paint_1280x720.png")
        _click(d, "Scatter")
        steps["scatter"] = {"tool": (studio.hd2d.sculpt or {}).get("tool"), "meadow_in_view": _shown(d, "Meadow")}
        d.picture(pics / "creator_scatter_1280x720.png")
        _click(d, "Objects")
        steps["objects"] = {"person_in_view": _shown(d, "Person"), "models_in_view": _shown(d, "Models..."),
                            "scatter_still_armed": (studio.hd2d.sculpt or {}).get("tool") == "scatter"}
        _click(d, "Environment")
        steps["environment"] = {"camera_and_sun": _shown(d, "Camera and sun..."), "lighting": _shown(d, "Lighting..."),
                                "wind": _shown(d, "Calm")}
        _click(d, "Audio")
        steps["audio"] = {"sounds": _shown(d, "Room sounds and ambience..."), "place": _shown(d, "Place a sound")}
        d.picture(pics / "creator_audio_1280x720.png")
        report["categories"] = steps
        # an object's inspector, kept through the categories and the panels hidden and shown
        npc = next(e["id"] for e in ops.entities(studio.project.scene()) if e.get("tag") == "npc")
        studio.select(npc)
        d.frame(2)
        name = ops.find_entity(studio.project.scene(), npc).get("name")
        kept = {}
        for title in ("Rooms", "Terrain", "Objects"):
            _click(d, title)
            kept[title] = studio.selected == npc and studio._focusable.get("name") is not None
        _click(d, "Inspector")
        kept["inspector_hidden"] = studio._focusable.get("name") is None and studio.selected == npc
        _click(d, "Inspector")
        kept["inspector_back"] = studio._focusable.get("name") is not None and studio._focusable["name"].text == name
        report["inspector_kept"] = kept
        # Ctrl+S in a focused box; Undo and Redo
        _type_only(d, "name", "Elder Oak")
        _ctrl(d, k.S)
        on_disk = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
        report["ctrl_s"] = {"message": studio.message, "focused": studio._focusable["name"].active,
                            "saved_name": next(e.get("name") for e in on_disk["entities"] if e.get("id") == npc)}
        _click(d, "Undo")
        undone = ops.find_entity(studio.project.scene(), npc).get("name")
        _click(d, "Redo")
        report["undo_redo"] = [undone, ops.find_entity(studio.project.scene(), npc).get("name")]
        # the panels hidden, Focus, and back; the wheel over each panel
        view0 = studio._map_rect()
        _click(d, "Tools")
        view_no_left = studio._map_rect()
        tools_hidden = not _shown(d, "Rooms")
        _click(d, "Tools")
        d.window.dispatch_event("on_key_press", k.TAB, 0)
        d.window.dispatch_event("on_key_release", k.TAB, 0)
        d.frame(2)
        focus = studio._map_rect()
        focus_clean = not _shown(d, "Rooms") and studio._focusable.get("name") is None
        d.picture(pics / "creator_focus_1280x720.png")
        d.window.dispatch_event("on_key_press", k.TAB, 0)
        d.window.dispatch_event("on_key_release", k.TAB, 0)
        d.frame(2)
        cam = studio.hd2d.camera.distance
        d.window.dispatch_event("on_mouse_scroll", 100, 300, 0, -3)
        d.window.dispatch_event("on_mouse_scroll", d.window.width - 100, 300, 0, -3)
        d.frame()
        report["panels"] = {"view": [round(view0[1] - view0[0])], "view_tools_hidden": round(view_no_left[1] - view_no_left[0]),
                            "tools_hidden": tools_hidden, "view_focus": [round(focus[1] - focus[0]), round(focus[3] - focus[2])],
                            "focus_clean": focus_clean, "back": round(studio._map_rect()[1] - studio._map_rect()[0]),
                            "wheel_over_panels_kept_the_view": studio.hd2d.camera.distance == cam}
        # Play and Stop
        d.key(k.F4)
        d.frame(20)
        mode = studio.mode
        d.key(k.F4)
        d.frame(5)
        report["play_stop"] = [mode, studio.mode, studio.selected == npc]
        # every size in turn, with the inspector open: what is shown, the view, nothing past the window
        sizes = {}
        for w, h in ((640, 480), (1920, 1080), (2560, 1440), (1280, 720)):
            resize(d, w, h)
            lw, rw = studio._panel_widths()
            past = [x.text for x in studio.ui.walk_widgets() if isinstance(getattr(x, "text", None), str) and x.text
                    and (x.rect.right > d.window.width + 1 or x.rect.left < -1 or x.rect.bottom < -1
                         or x.rect.top > d.window.height + 1)]
            sizes[f"{w}x{h}"] = {**layout(d), "panels": [lw, rw], "past_the_window": past[:5]}
            d.picture(pics / f"creator_selected_{w}x{h}.png")
        report["sizes"] = sizes
    finally:
        d.close()
    # a 2D project: its tiles, picked from the palette in the Terrain tab
    project2 = make(out, "ws_2d", "starter")
    d = StudioDriver(project2)
    try:
        resize(d, 1280, 720)
        studio = d.studio
        _click(d, "Terrain")
        d.frame(2)
        space = studio._sheet_space
        geometry = studio._sheet_geometry()
        assert space is not None and geometry is not None
        _tileset, px, cols, rows = geometry
        r = space.rect
        d.click(r.left + px * 1.5, r.top - px * 0.5)  # the second tile of the first row
        report["tiles_2d"] = {"palette": [cols, rows], "brush": studio.brush_label if hasattr(studio, "brush_label") else
                              studio.message, "tool": studio.tool}
        d.picture(pics / "creator_2d_terrain_1280x720.png")
    finally:
        d.close()
    return report


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    tag = sys.argv[3] if len(sys.argv) > 3 else ""
    report = {"shots": lambda: shots(out, tag=tag), "creator": lambda: creator(out)}[phase]()
    _write(out / f"{phase}{('_' + tag) if tag else ''}.json", report)
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
