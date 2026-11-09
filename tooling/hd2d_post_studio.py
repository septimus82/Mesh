"""M17-L4-2: an HD-2D room's colour grade and vignette set in Mesh Studio with its own controls (clicks, typing; hidden
windows) and by an AI proposal, then played, saved, reopened and exported.

    py -3.13 tooling/hd2d_post_studio.py OUT [--no-export]

A fresh HD-2D template project in OUT, its start room: Camera and sun... > Picture: Natural (the editing view graded at
once; Studio's lines drawn after it, the same pixels), strength and vignette typed, undo / redo, Off (the view exactly as
before); the game's camera path draws Studio's view the same; an AI proposes Moonlight against the current revision (the
person accepts; undo takes it back) and Golden hour against an old one that the person then changes too (a conflict,
nothing applied); Play; Save, reopen, export, and the exported game draws it."""

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
    return ((d.studio.project.scene().get("settings") or {}).get("hd2d") or {}).get("post")


def _parity(d: Any) -> dict[str, Any]:
    """The game's camera path (no camera passed) set to Studio's view against Studio's path, both drawn with the sun's
    shadow map fitted to the same game camera (#485) and play's cutaway off: the same picture."""
    import numpy as np  # noqa: PLC0415

    hd, view = d.renderer, d.studio.hd2d
    ctx = hd.ctx
    x, y, w, h = (int(v) for v in view.viewport())

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
    kept_cut = hd._bind_cutaway
    try:
        hd._bind_cutaway = lambda mp, cam: kept_cut(mp, None)
        game = at_origin(None)
        studio = at_origin(sc)
        stage = hd.last_stage
    finally:
        hd._bind_cutaway = kept_cut
        gc.target, gc.pitch, gc.fov, gc.distance, gc.ortho, gc.yaw, hd._camera_ready = saved
    return {"same": bool(np.array_equal(game, studio)), "stage": stage}


def _canvas_vs_origin(d: Any, canvas: Any) -> bool:
    """The graded canvas (offset in the window) against the same camera drawn at an offscreen target's origin: the
    grade and the vignette by the picture's own pixels, not the window's."""
    import numpy as np  # noqa: PLC0415

    hd, view = d.renderer, d.studio.hd2d
    ctx = hd.ctx
    _x, _y, w, h = (int(v) for v in view.viewport())
    tex = ctx.texture((w, h), components=4)
    fbo = ctx.framebuffer(color_attachments=[tex])
    try:
        fbo.use()
        raw = hd.draw(camera=view.camera, read_final=True)
    finally:
        d.window.use()
        fbo.delete()
        tex.delete()
    return bool(np.array_equal(np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)), canvas))


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
    original = (project / SCENES / "start.json").read_bytes()
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        d.advance(5)
        report["before"] = ops.post_of(d.studio.project.scene())
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
        d.advance(2)
        view = d.studio.hd2d
        view.advance_motion = view.advance_weather = lambda dt: None
        d.advance(2)
        plain = _canvas(d)
        report["still"] = bool(np.array_equal(plain, _canvas(d)))
        lines_plain = _canvas(d, lines=True)
        _press(d, "Natural", _right)
        d.advance(2)
        graded = _canvas(d)
        report["natural"] = {"stored": _stored(d), "message": d.studio.message, "stage": d.renderer.last_stage,
                             "renderer_preset": getattr(d.renderer.settings.post, "preset", None),
                             "changed_share": round(float((np.abs(graded.astype(int) - plain.astype(int)).max(axis=2)
                                                           > 0).mean()), 4)}
        Image.fromarray(plain).save(pics / "studio_off.png")
        Image.fromarray(graded).save(pics / "studio_natural.png")
        # Studio's lines over the graded picture: drawn after it, at the same pixels as over the original
        calls: list[str] = []
        drawn_after = d.renderer._overlay_after
        def counted(*a: Any, **k: Any) -> None:
            calls.append(d.renderer.last_stage)
            drawn_after(*a, **k)

        d.renderer._overlay_after = counted
        try:
            lines_graded = _canvas(d, lines=True)
        finally:
            d.renderer._overlay_after = drawn_after
        mask_off = np.abs(lines_plain.astype(int) - plain.astype(int)).max(axis=2) > 0
        mask_on = np.abs(lines_graded.astype(int) - graded.astype(int)).max(axis=2) > 0
        union = mask_off | mask_on
        report["lines"] = {"after_calls": calls, "pixels": [int(mask_off.sum()), int(mask_on.sum())],
                           "same_share": round(float((mask_off & mask_on).sum() / max(1, union.sum())), 4)}
        Image.fromarray(lines_graded).save(pics / "studio_natural_lines.png")
        report["parity"] = _parity(d)
        report["canvas_equals_origin"] = _canvas_vs_origin(d, graded)
        d.type_into("post_strength", "0.5")
        d.type_into("post_vignette", "0.3")
        report["typed"] = _stored(d)
        _press(d, "Undo")
        report["undone"] = _stored(d)
        _press(d, "Redo")
        report["redone"] = _stored(d)
        report["redone_renderer"] = {"strength": d.renderer.settings.post.strength,
                                     "vignette": d.renderer.settings.post.vignette}
        report["op_parity"] = ops.set_hd2d_post(json.loads(original), preset="natural", strength=0.5,
                                                vignette=0.3)["settings"]["hd2d"]["post"] == _stored(d)
        _press(d, "Off", _right)
        d.advance(2)
        report["off"] = {"stored": _stored(d), "stage": d.renderer.last_stage,
                         "view_same_as_before": bool(np.array_equal(_canvas(d), plain))}
        # an AI proposes, the person accepts; undo takes it back
        ai = d.studio.ai
        room = d.studio.project.current
        proposal = ai.stage_proposal_payload({"changes": [{"op": "set_hd2d_post", "room": room, "preset": "moonlight"}],
                                              "base_revision": d.studio.project.revision})
        report["ai_staged"] = {"summary": getattr(proposal, "summary", proposal)}
        d.studio.accept_ai(proposal)  # (the person's Accept: applied, the room reloaded, one undo step)
        d.advance(3)
        report["ai_accepted"] = {"status": proposal.status, "stored": _stored(d),
                                 "renderer_preset": getattr(d.renderer.settings.post, "preset", None),
                                 "stage": (_canvas(d), d.renderer.last_stage)[1]}
        _press(d, "Undo")
        d.advance(2)
        report["ai_undone"] = {"stored": _stored(d), "renderer_post": d.renderer.settings.post}
        # an AI proposal against a revision the person then changes too: a conflict, nothing applied
        old = d.studio.project.revision
        stale = ai.stage_proposal_payload({"changes": [{"op": "set_hd2d_post", "room": room, "preset": "golden_hour"}],
                                           "base_revision": old})
        _press(d, "Camera and sun...", lambda w: w.rect.left < 230)  # (accepting showed the inspector)
        d.advance(2)
        _press(d, "Interior warm", _right)
        d.advance(2)
        d.studio.accept_ai(stale)
        report["ai_conflict"] = {"status": stale.status, "conflicts": len(getattr(stale, "conflicts", []) or []),
                                 "stored": _stored(d)}
        ai.reject_proposal(stale)
        if not any(t == "Natural" for t in d.labels()):
            _press(d, "Camera and sun...", lambda w: w.rect.left < 230)
            d.advance(2)
        _press(d, "Natural", _right)
        d.advance(2)
        # Play: the game draws it
        k = d.arcade.key
        d.key(k.F4)
        for _ in range(30):
            d.advance()
            time.sleep(1 / 60)
        r = d.window.hd2d_renderer
        report["in_play"] = {"mode": d.studio.mode, "preset": getattr(r.settings.post, "preset", None),
                             "stage": r.last_stage}
        d.picture(pics / "play_natural.png")
        d.key(k.F4)
        d.advance(5)
        _press(d, "Save")
        report["saved"] = d.studio.message
    finally:
        d.close()
    room_doc = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    report["in_the_saved_file"] = room_doc["settings"]["hd2d"].get("post")
    without = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    without["settings"]["hd2d"].pop("post", None)
    report["rest_of_the_room_unchanged"] = without == json.loads(original)
    d = StudioDriver(project)
    try:
        d.advance(5)
        report["reopened"] = {"post": ops.post_of(d.studio.project.scene()), "unsaved": sorted(d.studio.project.dirty),
                              "renderer_preset": getattr(d.renderer.settings.post, "preset", None)}
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
    print(json.dumps({{"engine_from": engine.__file__, "preset": getattr(r.settings.post, "preset", None),
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
            "scene_setting": ((exported.get("settings") or {}).get("hd2d") or {}).get("post")}


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = studio(out, export="--no-export" not in sys.argv)
    (out / "post_studio.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1, default=str)[:8000])


if __name__ == "__main__":
    main()
