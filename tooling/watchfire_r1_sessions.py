"""Watchfire R1: does a new game start clean after an earlier session saved and loaded a game?

Two real processes, each starting the game the way a player does (the project's own ``main.py``: no test flags, so
the editor workspace and session restoration run exactly as they do for a player), in a hidden, silent window and
played with the game's own keys (the creator trial's player: arrows to walk, E to talk and choose):

    A  new game; accept the steward's task; light the watchfire; save; load that save; exit.
    B  start the game normally (A's saves, workspace.json and .mesh files present); check the new game: no
       task_accepted or watchfire_lit, the steward's opening is the fresh introduction, the watchfire is cold; then
       load A's save and check the progress is back.

    py -3.13 tooling/watchfire_r1_sessions.py OUT [--engine DIR] [--bundle DIR] [--fresh-only]

The project is a scratch copy of the creator trial's (never the trial itself); OUT gets ``report.json``.
``--bundle`` plays an exported build instead (its own engine copy, unless ``--engine``); ``--fresh-only`` runs B
alone, with no earlier session. A ``studio`` step reopens the project in Mesh Studio and the legacy editor
afterwards (the editor launch, as ``mesh edit`` does), recording which room each opens.

``flag_sessions(project)`` runs the same two sessions on any project, with the story's flags set as its dialogue
would set them (the CI check, tests/test_new_game_isolation_gpu.py, on Mesh's starter template).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TRIAL = Path("D:/Games/Mesh-Creator-Trial-Watchfire")
ENGINE = Path(__file__).resolve().parents[1]
KEEP_OUT = {"export_build", "trial_evidence", "trial_tools", "artifacts", "saves", ".mesh", "TRIAL_REPORT.md"}
STORY = ("task_accepted", "watchfire_lit", "quest_complete")
MARK = "R1|"


def _copy_project(source: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=lambda d, names: [n for n in names if Path(d) == source and n in KEEP_OUT]
                    + [n for n in names if n in (".mesh", "saves")])


def _copy_player(engine: Path, project: Path, dest: Path) -> None:
    """The trial's player (play.py) and its helpers (drive.py), pointed at this engine and this copy."""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TRIAL / "trial_tools" / "play.py", dest / "play.py")
    text = (TRIAL / "trial_tools" / "drive.py").read_text(encoding="utf-8")
    text = re.sub(r'^ENGINE = Path\(".*?"\)', lambda _m: f"ENGINE = Path({engine.as_posix()!r})", text, count=1, flags=re.M)
    text = re.sub(r'^PROJECT = Path\(".*?"\)', lambda _m: f"PROJECT = Path({project.as_posix()!r})", text, count=1, flags=re.M)
    (dest / "drive.py").write_text(text, encoding="utf-8")


def _run(role: str, engine: Path, tools: Path, project: Path) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_CURRENT_TEST", "PYTHONPATH", "MESH_REPO_ROOT")}
    env["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    ran = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--session", role, str(engine), str(tools)],
                         cwd=project, env=env, capture_output=True, text=True, timeout=900)
    found = [ln[len(MARK):] for ln in ran.stdout.splitlines() if ln.startswith(MARK)]
    if ran.returncode != 0 or not found:
        return {"error": f"exit {ran.returncode}", "stderr": ran.stderr[-3000:], "stdout": ran.stdout[-2000:]}
    return dict(json.loads(found[-1]))


def _files(project: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"saves": sorted(p.name for p in (project / "saves").glob("*.json"))
                           if (project / "saves").is_dir() else []}
    session = project / ".mesh" / "editor_session_state.json"
    out["session_last_scene_path"] = (json.loads(session.read_text(encoding="utf-8")).get("last_scene_path")
                                      if session.exists() else None)
    workspace = project / "workspace.json"
    out["workspace_last_scene_id"] = (json.loads(workspace.read_text(encoding="utf-8")).get("last_scene_id")
                                      if workspace.exists() else None)
    return out


# ---------------------------------------------------------------------- inside one session (cwd = the project)
def _session(role: str, engine: Path, tools: Path) -> None:
    sys.path.insert(0, str(engine))
    import engine.optional_arcade as optional_arcade  # noqa: PLC0415  # first: DPI-unaware, as the engine runs

    arcade = optional_arcade.arcade
    original_init = arcade.Window.__init__

    def hidden_init(window: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["visible"] = False  # never on the owner's screen
        original_init(window, *args, **kwargs)

    arcade.Window.__init__ = hidden_init
    from engine.game import GameWindow  # noqa: PLC0415

    loads: list[str] = []
    original_load = GameWindow.load_scene

    def recording_load(window: Any, path: Any, *args: Any, **kwargs: Any) -> Any:
        loads.append(str(path).replace("\\", "/"))
        return original_load(window, path, *args, **kwargs)

    setattr(GameWindow, "load_scene", recording_load)  # noqa: B010
    report: dict[str, Any] = {"role": role, "scene_loads": loads}

    def scenario(window: Any) -> None:  # in place of the event loop: the player plays, then closes the window
        window._allow_dispatch_event = True
        window.audio.set_muted(True)
        try:
            if role.startswith("flags-"):
                _flags(role, window, report)
            elif role == "studio":
                studio = getattr(window, "studio", None)
                report["studio_room"] = getattr(getattr(studio, "project", None), "current", None)
                report["window_scene"] = str(window.scene_controller.current_scene_path or "")
                camera = getattr(window, "camera", None)
                report["camera"] = [round(float(v), 1) for v in getattr(camera, "position", ())]
            else:
                _play(role, window, arcade, tools, report)
        except (AssertionError, AttributeError, KeyError, RuntimeError, StopIteration, TypeError, ValueError) as exc:
            # (a failed play: the report carries it to the parent process)
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            report["scene_loads"] = list(loads)
            print(MARK + json.dumps(report, default=str), flush=True)
            window.dispatch_event("on_close")  # the player closes the window

    setattr(GameWindow, "run", scenario)  # noqa: B010
    if role == "studio":
        from engine.game_launch import launch_editor  # noqa: PLC0415

        launch_editor(project_root=Path.cwd())
    else:
        import runpy  # noqa: PLC0415

        runpy.run_path("main.py", run_name="__main__")


def _play(role: str, window: Any, arcade: Any, tools: Path, report: dict[str, Any]) -> None:
    sys.path.insert(0, str(tools))
    sys.path.append(str(ENGINE / "tooling"))  # (play.py imports hd2d_demo; an exported build has no tooling)
    import accept  # noqa: PLC0415  # (talk_through)
    import play  # noqa: PLC0415

    class Game:  # what play.Player needs of a game: its window, its keys, frames
        def __init__(self) -> None:
            self.window, self.arcade = window, arcade

        def step(self, frames: int = 1) -> None:
            for _ in range(frames):
                window.dispatch_event("on_update", 1 / 60)

        def player(self) -> Any:
            return next(s for s in window.scene_controller.all_sprites if getattr(s, "mesh_tag", None) == "player")

    game = Game()
    p = play.Player.__new__(play.Player)
    p.game, p.window, p.k, p.log = game, window, arcade.key, []
    story = lambda: [f for f in p.flags() if f in STORY]  # noqa: E731
    game.step(30)
    report["new_game"] = {"room": p.room(), "story_flags": story(), "all_flags": p.flags(),
                          "counters": dict(getattr(window.game_state_controller.state, "counters", {}) or {})}
    play.to_steward(p)
    if role == "A":
        report["opening"] = accept.talk_through(p, "I'll light the watchfire.")
        play.emberford_to_crossing(p)
        play.to_marker(p)
        report["marker"] = accept.talk_through(p, "Strike the flint")
        game.step(30)
        report["before_save"] = {"room": p.room(), "story_flags": story(), "fires": p.fires()}
        report["saved"] = window.save_manager.save_game("slot_a")
        report["loaded"] = window.save_manager.load_game("slot_a")
        game.step(30)
        report["after_load"] = {"room": p.room(), "story_flags": story(), "fires": p.fires()}
        return
    report["opening"] = accept.talk_through(p)  # (up to its choices: decline the task if it is offered)
    if "Not right now." not in ((p.dialogue() or {}).get("choices") or []):
        return  # (not the fresh introduction: the steward already thinks the task is done; nothing more to see)
    report["opening"] += ["[chose: Not right now.]"] + [str(d["text"]) for d in (p.choose("Not right now."),) if d]
    p.read_on()
    play.emberford_to_crossing(p)
    play.to_marker(p)
    game.step(10)
    report["crossing"] = {"room": p.room(), "story_flags": story(), "fires": p.fires()}
    if role == "B":
        report["loaded"] = window.save_manager.load_game("slot_a")
        game.step(30)
        report["after_load"] = {"room": p.room(), "story_flags": story(), "fires": p.fires()}


def _flags(role: str, window: Any, report: dict[str, Any]) -> None:
    """Any project (the CI check, on Mesh's starter template): A sets the story's progress as its dialogue choices
    would, saves and loads that save; B looks at its new game, then loads A's save."""
    def step(frames: int) -> None:
        for _ in range(frames):
            window.dispatch_event("on_update", 1 / 60)

    state = window.game_state_controller
    story = lambda: sorted(f for f in STORY if state.state.flags.get(f))  # noqa: E731
    step(10)
    report["new_game"] = {"room": str(window.scene_controller.current_scene_path or ""), "story_flags": story(),
                          "scene_loads": list(report["scene_loads"])}
    if role == "flags-A":
        state.set_flag("task_accepted")
        state.set_flag("watchfire_lit")
        report["saved"] = window.save_manager.save_game("slot_a")
    report["loaded"] = window.save_manager.load_game("slot_a")
    step(10)
    report["after_load"] = {"story_flags": story()}


def flag_sessions(project: Path, engine: Path = ENGINE) -> dict[str, Any]:
    """A then B on ``project`` (its own main.py, its files kept between them): the reports, in order."""
    return {"A": _run("flags-A", engine, project, project), "files_after_A": _files(project),
            "B": _run("flags-B", engine, project, project)}


# ---------------------------------------------------------------------- the two sessions and the verdict
def _verdict(a: dict[str, Any] | None, b: dict[str, Any]) -> dict[str, Any]:
    fresh_opening = (a or {}).get("opening", [""])[:1] or [""]
    crossing = b.get("crossing", {})
    opening = b.get("opening") or []
    checks = {
        "new_game_story_flags_clear": not b.get("new_game", {}).get("story_flags", ["?"]),
        "opening_is_fresh_introduction": "[chose: Not right now.]" in opening  # (the task is offered)
        and (a is None or opening[:1] == fresh_opening),
        "watchfire_starts_cold": crossing.get("room") == "old_crossing" and bool(crossing.get("fires"))
        and not any(f["burning"] for f in crossing["fires"]) and "watchfire_lit" not in crossing.get("story_flags", []),
    }
    if a is not None:
        restored = b.get("after_load", {})
        checks["explicit_load_restores_progress"] = bool(b.get("loaded")) and \
            {"task_accepted", "watchfire_lit"} <= set(restored.get("story_flags", [])) and \
            any(f.get("burning") for f in restored.get("fires", []) if f.get("name") == "Watchfire")
    return {"checks": checks, "pass": all(checks.values())}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--session"]:
        _session(argv[1], Path(argv[2]), Path(argv[3]))
        return 0
    out = Path(argv[0])
    engine = Path(argv[argv.index("--engine") + 1]) if "--engine" in argv else ENGINE
    bundle = Path(argv[argv.index("--bundle") + 1]) if "--bundle" in argv else None
    out.mkdir(parents=True, exist_ok=True)
    project = out / "project"
    _copy_project(bundle or TRIAL, project)
    if bundle is not None and "--engine" not in argv:
        engine = project  # (an exported build plays on its own engine copy)
    tools = out / "tools"
    _copy_player(engine, project, tools)
    shutil.copy2(TRIAL / "trial_tools" / "accept.py", tools / "accept.py")
    report: dict[str, Any] = {"engine": str(engine), "project": str(project), "bundle": str(bundle) if bundle else None}
    a = None
    if "--fresh-only" not in argv:
        a = report["A"] = _run("A", engine, tools, project)
        report["files_after_A"] = _files(project)
    b = report["B"] = _run("B" if a else "B-fresh", engine, tools, project)
    report["files_after_B"] = _files(project)
    report["verdict"] = _verdict(a, b)
    if bundle is None:  # the editor reopening the project: as it stands, then remembering the Old Crossing
        session = project / ".mesh" / "editor_session_state.json"
        for remembered in (None, "packs/core_regions/scenes/old_crossing.json"):
            for mode, legacy in (("studio", None), ("legacy_editor", "1")):
                if remembered:  # (before each editor: the one before it remembered its own room)
                    state = json.loads(session.read_text(encoding="utf-8"))
                    state["last_scene_path"] = remembered
                    session.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
                os.environ.pop("MESH_LEGACY_EDITOR", None)
                if legacy:
                    os.environ["MESH_LEGACY_EDITOR"] = legacy
                report[f"{mode}{'_remembering_crossing' if remembered else ''}"] = _run("studio", engine, tools, project)
            os.environ.pop("MESH_LEGACY_EDITOR", None)
        report["files_after_editors"] = _files(project)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": report["verdict"], "B_new_game": b.get("new_game"),
                      "B_first_loads": b.get("scene_loads", [])[:3]}, indent=1))
    return 0 if report["verdict"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
