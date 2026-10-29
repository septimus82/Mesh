"""Milestone 23C evidence: weather particles authored in Mesh Studio (hidden windows; Studio's own events; silent).

    py -3.13 tooling/m23c_weather_studio.py creator OUT   # rain, snow, windborne leaves in Studio: preview, hide one,
                                                          # save, reopen, undo/redo, Play, another room, indoors
    py -3.13 tooling/m23c_weather_studio.py export OUT    # the creator's project exported, run on its own engine
    py -3.13 tooling/m23c_weather_studio.py perf OUT      # each effect at each strength: its GPU pass, draw calls
    py -3.13 tooling/m23c_weather_studio.py compat OUT    # an older room's own particle settings reopened and kept

The project is disposable (made in OUT): Milestone 23B's woodland clearing (tooling/m23b_fire_study.py: the Hills
room, a cottage, trees, a bridge) without weather and without its campfire, plus the template's village. Every
weather setting is made in Studio with its own controls; nothing writes the room's weather by hand. Master volume 0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import engine.optional_arcade  # noqa: E402,F401,I001  # (first: DPI-unaware before anything loads pyglet)
import m23b_fire_study as clearing  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402

PX = 32.0
ROOM = clearing.ROOM
VIEW = (8.5, 4.5)  # m: the cottage's front, a tree and the path (what the evidence pictures look at)
SAVED = "weather.json"  # (the creator phase's weather as Studio saved it: for the export phase)


def _ops() -> Any:
    from engine import project_ops as ops

    return ops


def _state(scene: dict[str, Any]) -> dict[str, Any]:
    """The room's weather as stored and as Studio describes it."""
    ops = _ops()
    settings = scene.get("settings") or {}
    return {"particles": settings.get("particles"), "wind": settings.get("wind"),
            "exposure": settings.get("weather_exposure", "outdoor"), "sounds": ops.weather_sounds_of(scene),
            "described": [(s["preset"], s["strength"] if s["present"] else "none", s["enabled"])
                          for s in ops.weather_of(scene)]}


def _runtime(window: Any) -> dict[str, Any]:
    """The weather the renderer has now: each effect (preset, count, shown) and its wind, its draws last frame."""
    hd = getattr(window, "hd2d_renderer", None)
    layer = hd.particles if hd is not None else None
    if layer is None:
        return {"effects": [], "draw_calls": 0}
    return {"effects": [(e.preset, e.count, on, [round(v, 3) for v in e.wind], round(e.gust, 3))
                        for e, on in zip(layer.effects, layer.enabled)],
            "draw_calls": layer.draw_calls, "time": round(layer.time, 3),
            "notice": getattr(window, "scene_particles_notice", None)}


def _tip(d: Any, tip: str) -> None:
    """Click the 3D view's button whose tooltip is ``tip`` (the weather panel's None/Light/Steady/Heavy repeat in each
    row: their tooltips name the kind), scrolling it into view first as a person would."""
    def find() -> Any:
        return next((w for w, t in d.studio.hd2d.tips if t == tip), None)

    if not d._scroll_panels(find):
        raise AssertionError(f"no button with the tip {tip!r}")
    d.frame()
    r = find().rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)
    d.frame(2)


def _strength(d: Any, kind: str, key: str) -> None:
    ops = _ops()
    name = ops.WEATHER_KINDS[kind]
    if key == "none":
        _tip(d, f"{name}: none")
    else:
        unit = d.studio.hd2d.WEATHER_UNITS[kind]
        _tip(d, f"{name}: {key} ({ops.WEATHER_STRENGTHS[kind][key]:,} {unit})")


def _probe(d: Any, at: tuple[float, float]) -> dict[str, Any]:
    """Every particle of the room's weather about ``at`` (m), in world space (tooling/m18b_weather_study.py): how many
    are falling and how many have landed, and those landed, how far off the ground under them (m)."""
    import m18b_weather_study as m18b
    import numpy as np

    hd = d.window.hd2d_renderer
    hd.camera.target = (at[0], at[1], 0.8)
    sample = m18b.probe(d.game)
    landed = sample["landed"]
    off = [abs(float(z) - hd.ground_height(float(x) * PX, float(y) * PX) / PX) for x, y, z in landed[:400]]
    on_ground = int(sum(1 for v in off if v < 0.15))
    return {"falling": int(len(sample["falling"])), "landed": int(len(landed)),
            "landed_within_15cm_of_the_ground": on_ground, "landed_sampled": len(off),
            "ids": sample["falling_ids"], "positions": sample["falling"],
            "_np": np}


def _drift(d: Any, at: tuple[float, float], seconds: float = 0.5) -> dict[str, Any]:
    """The leaves' movement in the preview: the same particles probed ``seconds`` apart (the preview's clock run by
    Studio's own frames); their median displacement (m/s, east, north)."""
    a = _probe(d, at)
    d.frame(round(seconds * 60))
    b = _probe(d, at)
    np = a["_np"]
    common, ia, ib = np.intersect1d(a["ids"], b["ids"], return_indices=True)
    if not len(common):
        return {"matched": 0}
    moved = (b["positions"][ib] - a["positions"][ia]) / seconds
    moved = moved[np.linalg.norm(moved[:, :2], axis=1) < 20.0]  # (not those wrapped round the box meanwhile)
    return {"matched": int(len(moved)), "median_m_s": [round(float(v), 2) for v in np.median(moved[:, :2], axis=0)]}


def _picture(d: Any, path: Path) -> None:
    """A picture with the mouse resting over the view (no button's tooltip showing)."""
    d.window.dispatch_event("on_mouse_motion", d.window.width // 3, d.window.height // 2, 0, 0)
    d.frame(2)
    d.picture(path)


def _open_room(d: Any) -> None:
    import m20c_material_study as m20c

    key = next(k for k, _l, path in d.studio.project.rooms() if path.endswith("hills.json"))
    if d.studio.project.current != key:
        d.button(d.studio.project.label(key))
        d.frame(3)
    m20c._look_at(d, VIEW[0], VIEW[1], 20.0)


def make_project(out: Path) -> Path:
    """The clearing: the Hills room, a cottage, trees, a bridge; no weather, no campfire, no wind; master volume 0."""
    project: Path = clearing.make_project(out, "weather", fires=[])
    path = project / ROOM
    scene = json.loads(path.read_text(encoding="utf-8"))
    for key in ("particles", "wind"):
        (scene.get("settings") or {}).pop(key, None)  # (setup: the room starts with none, as a new one does)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


# ---------------------------------------------------------------------- phases
def creator(out: Path) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    out.mkdir(parents=True, exist_ok=True)
    project = make_project(out)
    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    report: dict[str, Any] = {}
    k = None
    d = StudioDriver(project)
    try:
        k = d.arcade.key
        _open_room(d)
        report["before"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window),
                            "left_environment_has_button": None}
        d.studio.set_left_tab("environment")
        d.frame()
        report["before"]["left_environment_has_button"] = d.has_button("Weather particles...")
        d.button("Weather particles...")
        report["panel_open"] = d.studio.panel
        _picture(d, pics / "c01_panel_no_weather.png")

        # 2. rain, previewed
        _strength(d, "rain", "steady")
        d.frame(40)
        report["rain"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window),
                          "probe": {k2: v for k2, v in _probe(d, VIEW).items() if not k2.startswith(("_", "ids", "pos"))}}
        _picture(d, pics / "c02_rain_day.png")

        # 3. snow instead: flakes falling and settled on the ground
        _strength(d, "rain", "none")
        _strength(d, "snow", "heavy")
        d.frame(120)
        report["snow"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window),
                          "probe": {k2: v for k2, v in _probe(d, VIEW).items() if not k2.startswith(("_", "ids", "pos"))}}
        _picture(d, pics / "c03_snow_day.png")

        # 4-5. windborne leaves, a gusty breeze toward the north: the leaves move with it
        _strength(d, "wind", "heavy")
        d.button("Gusty")
        d.button("To North")
        d.frame(30)
        report["leaves"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window)}
        _picture(d, pics / "c04_snow_and_leaves_gusty_day.png")

        # 6. snow hidden, the leaves kept
        d.button("Snow shown: On")
        d.frame(30)
        report["snow_hidden"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window),
                                 "leaves_drift": _drift(d, VIEW)}
        _picture(d, pics / "c05_leaves_only_day.png")

        # night (Camera and sun...: Night), snow shown again
        d.button("Snow shown: Off")
        d.button("Camera and sun...")
        d.button("Night")
        d.button("Weather particles...")
        d.frame(60)
        _picture(d, pics / "c06_snow_and_leaves_night.png")
        import m20c_material_study as m20c

        m20c._look_at(d, 5.0, 6.0, 26.0)  # (the whole cottage: snow in front of it drawn, behind it hidden by it)
        d.frame(30)
        _picture(d, pics / "c07_snow_by_the_cottage_night.png")
        m20c._look_at(d, VIEW[0], VIEW[1], 20.0)

        # 8. undo and redo a weather change
        before_undo = _state(d.studio.project.scene())["described"]
        _strength(d, "snow", "light")
        changed = _state(d.studio.project.scene())["described"]
        d.key(k.Z, k.MOD_CTRL)
        undone = _state(d.studio.project.scene())["described"]
        d.key(k.Y, k.MOD_CTRL)
        redone = _state(d.studio.project.scene())["described"]
        report["undo_redo"] = {"before": before_undo, "changed": changed, "undone": undone, "redone": redone,
                               "runtime_after_redo": _runtime(d.window)}

        # indoors: no rain or snow (the leaves stay); then outdoors again
        d.button("Outdoors (rain and snow fall): On")
        d.frame(5)
        report["indoors"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window),
                             "message": d.studio.message}
        d.button("Outdoors (rain and snow fall): Off")
        d.frame(5)

        # 7. save
        d.key(k.S, k.MOD_CTRL)
        report["saved_message"] = d.studio.message
        report["configured"] = _state(d.studio.project.scene())
        report["configured_runtime"] = _runtime(d.window)
    finally:
        d.close()
    saved = json.loads((project / ROOM).read_text(encoding="utf-8"))
    report["in_the_saved_file"] = _state(saved)
    (out / SAVED).write_text(json.dumps(report["in_the_saved_file"], indent=1) + "\n", encoding="utf-8")

    d = StudioDriver(project)
    try:
        k = d.arcade.key
        _open_room(d)
        d.frame(20)
        report["reopened"] = {"state": _state(d.studio.project.scene()), "runtime": _runtime(d.window),
                              "unsaved": sorted(d.studio.project.dirty)}
        _picture(d, pics / "c08_reopened_night.png")
        # 9. Play, Stop, editing again
        cycles = []
        for n in range(2):
            d.key(k.F4)
            d.frame(40)
            cycles.append({"mode": d.studio.mode, "runtime": _runtime(d.window),
                           "master_volume": d.window.audio.master_volume})
            if n == 0:
                _picture(d, pics / "c09_play_night.png")
            d.key(k.F4)
            d.frame(10)
            cycles[-1]["after_stop"] = {"mode": d.studio.mode, "runtime": _runtime(d.window)}
        report["play_stop"] = cycles
        # another room: no weather leaks into it; and back
        start = next(k2 for k2, _l, path in d.studio.project.rooms() if path.endswith("start.json"))
        d.button(d.studio.project.label(start))
        d.frame(10)
        report["other_room"] = {"room": d.studio.project.current, "runtime": _runtime(d.window),
                                "particles": (d.studio.project.scene().get("settings") or {}).get("particles")}
        _open_room(d)
        d.frame(10)
        report["back"] = _runtime(d.window)
    finally:
        d.close()
    return report


def export(out: Path) -> dict[str, Any]:
    """The creator phase's project (OUT, after ``creator``) exported with ``mesh export build``; the bundle run on its
    own engine in a hidden window: its weather as the bundle's renderer has it, and a picture."""
    project = out / "weather"
    bundle = out / "export_bundle"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    report: dict[str, Any] = {"export_code": built.returncode, "export_tail": (built.stdout + built.stderr)[-200:]}
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
import engine.optional_arcade
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from pathlib import Path
from PIL import Image
game = HiddenGame(Path({str(bundle)!r}), size=(1280, 720))
try:
    game.load({ROOM!r})
    game.step(90)
    hd = game.window.hd2d_renderer
    hd.camera.target = ({VIEW[0]}, {VIEW[1] - 0.8}, 0.8)
    hd._camera_ready = True
    Image.frombytes("RGB", (1280, 720), hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save({str(out / "export_frame.png")!r})
    layer = hd.particles
    row = {{"engine_in_bundle": str(Path(engine.__file__)).startswith({str(bundle)!r}),
            "effects": [(e.preset, e.count, on, [round(v, 3) for v in e.wind], round(e.gust, 3))
                        for e, on in zip(layer.effects, layer.enabled)] if layer else [],
            "draw_calls": layer.draw_calls if layer else 0, "time": round(layer.time, 3) if layer else 0,
            "master_volume": game.window.audio.master_volume, "error": getattr(game.window, "scene_particles_error", None)}}
finally:
    game.close()
print(json.dumps(row))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        report["bundle_run"] = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        report["bundle_run"] = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    saved = out / SAVED
    if saved.is_file():
        report["configured"] = json.loads(saved.read_text(encoding="utf-8"))
    return report


def perf(out: Path) -> dict[str, Any]:
    """Each kind at each strength, alone, in the clearing (gusty, by day; Studio's own counts): the particle pass's
    GPU time (a timer query round 20 draws), the frame's draw calls, and the frame's wall time with none."""
    import m20d_scatter_study as m20d

    ops = _ops()
    report: dict[str, Any] = {}
    for kind in ("none", *ops.WEATHER_STRENGTHS):
        for key in (("-",) if kind == "none" else ("light", "steady", "heavy")):
            name = f"{kind}_{key}" if kind != "none" else "none"
            project = make_project(out / name)
            path = project / ROOM
            scene = json.loads(path.read_text(encoding="utf-8"))
            scene = ops.set_wind(scene, speed=5.0, gust=0.9)
            if kind != "none":
                scene = ops.set_weather(scene, kind, strength=key)  # (the panel's operation)
            path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
            game = HiddenGame(project, size=(1280, 720))
            try:
                game.load(ROOM)
                game.step(30)
                hd = game.window.hd2d_renderer
                row: dict[str, Any] = {"wall_ms_best_of_3": round(min(statistics.median(m20d._frame(game, 90))
                                                                      for _ in range(3)), 2)}
                game.window.dispatch_event("on_draw")
                row["draw_calls"] = hd.draw_calls
                if hd.particles is not None:
                    found: dict[str, list[float]] = {}
                    original = clearing._gpu(game, hd.particles, "draw_3d", found)
                    try:
                        for _ in range(20):
                            game.window.dispatch_event("on_update", 1 / 60)
                            game.window.dispatch_event("on_draw")
                    finally:
                        hd.particles.draw_3d = original
                    row["particle_pass_gpu_ms"] = round(statistics.median(found["draw_3d"]), 4)
                    row["particles"] = sum(e.count for e in hd.particles.effects)
                report[name] = row
            finally:
                game.close()
            shutil.rmtree(out / name, ignore_errors=True)
    return report


def compat(out: Path) -> dict[str, Any]:
    """A room with weather set before Studio could author it (as an older project, or the AI, wrote it: custom
    speed, area, seed, opacity, a hidden effect, two of a kind): reopened in Studio unchanged (no migration), shown
    in the panel as it is, and a change there touching only what it changes."""
    from hd2d_studio_demo import StudioDriver

    out.mkdir(parents=True, exist_ok=True)
    project = make_project(out)
    path = project / ROOM
    scene = json.loads(path.read_text(encoding="utf-8"))
    older = [{"preset": "snow", "count": 1700, "speed": 1.5, "area": [40, 40, 12], "seed": 9, "opacity": 0.7},
             {"preset": "wind", "count": 120, "gust": 0.4, "wind": [2.0, 1.0], "lifetime": 8},
             {"preset": "rain", "count": 500, "enabled": False}, {"preset": "snow", "count": 300, "seed": 2}]
    scene.setdefault("settings", {})["particles"] = older  # (as an older project has it: not through Studio)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        _open_room(d)
        report["reopened_unchanged"] = d.studio.project.scene()["settings"]["particles"] == older
        report["unsaved_on_open"] = sorted(d.studio.project.dirty)
        report["runtime"] = _runtime(d.window)
        d.studio.set_left_tab("environment")
        d.frame()
        d.button("Weather particles...")
        report["panel_says"] = [t for t in d.labels() if t.startswith(("Rain:", "Snow:", "Windborne", "Kept as set",
                                                                       "Weather effects"))]
        _picture(d, out / "compat_panel.png")
        _strength(d, "snow", "heavy")
        after = d.studio.project.scene()["settings"]["particles"]
        report["after_snow_heavy"] = after
        report["only_snow_count_changed"] = after == [{**older[0], "count": 4500}, *older[1:]]
        _strength(d, "rain", "light")  # (the rain is there, hidden: its strength changes, still hidden)
        report["rain_light_kept_hidden"] = d.studio.project.scene()["settings"]["particles"][2]
    finally:
        d.close()
    return report


PHASES: dict[str, Callable[[Path], dict[str, Any]]] = {"creator": creator, "export": export, "perf": perf,
                                                     "compat": compat}


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("phase", choices=sorted(PHASES))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    print(json.dumps(PHASES[args.phase](args.out), indent=1, default=str))


if __name__ == "__main__":
    main()
