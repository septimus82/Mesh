"""D2: an AI plays a Mesh Studio play-test through MCP, with the player's own controls, in a hidden window.

The project is D1's disposable one (``d1_debug_scenario.build``):
- the starter room with its Guide, whose conversation's "I'll light it." sets ``agreed_to_help``;
- a Cellar through a door north of the player;
- an ``auto_start`` quest that moves from "agree" to "cellar" on that flag.

Mesh Studio opens it with its live session on. Every game action is the real MCP tool
(``tools.debug_play_action``), called on another thread while the window keeps running; the AI steers only by what
the tool and snapshots tell it (``nearby``, ``player``, ``dialogue``). The person's part is done with Studio's own
buttons.

    1. While editing, nothing is allowed: an action is refused (gameplay_control_off).
    2. The person allows play-tests only; the AI starts one, and its move is still refused (separate permission).
       The AI stops it.
    3. The person allows AI play too. The AI starts a play-test; invalid requests are refused with reasons.
    4. The AI walks right to the Guide (repeated moves, using "nearby"), interacts, and checks the conversation's
       refusals (moving, advancing past a choice, a choice that isn't there). It chooses "I'll light it." and
       advances to the end. The snapshot shows the flag, and the quest moved from agree to cellar.
    5. It walks to below the door and up through it: the snapshot shows the Cellar.
    6. A long move is under way when the person takes the permission back (the play bar's "AI may play"): the move
       comes back cancelled, its key let go, and the next action is refused.
    7. The AI stops the play-test. The person allows play again; an action with no play-test is refused
       (not_playing). Studio is editing the same rooms with the person's unsaved Sign, no file changed. Closed:
       studio_not_open.

    py -3.13 tooling/d2_ai_playtest_scenario.py OUT [--keep]

OUT gets ``transcript.json`` (each MCP request and response) and ``report.json``. tests/test_ai_playtest_gpu.py runs
it in the GPU lane.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

STEPS_MAX = 20  # moves the AI may make to reach a place before the scenario fails


def run(out: Path, *, keep: bool = False) -> dict[str, Any]:
    import d1_debug_scenario as d1
    from hd2d_studio_demo import StudioDriver

    from engine import authoring
    from engine.mcp_server import tools

    out.mkdir(parents=True, exist_ok=True)
    project = out / "project"
    if project.exists():
        shutil.rmtree(project)
    d1.build(project)
    hidden_bridge = os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)  # (other studies turn the live session off)
    transcript: list[dict[str, Any]] = []
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    studio = d.studio
    try:
        d.window.audio.set_muted(True)

        def ask(tool: str, **arguments: Any) -> dict[str, Any]:
            """``tools.<tool>`` on another thread (as the MCP server calls it), while Studio keeps running."""
            box: dict[str, Any] = {}
            call: Callable[..., dict[str, Any]] = getattr(tools, tool)
            thread = threading.Thread(target=lambda: box.update(answer=call(root=str(project), **arguments)))
            thread.start()
            frames = 0
            while thread.is_alive():
                d.advance()
                frames += 1
                assert frames < 3000, f"{tool} didn't come back"
            answer: dict[str, Any] = box["answer"]
            transcript.append({"tool": tool, "arguments": arguments, "response": answer})
            return answer

        def act(**arguments: Any) -> dict[str, Any]:
            return ask("debug_play_action", **arguments)

        def panel_toggle(label: str) -> None:
            """The person, editing: AI (top bar), then the panel's switch."""
            if studio.panel != "ai":
                d.button("AI")
            d.button(label, prefix=True)

        files_before = d1._files(project)
        home = studio.project.current
        authoring.apply(studio.project, [{"op": "place_prefab", "prefab": "sign", "x": 480, "y": 160}])
        studio._reload()
        studio._rebuild()
        sign_ids = {e["id"] for e in studio.project.scene()["entities"] if e.get("name") == "Sign"}

        # 1. Nothing allowed yet.
        report["1_editing_refused"] = act(action="interact")

        # 2. Play-tests allowed, playing not.
        panel_toggle("Let an AI start and stop play-tests: Off")
        report["2_started"] = ask("debug_start_playtest")
        report["2_move_refused"] = act(action="move", direction="right", frames=10)
        report["2_stopped"] = ask("debug_stop_playtest")

        # 3. Playing allowed too.
        panel_toggle("Let an AI play: Off")
        report["3_allowed"] = {"playtest": studio.ai.playtest_control, "gameplay": studio.ai.gameplay_control}
        report["3_started"] = ask("debug_start_playtest")
        report["3_invalid"] = {
            "unknown action": act(action="jump"),
            "unknown direction": act(action="move", direction="north", frames=10),
            "too many frames": act(action="move", direction="right", frames=500),
            "advance with nothing said": act(action="advance"),
            "choose with no choices": act(action="choose", choice=0)}

        # 4. To the Guide, and talk.
        report["4_walk"] = walk_to(act, lambda snap: _entity(snap, "Guide"), stop_within=44.0)
        report["4_interact"] = act(action="interact")
        report["4_refused_in_dialogue"] = {
            "move": act(action="move", direction="left", frames=5),
            "advance past the choice": act(action="advance"),
            "a choice that isn't there": act(action="choose", choice="Maybe later?"),
            "interact again": act(action="interact")}
        report["4_choose"] = act(action="choose", choice="I'll light it.")
        lines: list[dict[str, Any]] = []
        while (report["4_choose"]["snapshot"].get("dialogue") or {}).get("open") and len(lines) < 5:
            lines.append(act(action="advance"))
            if not (lines[-1].get("snapshot", {}).get("dialogue") or {}).get("open"):
                break
        report["4_advanced"] = lines
        report["4_snapshot"] = ask("debug_runtime_snapshot", events=12)

        # 5. Below the door, then up through it.
        door = next(e for e in studio.project.scene()["entities"] if (e.get("name") or "").startswith("Door to"))
        report["5_line_up"] = walk_axis(act, "x", float(door["x"]))
        report["5_through"] = walk_until_room(act, "up", "cellar")
        report["5_snapshot"] = ask("debug_runtime_snapshot", events=6)

        # 6. A long move, interrupted by the person.
        report["6_interrupted"] = interrupted_move(d, studio, project, transcript)
        report["6_after"] = act(action="move", direction="down", frames=5)

        # 7. Stop; with no play-test, playing is refused even when allowed; the person's work as it was.
        report["7_stopped"] = ask("debug_stop_playtest")
        panel_toggle("Let an AI play: Off")
        report["7_not_playing"] = act(action="interact")
        report["7_editing"] = {
            "mode": studio.mode, "same_room": studio.project.current == home, "unsaved": studio.project.is_dirty,
            "sign_kept": sign_ids <= {e["id"] for e in studio.project.scene()["entities"]},
            "files_unchanged": d1._files(project) == files_before,
            "proposals": len(studio.ai.proposals)}
        studio.ai.stop()  # (Studio closing; on_close does this)
        report["7_closed"] = tools.debug_play_action("interact", root=str(project))
    finally:
        d.close()
        if hidden_bridge is not None:
            os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = hidden_bridge
        (out / "transcript.json").write_text(json.dumps(transcript, indent=1, default=str) + "\n", encoding="utf-8")
        (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
        if not keep:
            shutil.rmtree(project, ignore_errors=True)
    report["transcript"] = transcript
    return report


def _entity(snap: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((e for e in (snap.get("nearby") or {}).get("entities", []) if e.get("name") == name), None)


def walk_to(act: Callable[..., dict[str, Any]], find: Callable[[dict[str, Any]], dict[str, Any] | None], *,
            stop_within: float) -> list[dict[str, Any]]:
    """Moves right until ``find`` (in the action's snapshot) is ``stop_within`` px away: what an AI does."""
    steps: list[dict[str, Any]] = []
    snap = act(action="move", direction="right", frames=1)["snapshot"]
    for _ in range(STEPS_MAX):
        target = find(snap)
        assert target is not None, "the target isn't nearby"
        if abs(target["dx"]) <= stop_within:
            return steps
        frames = max(2, min(30, int((abs(target["dx"]) - stop_within) / 4)))
        result = act(action="move", direction="right" if target["dx"] > 0 else "left", frames=frames)
        steps.append({"frames": frames, "before": result["action"]["before"], "after": result["action"]["after"]})
        snap = result["snapshot"]
    raise AssertionError(("didn't reach it", steps))


def walk_axis(act: Callable[..., dict[str, Any]], axis: str, goal: float, within: float = 6.0) -> list[Any]:
    """Moves along ``axis`` to ``goal`` px, from where the action results say the player is."""
    steps: list[Any] = []
    index = 0 if axis == "x" else 1
    result = act(action="move", direction="left", frames=1)
    for _ in range(STEPS_MAX):
        at = result["action"]["after"]["player"][index]
        gap = goal - at
        if abs(gap) <= within:
            return steps
        frames = max(1, min(60, int(abs(gap) / 4)))
        direction = ("right" if gap > 0 else "left") if axis == "x" else ("up" if gap > 0 else "down")
        result = act(action="move", direction=direction, frames=frames)
        steps.append(result["action"]["after"]["player"])
    raise AssertionError(("didn't get there", steps))


def walk_until_room(act: Callable[..., dict[str, Any]], direction: str, room: str) -> list[Any]:
    steps: list[Any] = []
    for _ in range(STEPS_MAX):
        result = act(action="move", direction=direction, frames=20)
        steps.append(result["action"]["after"])
        if ((result["snapshot"].get("scene") or {}).get("room") or {}).get("key") == room:
            return steps
    raise AssertionError(("didn't reach", room, steps))


def interrupted_move(d: Any, studio: Any, project: Path, transcript: list[dict[str, Any]]) -> dict[str, Any]:
    """A 120-frame move; after a few frames the person clicks "AI may play" on the play bar."""
    from engine.mcp_server import tools

    box: dict[str, Any] = {}
    arguments: dict[str, Any] = {"action": "move", "direction": "down", "frames": 120}
    thread = threading.Thread(target=lambda: box.update(
        answer=tools.debug_play_action("move", direction="down", frames=120, root=str(project))))
    thread.start()
    for _ in range(600):
        d.advance()
        if studio.ai.play.running is not None and studio.ai.play.running["frames"] >= 10:
            break
    keys = d.window.input_controller.manager
    down_while_moving = sorted(keys.get_keys_down())
    widget = next(w for w in studio.play_ui.walk_widgets() if getattr(w, "text", None) == "AI may play")
    r = widget.rect
    d.click(r.left + r.width / 2, r.bottom + r.height / 2)
    frames = 0
    while thread.is_alive():
        d.advance()
        frames += 1
        assert frames < 600
    transcript.append({"tool": "debug_play_action", "arguments": arguments, "response": box["answer"],
                       "note": "the person took back the permission while it ran"})
    return {"answer": box["answer"], "down_while_moving": down_while_moving,
            "down_after": sorted(keys.get_keys_down()), "gameplay_control": studio.ai.gameplay_control}


if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    result = run(Path(arguments[0]), keep="--keep" in sys.argv)
    print(json.dumps({k: v for k, v in result.items() if k != "transcript"}, indent=1, default=str))
