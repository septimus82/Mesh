"""D1: an AI debugs a play-test through MCP while a person works in Mesh Studio, end to end, in a hidden window.

A disposable project (``build``): Mesh's starter room with its Guide, whose conversation asks the player to light the
cellar lantern ("I'll light it." sets the flag ``agreed_to_help``); a second room, the Cellar, through a door in the
starter room; and a quest, "Light the cellar lantern" (``auto_start``), whose first stage completes when that flag is
set. The quest starts with the play-test, and agreeing moves it from "agree" to "cellar".

(History: D1's first run, before #446, found that the quest never started. A play-test starts from
``GameStateController.replace_state({})``, which then left the quests' records unsynced, so the snapshot showed the
flag set and the quest still "inactive" with no stage. #446 made ``replace_state`` re-sync them. The D1 evidence is
in docs/reviews/d1_runtime_debugger_transcript.json.)

``run`` opens it in Mesh Studio (its live session on, as for a person) and plays the scenario. Every MCP call is the
real tool function (engine/mcp_server/tools.py) called on another thread, as the MCP server would, while the window
keeps drawing frames, so Studio's main thread answers it from its queue:

    1. a snapshot while editing: not_playing;  the person makes an unsaved edit (a Sign)
    2. debug_start_playtest: refused, the person hasn't allowed it;  the person turns it on in the AI panel
    3. refused again while the person has typed in a box and not finished;  they finish (nothing changed)
    4. debug_start_playtest: playing (and again: already_playing);  a snapshot: the starter room and its player
    5. the player walks to the Guide and talks (arrow keys, E), choosing "I'll light it."
    6. a snapshot: the flag, the quest's next stage, and the events that made them
    7. the player goes through the door: a snapshot in the Cellar
    8. debug_stop_playtest: stopped (and again: not_playing);  a snapshot: not_playing
    9. Studio is editing the same rooms, the Sign still unsaved, no file changed;  Studio closes: studio_not_open

    py -3.13 tooling/d1_debug_scenario.py OUT

OUT gets ``project/`` (deleted again unless --keep), ``transcript.json`` (each MCP request and its response) and
``report.json`` (what was checked). tests/test_runtime_debugger_gpu.py runs it in the GPU lane.
"""

from __future__ import annotations

import copy
import hashlib
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

WORLD = "packs/core_regions/worlds/main.json"
FLAG = "agreed_to_help"
DOOR_AT = (128.0, 352.0)  # px, in the starter room: north of where the player starts
TALK = {"speaker": "Guide", "start": "root", "nodes": {
    "root": {"text": "The cellar lantern has gone out. Will you light it?", "choices": [
        {"id": "help", "text": "I'll light it.", "set_flags": {FLAG: True}, "next": "thanks"},
        {"id": "later", "text": "Not now.", "next": "later"}]},
    "thanks": {"text": "Thank you! The cellar door is just north of here."},
    "later": {"text": "Come back when you can."}}}
QUEST = {"id": "light_the_lantern", "title": "Light the cellar lantern", "auto_start": True, "stages": [
    {"id": "agree", "title": "Talk to the Guide", "requirements": {"flags": {FLAG: True}}},
    {"id": "cellar", "title": "Go down to the cellar"}]}


def build(dest: Path) -> Path:
    """The scenario's project at ``dest`` (made new)."""
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    create_project(dest, "Lantern", template_id="starter")
    start = dest / "packs/core_regions/scenes/start.json"
    scene = json.loads(start.read_text(encoding="utf-8"))
    guide = next(e for e in scene["entities"] if e.get("name") == "Guide")
    guide["behaviour_config"]["Dialogue"]["dialogue"] = copy.deepcopy(TALK)
    start.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    project = Project.open(dest, WORLD)
    assert project is not None
    home = project.current
    cellar = project.add_room("Cellar")
    project.link_rooms(home, DOOR_AT, cellar, (256.0, 224.0))
    project.save()
    quests = dest / "assets/data/quests.json"
    quests.parent.mkdir(parents=True, exist_ok=True)
    quests.write_text(json.dumps({"quests": [QUEST]}, indent=2) + "\n", encoding="utf-8")
    return dest


def _files(root: Path) -> dict[str, str]:
    """The project's files and their hashes, but the live session's own record (.mesh)."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".mesh" not in p.relative_to(root).parts}


def run(out: Path, *, keep: bool = False) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    from engine import authoring
    from engine.mcp_server import tools

    out.mkdir(parents=True, exist_ok=True)
    project = out / "project"
    if project.exists():
        shutil.rmtree(project)
    build(project)
    hidden_bridge = os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)  # (other studies turn the live session off)
    transcript: list[dict[str, Any]] = []
    report: dict[str, Any] = {"project": "a disposable copy (deleted)" if not keep else str(project)}
    d = StudioDriver(project)
    studio, keys = d.studio, d.arcade.key
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
                assert frames < 600, f"{tool} didn't come back"
            answer: dict[str, Any] = box["answer"]
            transcript.append({"tool": tool, "arguments": arguments, "response": answer})
            return answer

        files_before = _files(project)
        home = studio.project.current

        # 1. Editing: nothing runs. The person adds a Sign and doesn't save.
        report["1_editing"] = ask("debug_runtime_snapshot")
        authoring.apply(studio.project, [{"op": "place_prefab", "prefab": "sign", "x": 480, "y": 160}])
        studio._reload()
        studio._rebuild()
        sign_ids = {e["id"] for e in studio.project.scene()["entities"] if e.get("name") == "Sign"}
        report["unsaved_edit"] = {"unsaved": studio.project.is_dirty, "revision": studio.project.revision}

        # 2. Not allowed yet; the person allows it (top bar: AI, then the toggle).
        report["2_refused"] = ask("debug_start_playtest")
        d.button("AI")
        d.button("Let an AI start and stop play-tests: Off")
        report["2_allowed"] = {"playtest_control": studio.ai.playtest_control,
                               "shown": d.has_button("Let an AI start and stop play-tests: On")}

        # 3. The person is typing in a box: refused, and the box left as it is. They finish.
        studio.selected = next(e["id"] for e in studio.project.scene()["entities"] if e.get("name") == "Guide")
        studio.panel = "inspect"
        studio._rebuild()
        field_key = next(k for k in ("name", "entity_name") if k in studio._focusable)
        original = studio._focusable[field_key].text
        _type_without_enter(d, field_key, original + " the Elder")
        report["3_busy"] = ask("debug_start_playtest")
        report["3_box_kept"] = {"text": studio._focusable[field_key].text, "mode": studio.mode}
        _type_without_enter(d, field_key, original)
        d.key(keys.ESCAPE)  # (the same name: nothing to commit; the box let go)
        studio.selected = None
        studio._rebuild()

        # 4. Play.
        report["4_started"] = ask("debug_start_playtest")
        report["4_again"] = ask("debug_start_playtest")
        d.advance(30)
        report["4_snapshot"] = ask("debug_runtime_snapshot")
        report["4_runtime_quests"] = copy.deepcopy(d.window.game_state_controller.state.values.get("quests"))

        # 5. The player talks to the Guide and agrees, with the game's own keys.
        report["5_talk"] = _talk(d, "I'll light it.")
        d.advance(10)

        # The read itself changes nothing (no frame between: compared as it was just before).
        report["read_changes_nothing"] = _read_is_pure(studio)

        # 6. What changed, and why.
        report["6_snapshot"] = ask("debug_runtime_snapshot", events=12)
        report["6_runtime_quests"] = copy.deepcopy(d.window.game_state_controller.state.values.get("quests"))

        # 7. Through the door to the Cellar.
        report["7_moved"] = _through_door(d)
        report["7_snapshot"] = ask("debug_runtime_snapshot", events=6)

        # 8. Stop.
        report["8_stopped"] = ask("debug_stop_playtest")
        report["8_again"] = ask("debug_stop_playtest")
        report["8_snapshot"] = ask("debug_runtime_snapshot")

        # 9. Back to editing, the person's work as it was.
        report["9_editing"] = {
            "mode": studio.mode, "room": studio.project.current, "same_room": studio.project.current == home,
            "unsaved": studio.project.is_dirty, "sign_kept": sign_ids <= {e["id"] for e in studio.project.scene()["entities"]},
            "files_unchanged": _files(project) == files_before,
            "flags_after_stop": dict(d.window.game_state_controller.state.flags)}
        token = studio.ai.bridge.token
        studio.ai.stop()  # (Studio closing: its session goes; on_close does this)
        transcript.append({"tool": "debug_runtime_snapshot", "arguments": {},
                           "response": tools.debug_runtime_snapshot(root=str(project)), "note": "after Studio closed"})
        report["9_closed"] = transcript[-1]["response"]
        said = json.dumps(transcript)
        report["nothing_secret"] = {"token": token not in said, "project_folder": str(project.resolve()) not in said
                                    and str(project.resolve()).replace("\\", "\\\\") not in said}
    finally:
        d.close()
        if hidden_bridge is not None:
            os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = hidden_bridge
        (out / "transcript.json").write_text(json.dumps(transcript, indent=1) + "\n", encoding="utf-8")
        (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
        if not keep:
            shutil.rmtree(project, ignore_errors=True)
    report["transcript"] = transcript
    return report


def _type_without_enter(d: Any, key: str, text: str) -> None:
    """As ``StudioDriver.type_into``, but the person stops before Enter: the box holds text not yet committed."""
    k = d.arcade.key
    field = d.studio._focusable[key]
    d.advance()
    r = field.rect
    if not field.active:
        d.click(r.left + r.width / 2, r.bottom + r.height / 2)
    d.window.dispatch_event("on_key_press", k.A, k.MOD_CTRL)
    d.window.dispatch_event("on_key_release", k.A, k.MOD_CTRL)
    d.window.dispatch_event("on_text", text)
    d.advance()


def _talk(d: Any, answer: str) -> dict[str, Any]:
    """The player walks up to the Guide and talks with E, choosing ``answer``: what was said."""
    game, keys = d.game, d.arcade.key
    box = d.window.ui_controller.dialogue_box
    guide = game.sprite("Guide")
    player = game.player()
    for _ in range(200):
        if guide.center_x - player.center_x <= 48:
            break
        d.window.dispatch_event("on_key_press", keys.RIGHT, 0)
        d.advance()
    d.window.dispatch_event("on_key_release", keys.RIGHT, 0)
    d.advance(3)
    said: list[str] = []
    d.window.dispatch_event("on_key_press", keys.E, 0)
    d.advance(2)
    d.window.dispatch_event("on_key_release", keys.E, 0)
    d.advance(5)
    for _ in range(12):
        if not box.is_active():
            break
        said.append(str((box._current_entry or {}).get("text")))
        choices = [c.get("text") for c in box._choices]
        if choices:
            target = choices.index(answer)
            for _ in range(target - box._choice_index):
                d.window.dispatch_event("on_key_press", keys.DOWN, 0)
                d.advance(2)
                d.window.dispatch_event("on_key_release", keys.DOWN, 0)
                d.advance(2)
        d.window.dispatch_event("on_key_press", keys.E, 0)
        d.advance(2)
        d.window.dispatch_event("on_key_release", keys.E, 0)
        d.advance(5)
    return {"said": said, "player_at": [round(player.center_x, 1), round(player.center_y, 1)]}


def _through_door(d: Any) -> dict[str, Any]:
    """The player stands below the door and walks up into it (the arrow key): the room it arrives in."""
    keys = d.arcade.key
    controller = d.window.scene_controller
    before = controller.current_scene_path
    player = d.game.player()
    player.center_x, player.center_y = DOOR_AT[0], DOOR_AT[1] - 64
    d.advance(2)
    for _ in range(240):
        if controller.current_scene_path != before:
            break
        d.window.dispatch_event("on_key_press", keys.UP, 0)
        d.advance()
    d.window.dispatch_event("on_key_release", keys.UP, 0)
    d.advance(20)
    return {"from": before, "to": controller.current_scene_path}


def _read_is_pure(studio: Any) -> dict[str, Any]:
    """A snapshot taken directly on the main thread, the running game compared before and after it."""
    window = studio.window

    def state() -> Any:
        controller = window.scene_controller
        player = controller._find_player_sprite()
        return (copy.deepcopy(window.game_state_controller.state), copy.deepcopy(window.event_bus._history),
                window.event_bus.emitted, len(window._mesh_event_queue), controller.current_scene_path,
                (player.center_x, player.center_y) if player else None, studio.selected, studio.mode,
                studio.project.revision, studio.project.is_dirty, bool(window.paused))

    before = state()
    studio.ai.debug_snapshot(20)
    return {"unchanged": state() == before}


if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    result = run(Path(arguments[0]), keep="--keep" in sys.argv)
    print(json.dumps({k: v for k, v in result.items() if k != "transcript"}, indent=1, default=str))
