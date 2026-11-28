"""D3A: "why can't the player use this?" answered by the MCP tool ``debug_interaction``, in a hidden window.

D1's disposable project (``d1_debug_scenario.build``), with:
- a Cellar Door in the starter room, used with the interact key, kept out of the room by its ``require_flags``
  ``["has_key"]`` (a room leaves such an object out while the flag is off when it loads);
- a Notice board just left of it (closer to a player coming from the left: chosen first);
- the Guide's "I'll light it." also giving ``has_key``, and a choice "Where is the cellar?" that needs
  ``agreed_to_help`` (a dialogue condition).

Every diagnosis is the real MCP tool, called on another thread while Studio keeps running. The player is moved by
placing it (the debugger is what's tested, not walking) and talks with the game's own keys.

    1. Editing: not_playing.
    2. Playing, no key: the door isn't in the room, its flag keeps it out, has_key is False, and the Guide's choice
       sets it. The Guide's "Where is the cellar?" needs agreed_to_help.
    3. After talking to the Guide: has_key is True, the door is still not in the room (the room loaded first: a
       possible cause, not a fact), and "Where is the cellar?" can now be picked.
    4. Out to the Cellar and back: the door is in the room.
    5. From far away: too far. Left of the Notice, facing right: the Notice is chosen instead (it is nearer).
       Right of the door, facing left: available. Pressing interact then really takes the player to the Cellar.
    6. Reading changed nothing: flags, room, events and the player are as they were.

    py -3.13 tooling/d3a_interaction_scenario.py OUT [--keep]
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

START = "packs/core_regions/scenes/start.json"
DOOR = {"id": "cellar_door", "name": "Cellar Door", "x": 560.0, "y": 128.0, "sprite": "assets/sprites/starter_sign.png",
        "require_flags": ["has_key"], "behaviours": ["SceneTransition"],
        "behaviour_config": {"SceneTransition": {"target_scene": "cellar", "spawn_id": "from_start",
                                                 "allow_interact": True, "trigger_on_touch": False}}}
NOTICE = {"id": "notice", "name": "Notice", "x": 520.0, "y": 128.0, "sprite": "assets/sprites/starter_sign.png",
          "behaviours": ["Dialogue"],
          "behaviour_config": {"Dialogue": {"dialogue": {"speaker": "", "start": "root",
                                                         "nodes": {"root": {"text": "Cellar: staff only."}}},
                                            "once": False}}}
FAR, CROWDED, CLEAR = (200.0, 128.0), (500.0, 128.0), (600.0, 128.0)


def build(dest: Path) -> Path:
    import d1_debug_scenario as d1

    d1.build(dest)
    scene = json.loads((dest / START).read_text(encoding="utf-8"))
    guide = next(e for e in scene["entities"] if e.get("name") == "Guide")
    talk = guide["behaviour_config"]["Dialogue"]["dialogue"]
    root = talk["nodes"]["root"]
    root["choices"][0]["set_flags"] = {d1.FLAG: True, "has_key": True}
    root["choices"].append({"id": "where", "text": "Where is the cellar?", "require_flags": [d1.FLAG],
                            "next": "thanks"})
    scene["entities"] += [copy.deepcopy(DOOR), copy.deepcopy(NOTICE)]
    (dest / START).write_text(json.dumps(scene, indent=1), encoding="utf-8")
    return dest


def run(out: Path, *, keep: bool = False) -> dict[str, Any]:
    import d1_debug_scenario as d1
    from hd2d_studio_demo import StudioDriver

    from engine.mcp_server import tools

    out.mkdir(parents=True, exist_ok=True)
    project = out / "project"
    if project.exists():
        shutil.rmtree(project)
    build(project)
    hidden_bridge = os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)  # (other studies turn the live session off)
    transcript: list[dict[str, Any]] = []
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    studio, window = d.studio, d.window
    try:
        window.audio.set_muted(True)

        def ask(entity_id: str, note: str) -> dict[str, Any]:
            """``tools.debug_interaction`` on another thread (as the MCP server calls it), while Studio runs."""
            box: dict[str, Any] = {}
            thread = threading.Thread(target=lambda: box.update(
                answer=tools.debug_interaction(entity_id, root=str(project))))
            thread.start()
            frames = 0
            while thread.is_alive():
                d.advance()
                frames += 1
                assert frames < 600, "debug_interaction didn't come back"
            answer: dict[str, Any] = box["answer"]
            transcript.append({"tool": "debug_interaction", "arguments": {"entity_id": entity_id}, "note": note,
                               "response": answer})
            return answer

        def place(at: tuple[float, float], facing_key: int | None = None) -> None:
            player = d.game.player()
            if facing_key is not None:  # (face that way: a step's key, then back to the spot)
                window.dispatch_event("on_key_press", facing_key, 0)
                d.advance(2)
                window.dispatch_event("on_key_release", facing_key, 0)
            player.center_x, player.center_y = at
            d.advance(3)

        keys = d.arcade.key
        report["1_editing"] = ask("cellar_door", "editing")
        studio.play()
        d.advance(10)
        report["2_no_key"] = ask("cellar_door", "playing, no key")
        report["2_guide"] = ask("start_guide_320_128_0_0", "the Guide's conversation")
        report["3_talk"] = d1._talk(d, "I'll light it.")
        d.advance(10)
        report["3_key_not_reloaded"] = ask("cellar_door", "has_key now, the room loaded before")
        report["3_guide"] = ask("start_guide_320_128_0_0", "the Guide again")
        report["4_through"] = d1._through_door(d)
        player = d.game.player()
        back = next(s for s in window.scene_controller.all_sprites if (s.mesh_name or "").startswith("Door to"))
        player.center_x, player.center_y = back.center_x, back.center_y
        d.advance(20)
        report["4_room"] = window.scene_controller.current_scene_path
        place(FAR, keys.RIGHT)
        report["5_far"] = ask("cellar_door", "far away")
        place(CROWDED, keys.RIGHT)
        report["5_crowded"] = ask("cellar_door", "next to the door and the Notice")
        place(CLEAR, keys.LEFT)
        before = _state(window, d)
        report["5_clear"] = ask("cellar_door", "next to the door alone")
        report["6_read_changed_nothing"] = _state(window, d) == before
        window.dispatch_event("on_key_press", keys.E, 0)
        d.advance(2)
        window.dispatch_event("on_key_release", keys.E, 0)
        d.advance(20)
        report["5_pressed_interact"] = window.scene_controller.current_scene_path
        studio.stop()
        d.advance(3)
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


def _state(window: Any, d: Any) -> Any:
    player = d.game.player()
    state = window.game_state_controller.state
    return (dict(state.flags), dict(state.counters), window.scene_controller.current_scene_path,
            window.event_bus.emitted, len(window._mesh_event_queue), (player.center_x, player.center_y))



if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    result = run(Path(arguments[0]), keep="--keep" in sys.argv)
    print(json.dumps({k: v for k, v in result.items() if k != "transcript"}, indent=1, default=str))
