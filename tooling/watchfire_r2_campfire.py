"""Watchfire R2: talk to a campfire. A picture-less object the world draws itself (a campfire) carrying a conversation:
can the player use it directly, with the game's own keys?

A scratch copy of the creator trial's project (never the trial itself), with the Old Crossing's marker sign's
conversation moved onto the cold watchfire (Studio's own operations: ``project_ops``) and the sign removed, so the fire
is the only thing there to talk to. One real process starts the game as a player does (the project's ``main.py``,
hidden, silent) and plays: accept the steward's task, walk to the fire, press E (the fire's conversation, its
"Strike the flint" choice, the flag it sets), then E by the lit fire (it has nothing to say: nothing happens).

    py -3.13 tooling/watchfire_r2_campfire.py OUT [--engine DIR] [--bundle]

``--bundle`` exports the prepared copy with ``mesh export build`` (from this engine) and plays the exported game on
its own engine copy. OUT gets ``report.json``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import watchfire_r1_sessions as r1  # noqa: E402  # (the trial project's copy, its player and the session plumbing)

SCENE = "packs/core_regions/scenes/old_crossing.json"
COLD_FIRE = "old_crossing_campfire_704_480_0_0"
MARKER = "old_crossing_sign_752_460_0_0"
NEXT_TO_FIRE = (22.0, 13.6)  # tiles: two steps south of the fire (22, 15), facing it


def _prepare(project: Path, engine: Path) -> None:
    """The marker's conversation onto the cold watchfire, the marker gone (``project_ops``, as Studio edits)."""
    sys.path.insert(0, str(engine))
    from engine import project_ops as ops  # noqa: PLC0415

    path = project / SCENE
    scene = json.loads(path.read_text(encoding="utf-8"))
    conversation = ops.find_entity(scene, MARKER)["behaviour_config"]["Dialogue"]
    scene = ops.add_behaviour(scene, COLD_FIRE, "Dialogue")
    for param, value in conversation.items():
        scene = ops.set_behaviour_param(scene, COLD_FIRE, "Dialogue", param, value)
    scene = ops.remove_entity(scene, MARKER)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")


def _play(role: str, window: Any, arcade: Any, tools: Path, report: dict[str, Any]) -> None:
    """In the game's process (``r1._session`` calls this in place of the Watchfire two-session play)."""
    sys.path.insert(0, str(tools))
    sys.path.append(str(r1.ENGINE / "tooling"))
    import accept  # noqa: PLC0415,F401  # (play.py and the steward talk)
    import play  # noqa: PLC0415

    class Game:
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
    game.step(30)
    play.to_steward(p)
    report["steward"] = accept.talk_through(p, "I'll light the watchfire.")
    play.emberford_to_crossing(p)
    play.to_marker(p)
    p.walk_to(*NEXT_TO_FIRE, order="xy")
    game.step(10)
    fire = next(s for s in window.scene_controller.all_sprites if getattr(s, "mesh_name", None) == "Cold watchfire")
    report["at_fire"] = {"room": p.room(), "at": p.at(), "flags": p.flags(), "fires": p.fires(),
                         "cold_fire_sprite": {"visible": bool(fire.visible), "drawn": bool(getattr(fire, "mesh_drawn", True))}}
    def shot(name: str) -> None:  # what the player sees now (the hidden window's frame), beside the report
        game.step(2)
        window.dispatch_event("on_draw")
        arcade.get_image(0, 0, *window.get_framebuffer_size()).convert("RGB").save(tools.parent / f"{name}.png")

    shot("1_by_the_cold_fire")
    shown = p.talk()  # E
    report["press_e"] = [str(shown["text"]), f"[choices: {' | '.join(shown['choices'])}]"] if shown else []
    if shown and "Strike the flint" in shown["choices"]:
        shot("2_its_conversation")
        shown = p.choose("Strike the flint")
        report["press_e"] += ["[chose: Strike the flint]"] + [str(d["text"]) for d in p.read_on()]
    game.step(60)
    shot("3_after")
    report["after"] = {"flags": p.flags(), "fires": p.fires(), "dialogue": p.dialogue()}
    p.press(p.k.E)  # by the lit fire: its cold twin is hidden now, and the burning one has nothing to say
    game.step(5)
    report["press_e_by_lit_fire"] = p.dialogue()
    report["walk_log"] = p.log


def _run(engine: Path, tools: Path, project: Path) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_CURRENT_TEST", "PYTHONPATH", "MESH_REPO_ROOT")}
    env["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    ran = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--session", "R2", str(engine), str(tools)],
                         cwd=project, env=env, capture_output=True, text=True, timeout=900)
    found = [ln[len(r1.MARK):] for ln in ran.stdout.splitlines() if ln.startswith(r1.MARK)]
    if ran.returncode != 0 or not found:
        return {"error": f"exit {ran.returncode}", "stderr": ran.stderr[-3000:], "stdout": ran.stdout[-2000:]}
    return dict(json.loads(found[-1]))


def _verdict(run: dict[str, Any]) -> dict[str, Any]:
    talk = run.get("press_e") or []
    after = run.get("after") or {}
    checks = {
        "the_fire_is_a_picture_less_object": run.get("at_fire", {}).get("cold_fire_sprite", {}).get("drawn") is False,
        "e_at_the_fire_opens_its_conversation": bool(talk) and talk[0].startswith("The kindling"),
        "its_choice_sets_its_flag": "watchfire_lit" in after.get("flags", []),
        "the_fire_then_burns": any(f.get("burning") for f in after.get("fires", []) if f.get("name") == "Watchfire"),
        "the_hidden_cold_fire_and_the_silent_lit_one_say_nothing": run.get("press_e_by_lit_fire") is None
        and bool(talk),
    }
    return {"checks": checks, "pass": all(checks.values())}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--session"]:
        r1._play = _play  # (the session plumbing is R1's; the play is this one)
        r1._session(argv[1], Path(argv[2]), Path(argv[3]))
        return 0
    out = Path(argv[0])
    engine = Path(argv[argv.index("--engine") + 1]) if "--engine" in argv else r1.ENGINE
    out.mkdir(parents=True, exist_ok=True)
    source = out / "source"
    r1._copy_project(r1.TRIAL, source)
    _prepare(source, engine)
    project = source
    if "--bundle" in argv:
        project = out / "bundle"
        made = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--repo-root", str(source),
                               "--out", str(project)], cwd=engine, capture_output=True, text=True, timeout=900)
        if made.returncode != 0:
            raise SystemExit(made.stdout[-2000:] + made.stderr[-2000:])
        engine = project  # (an exported game plays on its own engine copy)
    tools = out / "tools"
    r1._copy_player(engine, project, tools)
    shutil.copy2(r1.TRIAL / "trial_tools" / "accept.py", tools / "accept.py")
    run = _run(engine, tools, project)
    verdict = _verdict(run)
    report = {"engine": str(engine), "bundle": "--bundle" in argv, "run": run, "verdict": verdict}
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "press_e": run.get("press_e"), "error": run.get("error")}, indent=1))
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
