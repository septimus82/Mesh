"""#460 Phase B: the HD-2D depth of field measured in real rooms, in a hidden game window (nothing on screen).

    python tooling/dof_study.py PROJECT OUT [--set template|lakeside] [--size WxH] [--frames N] [--baseline-only]

PROJECT is a scratch copy of a game (the HD-2D template, or a copy of a Lakeside project): the study writes Subtle
depth of field into its outdoor room's file to test room changes, so never point it at a real project. It writes
OUT/report.json and pictures (off / Subtle per view). ``--baseline-only``: just the pictures with depth of field off
(run it on an older Mesh to show the off picture is unchanged).

What it records, per view: the pass's GPU time and the blit it replaces (timer queries), the frame's wall time; the
followed character's own pixels, off and on (its readability); the share of the sharp band changed; same screen row,
different depth (detail kept in a sharp and a blurred patch); and once: off and strength 0 identical to the original
blit, the software-rendering bypass identical to off, the HUD's text, walking toward and away from the camera, room
changes (outdoor on, indoor off), resizes, and GPU objects (none made per frame).
"""

from __future__ import annotations

import dataclasses
import json
import os
import statistics
import sys
import time
import warnings
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("MESH_STUDY_REPO") or Path(__file__).resolve().parents[1])  # (an older Mesh: --baseline-only)
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "tooling") not in sys.path:
    sys.path.insert(0, str(REPO / "tooling"))

SCENES = "packs/core_regions/scenes"
VIEWS: dict[str, list[tuple[str, str, tuple[float, float] | None]]] = {  # (name, scene, where the player stands)
    "template": [("village_start", f"{SCENES}/start.json", None),
                 ("village_shop", f"{SCENES}/start.json", (896.0, 290.0)),
                 ("village_bridge", f"{SCENES}/start.json", (640.0, 660.0)),
                 ("cottage_interior", f"{SCENES}/cottage.json", None)],
    "lakeside": [("lakeside_start", f"{SCENES}/lakeside.json", None),
                 ("lakeside_shop", f"{SCENES}/lakeside.json", (1168.0, 456.0)),
                 ("lakeside_bridge", f"{SCENES}/lakeside.json", (1040.0, 900.0)),
                 ("cottage_interior", f"{SCENES}/cottage.json", None)],
}
PATCH = 4  # px: half the side of a patch whose detail is compared


def _counts(ctx: Any) -> dict[str, int]:
    ctx.gc()
    return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1]
            for k in ("texture", "framebuffer", "program", "buffer", "geometry")}


def _detail(img: Any, y: int, x: int) -> float:
    import numpy as np  # noqa: PLC0415

    p = img[y - PATCH:y + PATCH, x - PATCH:x + PATCH].astype(np.float64).mean(axis=2)
    return float((np.abs(np.diff(p, axis=0)).mean() + np.abs(np.diff(p, axis=1)).mean()) / 2)


class Study:
    """One hidden game window and the measurements made in it."""

    def __init__(self, project: Path, out: Path, size: tuple[int, int], *, allow_software: bool = False) -> None:
        """``allow_software``: draw the pass even on a software rasteriser (a test of the pass itself, small)."""
        from hd2d_demo import HiddenGame  # noqa: PLC0415

        self.out, self.size, self.allow_software = out, size, allow_software
        self.game = HiddenGame(project, size=size)
        self.window = self.game.window
        self.window.audio.set_muted(True)  # (never plays aloud)
        self.ctx = self.window.ctx
        self._query = self.ctx.query(samples=False, time=True, primitives=False)
        self.draw_ns: list[int] = []
        self._timing = False

    @property
    def hd(self) -> Any:
        hd = getattr(self.window, "hd2d_renderer", None)  # (none before a room is loaded, or in a 2D room)
        if hd is not None and self.allow_software:
            hd.dof_allow_software = True
        return hd

    def set_dof(self, dof: Any) -> None:
        """This room's depth of field, as an edit in Mesh Studio sets it (the renderer's settings in place)."""
        self.hd.settings = dataclasses.replace(self.hd.settings, depth_of_field=dof)

    def frame(self) -> Any:
        import numpy as np  # noqa: PLC0415

        return np.asarray(self.game.draw().convert("RGB")).copy()

    def _timed_draw(self) -> None:
        """Time the renderer's whole draw on the GPU (the world, then the blit or the depth of field in its place):
        this window's renderer only, wrapped."""
        hd = self.hd
        if getattr(hd, "_dof_study", False):
            return
        original = hd.draw
        study = self

        def draw(*args: Any, **kwargs: Any) -> Any:
            if not study._timing or kwargs.get("solid") is not None:
                return original(*args, **kwargs)
            with study._query:
                result = original(*args, **kwargs)
            study.draw_ns.append(study._query.time_elapsed)
            return result

        hd.draw = draw
        hd._dof_study = True

    def alone_ns(self) -> int | None:
        """The pass's GPU time on its own: the last frame's composite drawn again over it, the GPU idle first (its
        inputs already resolved: a lower bound; the paired whole-draw difference is the cost in the frame)."""
        hd, ctx = self.hd, self.ctx
        if hd.last_dof is None:
            return None
        ctx.finish()
        with self._query:
            type(hd)._composite_dof(hd, hd.last_dof, hd.camera, None)
        return int(self._query.time_elapsed)

    def timed(self, dof: Any, frames: int) -> dict[str, Any]:
        """Off and on in alternate frames (so GPU clock changes fall on both): the renderer's whole draw's GPU time
        each way, and their paired difference (the depth of field's cost in the frame, all included); each frame's
        wall time (update + draw + GPU finished); and the pass alone (a lower bound)."""
        self._timed_draw()
        draws: dict[str, list[float]] = {"off": [], "on": []}
        walls: dict[str, list[float]] = {"off": [], "on": []}
        alone: list[float] = []
        self._timing = True
        try:
            for _ in range(frames):
                self.game.step(1)
                for label, setting in (("off", None), ("on", dof)):
                    self.set_dof(setting)
                    self.draw_ns = []
                    self.ctx.finish()
                    start = time.perf_counter()
                    self.window.dispatch_event("on_draw")
                    self.ctx.finish()
                    walls[label].append((time.perf_counter() - start) * 1000)
                    draws[label].append(float(self.draw_ns[-1]) if self.draw_ns else float("nan"))
                one = self.alone_ns()
                if one is not None:
                    alone.append(float(one))
        finally:
            self._timing = False

        def ms(xs: list[float], q: float) -> float | None:
            xs = sorted(x for x in xs if x == x)
            if not xs:
                return None
            return round(xs[min(len(xs) - 1, int(q * len(xs)))] / 1e6, 4)
        diff = [b - a for a, b in zip(draws["off"], draws["on"])]
        wall_diff = [(b - a) * 1e6 for a, b in zip(walls["off"], walls["on"])]
        return {"frames": frames,
                "draw_gpu_ms_off": {"median": ms(draws["off"], 0.5), "p95": ms(draws["off"], 0.95)},
                "draw_gpu_ms_on": {"median": ms(draws["on"], 0.5), "p95": ms(draws["on"], 0.95)},
                "incremental_gpu_ms": {"median": ms(diff, 0.5), "p95": ms(diff, 0.95), "max": ms(diff, 1.0)},
                "frame_wall_ms": {"off": round(statistics.median(walls["off"]), 3),
                                  "on": round(statistics.median(walls["on"]), 3),
                                  "paired_difference_median": ms(wall_diff, 0.5)},
                "pass_alone_gpu_ms": {"median": ms(alone, 0.5), "p95": ms(alone, 0.95)}}

    def depth_m(self) -> Any:
        """The world's last depth buffer as metres along the view axis, top row first (as pictures)."""
        import numpy as np  # noqa: PLC0415
        from pyglet import gl as raw  # noqa: PLC0415

        from engine.hd2d.dof import FAR, NEAR  # noqa: PLC0415

        hd = self.hd
        fw, fh = (int(v) for v in hd._fbo.size)
        buf = (raw.GLfloat * (fw * fh))()
        previous = self.ctx.active_framebuffer
        raw.glBindFramebuffer(raw.GL_READ_FRAMEBUFFER, hd._fbo.glo)
        raw.glReadPixels(0, 0, fw, fh, raw.GL_DEPTH_COMPONENT, raw.GL_FLOAT, buf)
        previous.use(force=True)
        d = np.flipud(np.ctypeslib.as_array(buf).reshape(fh, fw).astype(np.float64))
        if hd.camera.ortho:
            return NEAR + d * (FAR - NEAR)
        return NEAR * FAR / (FAR - d * (FAR - NEAR))

    def player_mask(self) -> Any:
        """The followed character's own visible pixels (the renderer's flat-red draw against the world's depth)."""
        import numpy as np  # noqa: PLC0415

        hd = self.hd
        raw = hd.draw(solid=self.game.player(), read=True)
        fw, fh = (int(v) for v in hd._fbo.size)
        solid = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(fh, fw, 3))
        return (solid[..., 0] > 200) & (solid[..., 1] < 60) & (solid[..., 2] < 60)

    def view(self, name: str, scene: str, place: tuple[float, float] | None, frames: int, subtle: Any) -> dict[str, Any]:
        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        from engine.hd2d.dof import coc  # noqa: PLC0415

        game = self.game
        game.load(scene)
        game.step(5)
        if place is not None:
            p = game.player()
            p.center_x, p.center_y = place
        game.step(90)  # past the fade-in; the camera settles on the player
        self.set_dof(None)
        off = self.frame()
        self.set_dof(subtle)
        on = self.frame()
        state = dict(self.hd.last_dof or {})
        Image.fromarray(off).save(self.out / f"{name}_off.png")
        Image.fromarray(on).save(self.out / f"{name}_subtle.png")
        cam = self.hd.camera
        facts: dict[str, Any] = {"scene": scene, "camera": {"pitch": cam.pitch, "fov": cam.fov, "distance": cam.distance,
                                                            "ortho": cam.ortho},
                                 "status": list(self.hd.dof_status())}
        facts["focus"] = {k: round(float(v), 4) for k, v in state.items() if k in ("focus", "band", "radius", "taps")}
        z = self.depth_m()
        sky = z > 400
        facts["depth_span_m"] = ([round(float(z[~sky].min()), 2), round(float(z[~sky].max()), 2)]
                                 if (~sky).any() else None)
        mask = self.player_mask()
        diff = np.abs(on.astype(int) - off.astype(int)).max(axis=2)
        facts["player"] = {"pixels": int(mask.sum()),
                           "depth_m": ([round(float(np.percentile(z[mask], q)), 3) for q in (2, 50, 98)]
                                       if mask.any() else None),
                           "changed_share": round(float((diff[mask] > 2).mean()), 4) if mask.any() else None,
                           "max_delta": int(diff[mask].max()) if mask.any() else None}
        if not state:
            facts["note"] = "depth of field not drawn"
            return facts
        radius, band, focus = state["radius"], state["band"], state["focus"]
        cocs = np.vectorize(lambda d: coc(d, focus, band, subtle.near_falloff, subtle.far_falloff, radius))(z)
        sharp_px, far_px = cocs == 0.0, cocs >= min(1.0, radius)  # far: blurred at least a pixel
        facts["sharp_band"] = {"pixels": int(sharp_px.sum()),
                               "changed_share": round(float((diff[sharp_px] > 2).mean()), 4) if sharp_px.any() else None}
        facts["blurred_share"] = round(float((np.abs(cocs) >= 0.5).mean()), 4)
        facts["same_row"] = self._same_row(off, on, sharp_px, far_px, cocs)
        facts["timing"] = self.timed(subtle, frames)
        return facts

    def _same_row(self, off: Any, on: Any, sharp_px: Any, far_px: Any, cocs: Any) -> dict[str, Any]:
        """Same screen row, different depth: a patch in the sharp band and one farther, blurred by at least a pixel,
        both with detail when off; how much detail each keeps with depth of field on."""
        h, w = sharp_px.shape
        found = []
        for y in range(PATCH + 2, h - PATCH - 2, 6):
            def ok(mask: Any, x: int) -> bool:
                return bool(mask[y - PATCH:y + PATCH, x - PATCH:x + PATCH].all()) and _detail(off, y, x) >= 6.0
            xs_sharp = [x for x in range(PATCH + 2, w - PATCH - 2, 4) if ok(sharp_px, x)]
            xs_far = [x for x in range(PATCH + 2, w - PATCH - 2, 4) if ok(far_px, x)]
            if xs_sharp and xs_far:
                a = max(xs_sharp, key=lambda x: _detail(off, y, x))
                b = max(xs_far, key=lambda x: _detail(off, y, x))
                found.append({"row": y, "sharp_col": a, "far_col": b, "far_coc_px": round(float(cocs[y, b]), 2),
                              "sharp_kept": round(_detail(on, y, a) / _detail(off, y, a), 3),
                              "far_kept": round(_detail(on, y, b) / _detail(off, y, b), 3)})
        return {"rows": len(found), "examples": sorted(found, key=lambda f: f["far_kept"])[:4]}

    def close(self) -> None:
        self.game.close()


def _write_room_dof(project: Path, scene: str, dof: dict[str, Any] | None) -> None:
    """Set (or remove) a room's depth of field in its file (the scratch copy only)."""
    path = project / scene
    doc = json.loads(path.read_text(encoding="utf-8"))
    hd2d = doc["settings"]["hd2d"]
    if dof is None:
        hd2d.pop("depth_of_field", None)
    else:
        hd2d["depth_of_field"] = dof
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def run(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """The study (see `_run`). The game's interact prompt (engine/ui_overlays/hud.py, not this study's code) draws
    with arcade's slow draw_text, which warns every frame the player stands by an NPC, and pytest's -W error would end
    the run on it: only that one message is set aside, only while the study runs."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="draw_text is an extremely slow function")
        return _run(*args, **kwargs)


def _run(project: Path, out: Path, *, which: str = "template", size: tuple[int, int] = (1280, 720), frames: int = 120,
         baseline_only: bool = False, walk: int = 30, loops: int = 120, dof: Any = None,
         allow_software: bool = False, resizes: tuple[tuple[int, int], ...] = ((960, 540), (1920, 1080))) -> dict[str, Any]:
    """The whole study (see the module). ``dof``: the depth of field measured (Subtle when None)."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"size": list(size), "set": which, "views": {}}
    study = Study(project, out, size, allow_software=allow_software)
    ctx = study.ctx
    report["gl"] = {"vendor": ctx.info.VENDOR, "renderer": ctx.info.RENDERER, "version": list(ctx.gl_version)}
    try:
        if baseline_only:
            for name, scene, place in VIEWS[which]:
                study.game.load(scene)
                study.game.step(5)
                if place is not None:
                    p = study.game.player()
                    p.center_x, p.center_y = place
                study.game.step(90)
                Image.fromarray(study.frame()).save(out / f"{name}_baseline.png")
            return report
        from engine.hd2d.dof import SUBTLE as PRESET  # noqa: PLC0415
        from engine.hd2d.dof import dof_unavailable_reason, parse_dof  # noqa: PLC0415

        SUBTLE = dof if dof is not None else PRESET  # noqa: N806  # (the depth of field this run measures)
        report["measured"] = dataclasses.asdict(SUBTLE)

        report["software_renderer"] = dof_unavailable_reason(ctx)
        for name, scene, place in VIEWS[which]:
            report["views"][name] = study.view(name, scene, place, frames, SUBTLE)
            (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
        outdoor = VIEWS[which][0][1]
        game, hd = study.game, None
        game.load(outdoor)
        game.step(90)
        hd = study.hd
        checks: dict[str, Any] = {}
        # off, and strength 0: the original blit, pixel for pixel; and nothing drawn (no program made)
        study.set_dof(None)
        off = study.frame()
        study.set_dof(parse_dof({"strength": 0.0}))
        zero = study.frame()
        checks["zero_strength_drawn"] = hd.last_dof is not None  # (the original blit ran, not the pass)
        study.set_dof(parse_dof({"enabled": False}))
        disabled = study.frame()
        checks["zero_strength_identical_to_off"] = bool(np.array_equal(off, zero))
        checks["disabled_identical_to_off"] = bool(np.array_equal(off, disabled))
        # software rendering: bypassed, said why, the picture exactly off (real on a software rasteriser)
        kept = hd.dof_unavailable
        study.set_dof(SUBTLE)
        hd.dof_allow_software = False
        hd.dof_unavailable = hd.dof_unavailable or "depth of field is off on this computer (simulated software rendering)"
        bypassed = study.frame()
        checks["software_bypass"] = {"status": list(hd.dof_status()), "identical_to_off": bool(np.array_equal(off, bypassed)),
                                     "drawn": hd.last_dof is not None, "real": kept is not None,
                                     "room_message": getattr(study.window, "hd2d_dof_message", None)}
        hd.dof_unavailable = kept
        hd.dof_allow_software = allow_software
        # the HUD is drawn after the world: its text unchanged by the blur
        hud = study.window.player_hud
        hud.enqueue_toast("Depth of field: the HUD stays sharp")
        game.step(2)
        study.set_dof(None)
        toast_off = study.frame()
        study.set_dof(SUBTLE)
        toast_on = study.frame()
        hud.clear_toasts()
        study.set_dof(None)
        without = study.frame()
        glyphs = (np.abs(toast_off.astype(int) - without).max(axis=2) > 120) & (toast_off.min(axis=2) > 225)
        delta = np.abs(toast_on.astype(int) - toast_off).max(axis=2)
        checks["hud"] = {"glyph_pixels": int(glyphs.sum()), "glyph_pixels_changed": int((delta[glyphs] > 0).sum()),
                         "glyph_max_delta": int(delta[glyphs].max()) if glyphs.any() else None}
        Image.fromarray(toast_on).save(out / "hud_toast_subtle.png")
        # walking toward and away from the camera: the character stays sharp, the picture steady
        keys = study.game.arcade.key
        walked: dict[str, Any] = {}
        for label, key in (("away", keys.UP), ("toward", keys.DOWN)):
            changed, focus, frames_off, frames_on = [], [], [], []
            study.window.dispatch_event("on_key_press", key, 0)
            for _ in range(walk):
                game.step(1)
                study.set_dof(None)
                a = study.frame()
                study.set_dof(SUBTLE)
                b = study.frame()
                focus.append(round(float((hd.last_dof or {}).get("focus", 0.0)), 3))
                mask = study.player_mask()
                d = np.abs(b.astype(int) - a.astype(int)).max(axis=2)
                changed.append(round(float((d[mask] > 2).mean()), 4) if mask.any() else None)
                frames_off.append(a.astype(np.int16))
                frames_on.append(b.astype(np.int16))
            study.window.dispatch_event("on_key_release", key, 0)
            game.step(2)
            step = {k: float(np.mean([np.abs(y - x).mean() for x, y in zip(v, v[1:])]))
                    for k, v in (("off", frames_off), ("on", frames_on))}
            walked[label] = {"player_changed_share_max": max((c for c in changed if c is not None), default=None),
                             "focus_m_first_last": [focus[0], focus[-1]],
                             "frame_to_frame_change": {k: round(v, 3) for k, v in step.items()},
                             "on_over_off": round(step["on"] / max(1e-9, step["off"]), 3)}
        checks["walking"] = walked
        still = [study.frame() for _ in range(3)]
        checks["still_frames_identical"] = bool(all(np.array_equal(still[0], s) for s in still[1:]))
        # GPU objects: none per frame (off control first), none across room changes and resizes
        study.set_dof(None)
        before_off = _counts(ctx)
        for _ in range(loops):
            game.step(1)
            study.frame()
        after_off = _counts(ctx)
        study.set_dof(SUBTLE)
        study.frame()
        before = _counts(ctx)
        for _ in range(loops):
            game.step(1)
            study.frame()
        after = _counts(ctx)
        checks["gl_objects"] = {"off_before": before_off, "off_after": after_off, "on_before": before, "on_after": after}
        # room changes: the outdoor room on (written into its file), the interior off, and back
        _write_room_dof(project, outdoor, {})
        rooms = []
        indoor = VIEWS[which][-1][1]
        for scene in (outdoor, indoor, outdoor, indoor, outdoor):
            game.load(scene)
            game.step(40)
            said = getattr(study.window, "hd2d_dof_message", None)  # (what the room's load said, as Studio shows it)
            _ = study.hd  # (the new room's renderer: the test's software allowance)
            study.frame()
            rooms.append({"scene": scene, "status": list(study.hd.dof_status()), "load_message": said,
                          "drawn": study.hd.last_dof is not None, "objects": _counts(ctx)})
        _write_room_dof(project, outdoor, None)
        checks["room_changes"] = rooms
        # resizes: the blur keeps its look (radius scales with the picture's height); nothing left behind
        sizes = {}
        hd = study.hd
        study.set_dof(SUBTLE)
        for w, h in (*resizes, size):
            study.window.set_size(w, h)
            game.step(2)
            img = study.frame()
            sizes[f"{w}x{h}"] = {"frame": list(img.shape[:2][::-1]), "fbo": list(hd._fbo.size),
                                 "radius_px": round(float((hd.last_dof or {}).get("radius", 0.0)), 3),
                                 "taps": (hd.last_dof or {}).get("taps"), "objects": _counts(ctx)}
        checks["resizes"] = sizes
        # orthographic camera: drawn without error (its look is NOT measured: untested)
        hd.camera.ortho = True
        img = study.frame()
        checks["ortho_drawn"] = {"status": list(hd.dof_status()), "drawn": hd.last_dof is not None,
                                 "non_black": bool(img.max() > 0)}
        Image.fromarray(img).save(out / "ortho_subtle_untested.png")
        hd.camera.ortho = False
        report["checks"] = checks
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
        study.close()
    return report


def main(argv: list[str]) -> int:
    project, out = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    rest = argv[2:]

    def opt(name: str, default: str) -> str:
        return rest[rest.index(name) + 1] if name in rest else default
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
        if name not in os.environ or "--scratch-env" in rest:
            os.environ[name] = str(out / "env" / name.lower())
            Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
    size = (int(opt("--size", "1280x720").split("x")[0]), int(opt("--size", "1280x720").split("x")[1]))
    report = run(project, out, which=opt("--set", "template"), size=size, frames=int(opt("--frames", "120")),
                 baseline_only="--baseline-only" in rest)
    print(json.dumps({k: v for k, v in report.items() if k != "views"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
