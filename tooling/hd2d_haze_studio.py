"""M17-L4-3: an HD-2D room's haze set in Mesh Studio with its own controls (clicks, typing; hidden windows), then played,
saved, reopened and exported.

    py -3.13 tooling/hd2d_haze_studio.py OUT [--no-export]

A fresh HD-2D template project in OUT, its start room: Camera and sun... > Haze: Daytime haze (the editing view hazed at once,
by its own depth; Studio's lines drawn after it, the same pixels), strength, colour, start and falloff typed, a bad
colour refused, undo / redo, Off (the view exactly as before); the game's camera path draws Studio's view the same (one
renderer, one composite); with the colour grade too; Play; Save, reopen, export, and the exported game draws it; then
the saved room hand-edited so its preset is a list: Studio opens it off, says why, and a preset repairs it."""

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


def _canvas(d: Any, lines: bool = False) -> Any:
    """Studio's editing view as its renderer draws it, read before Studio's panels are drawn over it."""
    import numpy as np  # noqa: PLC0415

    view = d.studio.hd2d
    kept = view._overlay
    if not lines:
        view._overlay = lambda vp: None
    try:
        d.advance()
        d.window.clear()
        view.draw()
        x, y, w, h = (int(v) for v in view.viewport())
        return np.asarray(d.arcade.get_image(x, y, w, h).convert("RGB")).copy()
    finally:
        view._overlay = kept


def _stored(d: Any) -> Any:
    return ((d.studio.project.scene().get("settings") or {}).get("hd2d") or {}).get("haze")


def _between(d: Any, top: str, below: str) -> Any:
    """Buttons on the right panel between the heading ``top`` and the heading ``below`` (several sections have an Off,
    the sun has an Evening)."""
    def heading(text: str) -> Any:
        return next((h for h in d.studio.ui.walk_widgets() if getattr(h, "text", None) == text), None)

    def where(w: Any) -> bool:
        a, b = heading(top), heading(below)
        return (a is not None and b is not None and w.rect.left > 900 and w.rect.top <= a.rect.bottom
                and w.rect.bottom >= b.rect.top)
    return where


def _in_haze(d: Any) -> Any:
    return _between(d, "Haze", "Sun and sky")


def _escape(d: Any, key: str) -> str:
    """Click the box ``key`` and press Esc, as Studio asks after a refused value: it puts back what the box had."""
    field = d.studio._focusable[key]
    d.advance()
    r = field.rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)
    d.key(d.arcade.key.ESCAPE)
    return str(d.studio.message)


def _parity(d: Any) -> dict[str, Any]:
    """The game's camera path (no camera passed) set to Studio's view against Studio's path, both drawn with the sun's
    shadow map fitted to the same game camera (#485) and play's cutaway off: the same picture, haze included."""
    import numpy as np  # noqa: PLC0415

    hd, view = d.renderer, d.studio.hd2d
    ctx = hd.ctx
    _x, _y, w, h = (int(v) for v in view.viewport())

    def at_origin(camera: Any) -> Any:
        tex = ctx.texture((w, h), components=4)
        fbo = ctx.framebuffer(color_attachments=[tex])
        try:
            fbo.use()
            return np.frombuffer(hd.draw(camera=camera, read_final=True), dtype=np.uint8).copy()
        finally:
            d.window.use()
            fbo.delete()
            tex.delete()

    gc, sc = hd.camera, view.camera
    saved = (gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw, hd._camera_ready)
    gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw = sc.target, sc.pitch, sc.fov, sc.distance, sc.ortho, sc.yaw
    hd._camera_ready = True
    kept_cut, kept_followed = hd._bind_cutaway, hd.followed
    try:
        hd._bind_cutaway = lambda mp, cam: kept_cut(mp, None)
        hd.followed = lambda: None  # (nobody followed: the game's focus is the view's target, as Studio's is)
        game = at_origin(None)
        game_onset = hd.last_haze["onset"] if hd.last_haze else None
        studio = at_origin(sc)
        stage = hd.last_stage
        studio_onset = hd.last_haze["onset"] if hd.last_haze else None
    finally:
        hd._bind_cutaway, hd.followed = kept_cut, kept_followed
        gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw, hd._camera_ready = saved
    return {"same": bool(np.array_equal(game, studio)), "stage": stage, "onsets": [game_onset, studio_onset]}


def studio(out: Path, *, export: bool = True) -> dict[str, Any]:
    import numpy as np  # noqa: PLC0415
    from hd2d_room_studio import _press, _silent
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
    original = (project / SCENES / "start.json").read_bytes()
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        d.advance(5)
        report["before"] = ops.haze_of(d.studio.project.scene())
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
        d.advance(2)
        view = d.studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None
        d.advance(2)
        plain = _canvas(d)
        report["still"] = bool(np.array_equal(plain, _canvas(d)))
        lines_plain = _canvas(d, lines=True)
        _press(d, "Daytime haze", _in_haze(d))
        d.advance(2)
        hazed = _canvas(d)
        report["daytime"] = {"stored": _stored(d), "message": d.studio.message, "stage": d.renderer.last_stage,
                             "renderer_preset": getattr(d.renderer.settings.haze, "preset", None),
                             "changed_share": round(float((np.abs(hazed.astype(int) - plain.astype(int)).max(axis=2)
                                                           > 0).mean()), 4),
                             "fields": [k for k in ("haze_strength", "haze_color", "haze_start", "haze_falloff")
                                        if k in d.studio._focusable]}
        Image.fromarray(plain).save(pics / "studio_off.png")
        Image.fromarray(hazed).save(pics / "studio_daytime.png")
        calls: list[str] = []
        drawn_after = d.renderer._overlay_after

        def counted(*a: Any, **k: Any) -> None:
            calls.append(d.renderer.last_stage)
            drawn_after(*a, **k)

        d.renderer._overlay_after = counted
        try:
            lines_hazed = _canvas(d, lines=True)
        finally:
            d.renderer._overlay_after = drawn_after
        mask_off = np.abs(lines_plain.astype(int) - plain.astype(int)).max(axis=2) > 0
        mask_on = np.abs(lines_hazed.astype(int) - hazed.astype(int)).max(axis=2) > 0
        union = mask_off | mask_on
        report["lines"] = {"after_calls": calls, "pixels": [int(mask_off.sum()), int(mask_on.sum())],
                           "same_share": round(float((mask_off & mask_on).sum() / max(1, union.sum())), 4)}
        report["parity"] = _parity(d)
        d.type_into("haze_strength", "0.4")
        d.type_into("haze_color", "#a0b8d0")
        d.type_into("haze_start", "2")
        d.type_into("haze_falloff", "20")
        report["typed"] = _stored(d)
        d.type_into("haze_color", "bluish")
        report["bad_colour"] = {"stored": _stored(d), "message": d.studio.message, "ok": d.studio.message_ok,
                                "put_back": _escape(d, "haze_color")}
        d.type_into("haze_strength", "0.9")
        report["too_strong"] = {"stored": _stored(d), "message": d.studio.message, "ok": d.studio.message_ok,
                                "put_back": _escape(d, "haze_strength")}
        _press(d, "Undo")
        report["undone"] = _stored(d)
        _press(d, "Redo")
        report["redone"] = _stored(d)
        h = d.renderer.settings.haze
        report["redone_renderer"] = {"strength": h.strength, "start": h.start, "falloff": h.falloff,
                                     "color": None if h.color is None else [round(c, 4) for c in h.color]}
        report["op_parity"] = ops.set_hd2d_haze(json.loads(original), preset="daytime", strength=0.4, color="#a0b8d0",
                                                start=2, falloff=20)["settings"]["hd2d"]["haze"] == _stored(d)
        _press(d, "Golden hour", _between(d, "Picture", "Haze"))  # (the grade too: haze first, then it, one pass)
        d.advance(2)
        both = _canvas(d)
        report["with_grade"] = {"stage": d.renderer.last_stage, "post": getattr(d.renderer.settings.post, "preset", None)}
        Image.fromarray(both).save(pics / "studio_haze_grade.png")
        _press(d, "Off", _between(d, "Picture", "Haze"))
        d.advance(2)
        _press(d, "Haze: off", _in_haze(d))
        d.advance(2)
        report["off"] = {"stored": _stored(d), "stage": d.renderer.last_stage,
                         "view_same_as_before": bool(np.array_equal(_canvas(d), plain))}
        _press(d, "Evening haze", _in_haze(d))
        d.advance(2)
        k = d.arcade.key
        d.key(k.F4)
        for _ in range(30):
            d.advance()
            time.sleep(1 / 60)
        r = d.window.hd2d_renderer
        report["in_play"] = {"mode": d.studio.mode, "preset": getattr(r.settings.haze, "preset", None),
                             "stage": r.last_stage, "haze": r.last_haze}
        d.picture(pics / "play_evening.png")
        d.key(k.F4)
        d.advance(5)
        _press(d, "Save")
        report["saved"] = d.studio.message
    finally:
        d.close()
    room_doc = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    report["in_the_saved_file"] = room_doc["settings"]["hd2d"].get("haze")
    without = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    without["settings"]["hd2d"].pop("haze", None)
    report["rest_of_the_room_unchanged"] = without == json.loads(original)
    d = StudioDriver(project)
    try:
        d.advance(5)
        report["reopened"] = {"haze": ops.haze_of(d.studio.project.scene()), "unsaved": sorted(d.studio.project.dirty),
                              "renderer_preset": getattr(d.renderer.settings.haze, "preset", None)}
    finally:
        d.close()
    if export:
        report["export"] = _export(project, out)
    report["malformed"] = _malformed(project)
    return report


def _malformed(project: Path) -> dict[str, Any]:
    """The saved room hand-edited so its preset isn't a name (a list): Studio opens it with the haze off and the reason
    shown in Camera and sun... > Haze; choosing a preset repairs it (one undo step) and the view takes it."""
    from hd2d_room_studio import _press
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    path = project / SCENES / "start.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["settings"]["hd2d"]["haze"] = {"preset": ["daytime"], "strength": 0.2}
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    d = StudioDriver(project)
    try:
        d.advance(5)
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
        d.advance(2)
        _canvas(d)

        def warned() -> bool:
            d._scroll_panels(lambda: "Evening haze" in d.texts())
            return any("can't be read" in t and "settings.hd2d.haze.preset" in t for t in d.texts())

        found: dict[str, Any] = {"haze_of": ops.haze_of(d.studio.project.scene()),
                                 "renderer_haze": d.renderer.settings.haze,
                                 "renderer_error": d.renderer.settings.haze_error, "stage": d.renderer.last_stage,
                                 "warning": warned()}
        _press(d, "Daytime haze", _in_haze(d))
        d.advance(2)
        _canvas(d)
        found["repaired"] = {"stored": _stored(d), "renderer_preset": getattr(d.renderer.settings.haze, "preset", None),
                             "stage": d.renderer.last_stage, "warning": warned()}
        _press(d, "Undo")
        d.advance(2)
        found["undone"] = _stored(d)
    finally:
        d.close()
    return found


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
    print(json.dumps({{"engine_from": engine.__file__, "preset": getattr(r.settings.haze, "preset", None),
                      "stage": r.last_stage}}))
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
            "scene_setting": ((exported.get("settings") or {}).get("hd2d") or {}).get("haze")}


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = studio(out, export="--no-export" not in sys.argv)
    (out / "haze_studio.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1, default=str)[:8000])


if __name__ == "__main__":
    main()
