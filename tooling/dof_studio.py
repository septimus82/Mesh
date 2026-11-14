"""#460 Phase B: an HD-2D room's depth of field set in Mesh Studio with its own controls (clicks, typing; hidden
windows), then saved, reopened, played and exported.

    py -3.13 tooling/dof_studio.py OUT [--no-export]

A fresh HD-2D template project in OUT: Camera and sun... > Depth of field: on (Subtle), Most blur 3, undo / redo; the
editing view stays sharp until Preview here; previewing, the world blurs but Studio's lines (grid, selection,
handles) are drawn after it, sharp; the status Studio shows when software rendering bypasses it; the cottage
(an interior: a steep camera) says why the effect is slight there; Save, reopen; Play; export, and the exported game
draws it. The player's settings file is OUT's own; nothing is played aloud."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
SCENES = "packs/core_regions/scenes"


def _flat(text: str) -> str:
    return " ".join(text.split())  # (a label's text as wrapped on screen, as one line)


def _world_pixels(d: Any) -> Any:
    """Studio's editing view as its renderer draws it (lines included), read before Studio's own panels, messages and
    tooltips are drawn over the canvas."""
    import numpy as np  # noqa: PLC0415

    d.advance()
    d.window.clear()
    d.studio.hd2d.draw()
    x, y, w, h = (int(v) for v in d.studio.hd2d.viewport())
    return np.asarray(d.arcade.get_image(x, y, w, h).convert("RGB")).copy()


def _overlay_mask(d: Any) -> tuple[Any, Any]:
    """(picture with Studio's lines, the pixels its lines change): the same view drawn with and without them."""
    import numpy as np  # noqa: PLC0415

    view = d.studio.hd2d
    with_lines = _world_pixels(d)
    kept = view._overlay
    view._overlay = lambda vp: None  # (this view only, to see what the lines add)
    try:
        without = _world_pixels(d)
    finally:
        view._overlay = kept
    return with_lines, np.abs(with_lines.astype(int) - without.astype(int)).max(axis=2) > 0


def studio(out: Path, *, export: bool = True) -> dict[str, Any]:
    import numpy as np  # noqa: PLC0415
    from hd2d_room_studio import _press, _right, _silent
    from hd2d_studio_demo import StudioDriver
    from PIL import Image  # noqa: PLC0415

    from engine import project_ops as ops

    pics = out / "pictures"
    pics.mkdir(parents=True, exist_ok=True)
    project = out / "game"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "hd2d_rpg"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        from engine.hd2d.dof import dof_unavailable_reason  # noqa: PLC0415

        report["software_renderer"] = software = dof_unavailable_reason(d.window.ctx)
        d.advance(5)
        report["before"] = ops.depth_of_field_of(d.studio.project.scene())
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
        d.advance(2)
        report["panel_labels"] = [_flat(t) for t in d.labels() if "depth" in t.lower() or "Not shown" in t]
        view = d.studio.hd2d  # (still: plants don't sway, fires don't burn, so two pictures can be compared)
        view.advance_motion = view.advance_weather = lambda dt: None
        d.advance(2)
        plain_before = _world_pixels(d)
        report["editing_view_still"] = bool(np.array_equal(plain_before, _world_pixels(d)))
        _press(d, "Depth of field: off", _right)
        d.advance(2)
        report["turned_on"] = {"stored": ((d.studio.project.scene().get("settings") or {}).get("hd2d") or {})
                               .get("depth_of_field"), "renderer_active": d.renderer.settings.depth_of_field.active,
                               "status": list(d.renderer.dof_status()), "message": d.studio.message}
        plain_after = _world_pixels(d)
        report["editing_view_unchanged_without_preview"] = bool(np.array_equal(plain_before, plain_after))
        changed = np.argwhere(np.abs(plain_before.astype(int) - plain_after.astype(int)).max(axis=2) > 0)
        report["editing_view_changed_box"] = ([int(v) for v in changed.min(axis=0)] + [int(v) for v in changed.max(axis=0)]
                                              + [int(len(changed))] if len(changed) else None)
        report["editing_view_drawn"] = d.renderer.last_dof is not None
        d.type_into("dof_max_blur", "3")
        set_value = ops.depth_of_field_of(d.studio.project.scene())["max_blur"]
        _press(d, "Undo")
        undone = ops.depth_of_field_of(d.studio.project.scene())["max_blur"]
        _press(d, "Redo")
        report["max_blur_set_undo_redo"] = [set_value, undone, ops.depth_of_field_of(d.studio.project.scene())["max_blur"]]
        d.advance(3)
        # Studio's lines without the preview, then with it: the blur under them, the lines the same pixels
        d.studio.hd2d.selected = None
        if software:  # (a software rasteriser: the pass drawn for this check anyway, to test the lines over it)
            d.renderer.dof_allow_software = True
        lines_off, mask_off = _overlay_mask(d)
        _press(d, "Preview here: off", _right)
        d.advance(3)
        lines_on, mask_on = _overlay_mask(d)
        Image.fromarray(lines_off).save(pics / "studio_preview_off.png")
        Image.fromarray(lines_on).save(pics / "studio_preview_on.png")
        union = mask_off | mask_on
        world = ~union
        report["preview"] = {
            "drawn": d.renderer.last_dof is not None,
            "line_pixels": [int(mask_off.sum()), int(mask_on.sum())],
            "line_pixels_same_share": round(float((mask_off & mask_on).sum() / max(1, union.sum())), 4),
            "world_changed_share": round(float((np.abs(lines_on.astype(int) - lines_off.astype(int)).max(axis=2)
                                                [world] > 2).mean()), 4)}
        # software rendering: the panel says so, and the view is drawn without it
        kept = d.renderer.dof_unavailable
        d.renderer.dof_allow_software = False
        d.renderer.dof_unavailable = kept or "depth of field is off on this computer (simulated software rendering)"
        d.studio._rebuild()
        d.advance(2)
        report["software_label"] = [_flat(t) for t in d.labels() if t.startswith("Not shown on this computer")]
        report["software_drawn"] = d.renderer.last_dof is not None
        d.renderer.dof_unavailable = kept
        _press(d, "Preview here: on", _right)
        d.advance(2)
        _press(d, "Save")
        report["saved"] = d.studio.message
    finally:
        d.close()
    room = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    report["in_the_saved_file"] = room["settings"]["hd2d"].get("depth_of_field")
    d = StudioDriver(project)
    try:
        d.advance(5)
        report["reopened"] = {"same": ops.depth_of_field_of(d.studio.project.scene())["max_blur"] == 3.0,
                              "unsaved": sorted(d.studio.project.dirty)}
        k = d.arcade.key
        d.key(k.F4)
        for _ in range(30):
            d.advance()
            time.sleep(1 / 60)
        r = d.window.hd2d_renderer
        report["in_play"] = {"mode": d.studio.mode, "status": list(r.dof_status()),
                             "load_message": getattr(d.window, "hd2d_dof_message", None),
                             "drawn": r.last_dof is not None, "radius": (r.last_dof or {}).get("radius"),
                             "max_blur": r.settings.depth_of_field.max_blur}
        d.picture(pics / "play_dof.png")
        d.key(k.F4)
        d.advance(5)
        # the interior: a steep camera, off by default, the panel says the effect is slight there
        _press(d, "Cottage", lambda w: w.rect.left < 230)
        d.advance(5)
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
        d.advance(2)
        def note() -> Any:
            return next((w for w in d.studio.ui.walk_widgets()
                         if "few metres of depth" in _flat(getattr(w, "mesh_text", None) or getattr(w, "text", "") or "")),
                        None)
        d._scroll_panels(note)  # (the panel builds its rows as they scroll into view)
        report["indoor"] = {"room": d.studio.project.current, **ops.depth_of_field_of(d.studio.project.scene()),
                            "note": [_flat(t) for t in d.texts() if "few metres of depth" in _flat(t)]}
    finally:
        d.close()
    if export:
        report["export"] = _export(project, out)
    return report


def _export(project: Path, out: Path) -> dict[str, Any]:
    bundle = out / "export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from pathlib import Path
game = HiddenGame(Path({str(bundle)!r}))
try:
    game.load("{SCENES}/start.json")
    game.step(60)
    game.draw()
    r = game.window.hd2d_renderer
    print(json.dumps({{"engine_from": engine.__file__, "status": list(r.dof_status()), "drawn": r.last_dof is not None,
                      "max_blur": r.settings.depth_of_field.max_blur,
                      "message": getattr(game.window, "hd2d_dof_message", None)}}))
finally:
    game.window.close()
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        run = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        run = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    copied = next((p for p in bundle.rglob("start.json") if p.as_posix().endswith(f"{SCENES}/start.json")), None)
    exported = json.loads(copied.read_text(encoding="utf-8")) if copied is not None else {}
    return {"code": built.returncode, "bundle_run": run,
            "scene_setting": ((exported.get("settings") or {}).get("hd2d") or {}).get("depth_of_field")}


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = studio(out, export="--no-export" not in sys.argv)
    (out / "dof_studio.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
