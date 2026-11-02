"""Watchfire R4: a conversation written in Mesh Studio, saved, closed and reopened: what changes?

A disposable copy of the M23B clearing (tooling/m23b_fire_study.py). Everything is done in Mesh Studio's hidden window
with its own mouse and keyboard events: a Person placed (Objects > Person), its conversation written in the Dialogue
tab (its first line, "+ Next line", "+ Separate line", "+ Line after", choices that set a flag and lead to lines, an
opening that needs the flag), saved; Studio closed and reopened; the same conversation looked at again, then edited
(a line's words, a line inserted, a choice's destination, a line deleted), undone and redone, another room visited and
back, saved and reopened again, and saved and reopened twice more without edits.

Recorded each time: the inspector's line list as shown (numbers and flow), its "Otherwise line" and openings, and the
conversation as stored (line ids, what follows each, the choices' destinations and flags). Then the conversation is
played in the game (a hidden game window, the player walking up and pressing E) and in an exported build.

    py -3.13 tooling/watchfire_r4_dialogue.py OUT
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parents[1]

WHEEL_LIMIT = 100  # notches (two rows each): the most any scroll through the inspector may take before it fails
WARDEN = (8.0, 9.0)  # m: where the Warden is placed (open ground in the clearing)
LINES = {  # the conversation, as written (each line's words are unique: the driver finds lines by their words)
    "root": "Traveller! The watchfire at the crossing has gone dark.",
    "ask": "Will you light it before nightfall?",
    "yes": "Bless you. Take my flint.",
    "no": "Then I'll keep waiting... but the dark won't.",
    "road": "Follow the road east, past the lamps.",
    "ford": "Mind the ford: it runs cold.",
    "flint": "Strike the flint on the dry kindling.",
    "carry": "Its light will carry to the forest road.",
    "tell": "Come back and tell me when it burns.",
    "bye": "Safe travels.",
    "again": "Back already? Is it lit?",
}


def make(out: Path) -> Path:
    import m23b_fire_study as study

    project: Path = study.make_project(out, "r4", fires=[])
    return project


def run(out: Path) -> dict[str, Any]:
    import m20c_material_study as m20c
    import m23b_fire_study as study
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    out.mkdir(parents=True, exist_ok=True)
    project = make(out)
    room_file = project / study.ROOM
    report: dict[str, Any] = {}
    state: dict[str, Any] = {"d": StudioDriver(project)}

    def d() -> Any:
        return state["d"]

    def open_room(key_suffix: str = "hills.json") -> None:
        key = next(k for k, _l, path in d().studio.project.rooms() if path.endswith(key_suffix))
        d().button(d().studio.project.label(key))
        d().advance(3)

    def ground(x: float, y: float, up: float = 0.0) -> tuple[float, float]:
        z = d().renderer.ground_height(x * study.PX, y * study.PX) / study.PX
        sx, sy = d().screen((x, y, z + up))
        return float(sx), float(sy)

    def warden() -> dict[str, Any]:
        return next(e for e in ops.entities(d().studio.project.scene()) if e.get("name") == "Warden")

    def select_warden() -> None:  # a click on it in the 3D view, then its Dialogue tab
        m20c._look_at(d(), WARDEN[0], WARDEN[1] + 1.0, 10.0)
        if d().studio.selected != warden()["id"]:
            d().click(*ground(*WARDEN, up=0.75))
            d().advance(2)
        assert d().studio.selected == warden()["id"], "the Warden selected by clicking it"
        d().button("Dialogue")
        d().advance()

    def visible_lines() -> list[str]:
        return [t for t in d().labels() if re.match(r"^\d+\. ", t)]

    def wheel(notches: int, times: int) -> None:  # the mouse wheel over the inspector (the right panel)
        x, y = d().window.width - 160, d().window.height // 2
        for _ in range(times):
            d().window.dispatch_event("on_mouse_scroll", x, y, 0, notches)
            d().advance()

    def more(below: bool) -> int:  # how many rows Studio says are out of view that way ("v 3 more below")
        return int(d().studio._panel_more[1 if below else 0])

    def to_top() -> None:
        """The mouse wheel up over the inspector until nothing more is above (boundary-aware: no notches wasted at the
        top, where Studio ignores them)."""
        for _ in range(WHEEL_LIMIT):
            if not more(below=False):
                return
            wheel(1, 1)
        raise AssertionError(f"the inspector never reached its top in {WHEEL_LIMIT} notches: {d().studio._panel_more}")

    def down_until(found: Any) -> Any:
        """From the inspector's top, a notch down at a time until ``found()`` gives something (returned) or nothing
        more is below (None). Fails if the bottom isn't reached in WHEEL_LIMIT notches."""
        to_top()
        for _ in range(WHEEL_LIMIT):
            hit = found()
            if hit or not more(below=True):
                return hit or None
            wheel(-1, 1)
        raise AssertionError(f"the inspector never reached its bottom in {WHEEL_LIMIT} notches: {d().studio._panel_more}")

    def all_labels() -> list[str]:
        """Everything in the panels, read with the mouse wheel from top to bottom (it shows part at a time)."""
        seen: list[str] = []

        def read() -> None:
            seen.extend(t for t in d().labels() if t not in seen)

        down_until(read)
        to_top()
        return seen

    def all_lines() -> list[str]:
        """The line list, in its numbers' order."""
        lines = [t for t in all_labels() if re.match(r"^\d+\. ", t)]
        return sorted(lines, key=lambda t: int(t.split(".", 1)[0]))

    def shown() -> dict[str, Any]:
        """The Dialogue tab as the creator sees it."""
        labels = all_labels()
        lines = sorted((t for t in labels if re.match(r"^\d+\. ", t)), key=lambda t: int(t.split(".", 1)[0]))
        focus = d().studio._focusable
        return {"lines": lines,
                "otherwise_line": getattr(focus.get("dlg_start"), "text", None),
                "openings": [getattr(focus.get(f"open_node_{i}"), "text", None) for i in range(4) if f"open_node_{i}" in focus],
                "next_line_button": [t for t in labels if t.startswith("+ Next line")]}

    def stored() -> dict[str, Any]:
        """The conversation as stored: line ids, words, what follows, the choices; start and openings."""
        talk = ops.conversation(warden())
        return {"start": talk["start"], "starts": talk["starts"],
                "nodes": {nid: {"text": n.get("text"), "next": n.get("next"),
                                "choices": [{"text": c.get("text"), "next": c.get("next"), "set_flags": c.get("set_flags")}
                                            for c in n.get("choices") or []]} for nid, n in talk["nodes"].items()}}

    def line(words: str) -> None:
        """Select the line with these words (its button in the list), unless it's the one open."""
        current = d().studio.dlg_line
        if current is not None and (warden_nodes().get(current) or {}).get("text") == words:
            return
        d().button(label_of(words))
        d().advance()

    def warden_nodes() -> dict[str, Any]:
        nodes: dict[str, Any] = ops.conversation(warden())["nodes"]
        return nodes

    def label_of(words: str) -> str:
        """The line list's button for the line with these words (scrolled to, as a person would)."""
        def match() -> str | None:
            return next((t for t in visible_lines() if t.split(". ", 1)[1].startswith(words[:20])), None)
        found = down_until(match)
        if found is None:
            raise AssertionError((words, all_lines()))
        return str(found)

    def number_of(words: str) -> str:
        return label_of(words).split(".", 1)[0]

    def type_line(text: str) -> None:
        d().type_into("line_text", text)
        d().advance()

    def save() -> str:
        d().key(d().arcade.key.S, d().arcade.key.MOD_CTRL)
        d().advance()
        return str(d().studio.message)

    def reopen() -> None:
        d().close()
        state["d"] = StudioDriver(project)
        open_room()
        select_warden()

    try:
        open_room()
        # the Warden: Objects > Person, a click on the ground; renamed
        m20c._look_at(d(), WARDEN[0], WARDEN[1] + 1.0, 10.0)
        d().studio.set_left_tab("objects")
        d().advance()
        d().button("Person")
        d().click(*ground(*WARDEN))
        d().advance(2)
        d().key(d().arcade.key.ESCAPE)
        d().advance()
        d().click(*ground(*WARDEN, up=0.75))
        d().advance(2)
        d().type_into("name", "Warden")
        d().advance()
        select_warden()

        # write the conversation
        d().type_into("says", LINES["root"])
        d().advance()
        d().button("+ Next line", prefix=True)  # (after 1)
        type_line(LINES["ask"])
        for key in ("yes", "no", "road"):  # branch targets and the road on: separate lines
            d().button("+ Separate line")
            type_line(LINES[key])
        for prev, key in (("road", "ford"), ("ford", "flint"), ("flint", "carry"), ("carry", "tell"), ("tell", "bye")):
            line(LINES[prev])
            d().button("+ Line after")
            type_line(LINES[key])
        d().button("+ Separate line")
        type_line(LINES["again"])
        line(LINES["yes"])  # "Bless you" runs on to the road
        d().type_into("line_next", number_of(LINES["road"]))
        d().advance()
        line(LINES["ask"])  # its two choices
        for text, goes, sets in (("I'll light the watchfire.", "yes", "task_accepted"), ("Not right now.", "no", "")):
            d().button("+ Choice")
            d().type_into("choice_text", text)
            d().type_into("choice_next", number_of(LINES[goes]))
            if sets:
                d().type_into("choice_sets", sets)
            d().advance()
            line(LINES["ask"])
        d().button("+ Opening")  # once the task is accepted, the Warden opens with "Back already?"
        d().type_into("open_node_0", number_of(LINES["again"]))
        d().type_into("open_req_0", "task_accepted")
        d().advance()
        report["A_written"] = {"shown": shown(), "stored": stored()}
        report["A_saved"] = save()
        report["A_file"] = room_file.read_text(encoding="utf-8")

        # B: closed, reopened, looked at again
        reopen()
        report["B_reopened"] = {"shown": shown(), "stored": stored()}
        # a line added at the end (ops.add_line: Studio's "+ Next line"): which line does it follow?
        probe, new_id = ops.add_line(d().studio.project.scene(), warden()["id"], text="(probe)")
        probe_nodes = ops.conversation(next(e for e in ops.entities(probe) if e.get("name") == "Warden"))["nodes"]
        report["B_add_line_at_the_end_follows"] = [probe_nodes[n].get("text") for n in probe_nodes
                                                   if probe_nodes[n].get("next") == new_id]

        # C: edited after reopening: words, a line inserted, a choice's destination, a line deleted; undo and redo
        line(LINES["yes"])
        type_line("Bless you, traveller. Take my flint.")
        d().button("+ Line after")
        type_line("It sparks on the first strike.")
        line(LINES["ask"])
        d().button(f"  b) {'Not right now.'}", prefix=True)
        d().type_into("choice_next", number_of(LINES["bye"]))
        d().advance()
        line(LINES["flint"])
        d().button("Delete line")
        d().advance()
        before_undo = stored()
        d().key(d().arcade.key.Z, d().arcade.key.MOD_CTRL)
        d().advance(2)
        undone = stored()
        d().key(d().arcade.key.Y, d().arcade.key.MOD_CTRL)
        d().advance(2)
        report["C_edited"] = {"shown": shown(), "stored": stored(), "undo_restored_the_line": LINES["flint"] in
                              [n["text"] for n in undone["nodes"].values()], "redo_same": stored() == before_undo}
        # the "+ Next line" button: where does a new line go now?
        report["C_next_line_button"] = shown()["next_line_button"]

        # D: another room and back
        other = next(k for k, _l, path in d().studio.project.rooms() if not path.endswith("hills.json"))
        d().button(d().studio.project.label(other))
        d().advance(3)
        open_room()
        select_warden()
        report["D_room_and_back"] = {"shown": shown(), "stored": stored()}
        report["D_saved"] = save()
        reopen()
        report["E_reopened"] = {"shown": shown(), "stored": stored()}
        files = []
        for _ in range(2):  # saved and reopened twice more, no edits
            d().studio.project.dirty.add(d().studio.project.current)  # (Save writes only rooms with changes)
            save()
            files.append(room_file.read_text(encoding="utf-8"))
            reopen()
        report["F_repeat"] = {"files_identical": len(set(files)) == 1, "shown": shown(), "stored": stored()}
    finally:
        d().close()

    report["G_game"] = _play(project, REPO)
    bundle = out / "bundle"
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--repo-root", str(project),
                           "--out", str(bundle)], cwd=REPO, capture_output=True, text=True, timeout=900)
    report["H_export"] = {"exit": made.returncode, "tail": made.stdout[-400:]}
    report["H_exported_game"] = _play(bundle, bundle) if made.returncode == 0 else None
    (out / "report.json").write_text(json.dumps({k: v for k, v in report.items() if k != "A_file"}, indent=1,
                                                default=str) + "\n", encoding="utf-8")
    return report


PLAY = r"""
import json, sys
sys.path.insert(0, {engine!r})
import engine.optional_arcade
sys.path.append({tooling!r})
from pathlib import Path
from hd2d_demo import HiddenGame
import m23b_fire_study as study

game = HiddenGame(Path({project!r}), size=(1280, 720))
w = game.window
out = {{}}
try:
    w.audio.set_muted(True)
    game.load(study.ROOM)
    game.step(30)
    keys = game.arcade.key
    box = w.ui_controller.dialogue_box

    def said():
        return None if not box.is_active() else {{"text": (box._current_entry or {{}}).get("text"),
                                                  "choices": [c.get("text") for c in box._choices], "cursor": box._choice_index}}

    def talk():
        player = game.player()
        player.center_x, player.center_y = {x} * 32, {y} * 32 - 64
        game.step(2)
        for _ in range(120):
            if {y} * 32 - player.center_y <= 36:
                break
            game.hold(keys.UP, 1)
        game.hold(keys.E, 2)
        game.step(5)
        lines = []
        for _ in range(20):
            now = said()
            if now is None:
                break
            lines.append(now)
            if now["choices"]:
                target = now["choices"].index("I'll light the watchfire.")
                while (said() or {{}}).get("cursor", target) < target:
                    game.hold(keys.DOWN, 2)
            game.hold(keys.E, 2)
            game.step(5)
        return lines

    out["first_talk"] = [l["text"] for l in talk()]
    out["flags"] = sorted(k for k, v in w.game_state_controller.state.flags.items() if v)
    game.step(30)
    out["second_talk"] = [l["text"] for l in talk()]
finally:
    game.close()
print("R4PLAY " + json.dumps(out))
"""


def _play(project: Path, engine: Path) -> dict[str, Any]:
    """The Warden's conversation in a hidden game window on ``engine`` (an exported build: its own engine copy)."""
    code = PLAY.format(engine=str(engine), tooling=str(REPO / "tooling"), project=str(project), x=WARDEN[0], y=WARDEN[1])
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_CURRENT_TEST", "PYTHONPATH", "MESH_REPO_ROOT")}
    ran = subprocess.run([sys.executable, "-c", code], cwd=project, env=env, capture_output=True, text=True, timeout=600)
    found = [ln[len("R4PLAY "):] for ln in ran.stdout.splitlines() if ln.startswith("R4PLAY ")]
    return dict(json.loads(found[-1])) if found else {"error": ran.stderr[-2000:]}


if __name__ == "__main__":
    print(json.dumps({k: v for k, v in run(Path(sys.argv[1])).items() if k != "A_file"}, indent=1, default=str))
