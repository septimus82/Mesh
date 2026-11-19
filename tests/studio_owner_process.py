"""A Mesh Studio session in its own process, for tests of who owns a project (#462 R2). Not a test module.

    python tests/studio_owner_process.py ROOT COMMANDS [nobridge] [real]

It opens the project at ROOT as Mesh Studio does. By default without a window: Studio's own project documents
(``engine.studio_project.Project``), its own AI host and live-session bridge (``engine.studio_ai.StudioAIHost``,
``engine.editor.live_session_bridge``), drained as Studio's update drains them, the project owned first as
``engine.studio.open_studio`` owns it. ``real``: Mesh Studio itself, in a hidden window (``open_studio``; needs a GL
context). ``nobridge``: started with its live session turned off: it holds the project, with no bridge and no
session record (for ``real``, the test starts this process with ``MESH_STUDIO_NO_AI_BRIDGE`` set, as a person would
start Mesh Studio; this process writes no environment variable itself).

Commands are files in the folder COMMANDS, taken in order: ``0001.cmd``, ``0002.cmd``, ... (written whole, then
renamed into place). Not stdin: on Windows a thread waiting on stdin stalls imports made meanwhile. It answers one
JSON line on stdout for each:

    (on starting)  {"ready": true, "session_id": ..., "pid": ...}
                   or {"ready": false, "refused": "<the reason, as Studio says it>"}, and exits with code 3
    edit NAME      an unsaved edit: a person named NAME placed in the room
    state          {"names": [...], "unsaved": bool, "pending": [titles], "session_id": ...}
    accept         accept the first proposal waiting
    save           save, as Studio's Save
    room PATH      go to the room whose file is PATH (Studio's room switch, ``real``)
    ctrl_s         press Ctrl+S in Studio's window (``real`` only: Studio's own save, as the person saves):
                   {"message": what Studio says, "ok": bool, "unsaved": bool, "rooms_unsaved": [keys]}
    import_tileset JSON  import a tileset as the person does (``real`` only): the form filled with
                   {"path", "tile", "name"}, then Studio's Import button's action; answers as ``ctrl_s``
    rename ID NAME the person renames object ID to NAME (unsaved)
    undo / redo    as Studio's Undo and Redo: {"done": bool}
    reject         reject the first proposal waiting
    close         close as Studio closes: its session stopped, the project let go, then exit 0

Killed, it ends as a crashed Studio does: nothing is released by its own code.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
ROOM = "packs/core_regions/scenes/start.json"
REFUSALS = ("OwnedElsewhere", "OwnershipUnavailable")


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window: the project as Studio holds it."""

    def __init__(self, project: Any, ownership: Any) -> None:
        self.project, self.ownership = project, ownership
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM))

    def on_ai_proposal(self, proposal: Any) -> None:
        pass

    def on_ai_decided(self, proposal: Any) -> None:
        pass


def _say(**fields: Any) -> None:
    print(json.dumps(fields), flush=True)


class _Windowless:
    """Studio's project, AI host and bridge with no window; the project owned first, as ``open_studio`` owns it."""

    def __init__(self, root: Path, bridge: bool) -> None:
        from engine.studio_ai import StudioAIHost
        from engine.studio_project import Project

        try:
            from engine.editor import project_ownership  # the fix (absent before it: the session then opens as it did)
        except ImportError:
            project_ownership = None  # type: ignore[assignment]
        wait = float(os.environ.get("MESH_TEST_OWNER_WAIT", "2.0"))
        self.held = project_ownership.acquire(root, "mesh_studio", wait=wait) if project_ownership is not None else None
        world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
        self.project = Project(root, world)
        self.host = StudioAIHost(_Studio(self.project, self.held))
        if bridge:
            self.host.start()

    def pump(self) -> None:
        self.host.drain()

    def switch(self, key: str) -> None:
        self.project.current = key

    def ctrl_s(self) -> dict[str, Any]:
        return {"error": "ctrl_s needs Mesh Studio itself (real)"}

    def import_tileset(self, form: dict[str, str]) -> dict[str, Any]:
        return {"error": "import_tileset needs Mesh Studio itself (real)"}

    def close(self) -> None:
        self.host.stop()
        if self.held is not None:
            self.held.release()


class _Real:
    """Mesh Studio itself in a hidden window (``tooling/hd2d_studio_demo.StudioDriver``: ``open_studio``)."""

    def __init__(self, root: Path, bridge: bool) -> None:
        sys.path.insert(1, str(REPO / "tooling"))
        assert bridge is not bool(os.environ.get("MESH_STUDIO_NO_AI_BRIDGE")), "the test starts it with the variable to match"
        from hd2d_studio_demo import StudioDriver

        self.driver = StudioDriver(root)
        self.project, self.host = self.driver.studio.project, self.driver.studio.ai

    def pump(self) -> None:
        self.driver.advance()  # (Studio's own update: it drains its AI host)

    def switch(self, key: str) -> None:
        self.driver.studio.switch_room(key)
        self.driver.advance()

    def ctrl_s(self) -> dict[str, Any]:
        k = self.driver.arcade.key
        self.driver.key(k.S, k.MOD_CTRL)  # (the window's own key event: Studio's on_key_press, then Studio.save)
        studio = self.driver.studio
        return {"message": studio.message, "ok": bool(studio.message_ok)}

    def import_tileset(self, form: dict[str, str]) -> dict[str, Any]:
        studio = self.driver.studio
        studio.open_import()  # (the Import tileset panel, as the menu opens it)
        studio._set_import_path(form["path"])
        studio._set_import_tile(form["tile"])
        studio.import_form["name"] = form["name"]
        studio.import_tileset()  # (the panel's Import button)
        self.driver.advance()
        return {"message": studio.message, "ok": bool(studio.message_ok), "panel": studio.panel}

    def close(self) -> None:
        self.driver.close()  # (the window closes: Studio's session stops and the project is let go)


def main() -> int:
    from engine import authoring

    root, commands = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    flags = sys.argv[3:]
    wait_for = os.environ.get("MESH_TEST_START_GATE")  # (several started at once: all wait for this file, then race)
    while wait_for and not Path(wait_for).exists():
        time.sleep(0.005)
    try:
        session: Any = (_Real if "real" in flags else _Windowless)(root, "nobridge" not in flags)
    except Exception as exc:  # noqa: BLE001  # REASON: whatever refuses the session is reported as the reason; the test reads it
        if type(exc).__name__ not in REFUSALS:
            raise
        _say(ready=False, refused=str(exc))
        return 3
    host, project = session.host, session.project
    session_id = host.bridge.session_id if host.bridge is not None else None
    _say(ready=True, session_id=session_id, pid=os.getpid())
    taken = 0
    while True:
        session.pump()
        waiting = commands / f"{taken + 1:04d}.cmd"
        if not waiting.is_file():
            if not commands.is_dir():
                return 0  # (the test's folder is gone: the test is over)
            time.sleep(0.01)
            continue
        taken += 1
        command, _, argument = waiting.read_text(encoding="utf-8").strip().partition(" ")
        if command == "edit":
            authoring.apply(project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64},
                                      {"op": "rename_entity", "entity_id": "@0", "name": argument}])
            _say(ok=True)
        elif command == "rename":  # (R1) rename ENTITY_ID NAME: the person renames an object
            entity_id, _, name = argument.partition(" ")
            authoring.apply(project, [{"op": "rename_entity", "entity_id": entity_id, "name": name}])
            _say(ok=True)
        elif command in ("undo", "redo"):  # (R1) as Studio's Undo and Redo
            _say(done=bool(getattr(project, command)()))
        elif command == "reject":  # (R1) the person rejects the first proposal waiting
            waiting = host.pending()
            _say(result=host.reject_proposal(waiting[0]) if waiting else None)
        elif command == "state":
            _say(names=[str(e.get("name")) for e in project.scene()["entities"]], unsaved=bool(project.is_dirty),
                 pending=[p.title for p in host.pending()], session_id=session_id)
        elif command == "accept":
            waiting = host.pending()
            _say(result=host.accept(waiting[0]) if waiting else None)
        elif command == "save":
            try:
                _say(saved=project.save())
            except Exception as exc:  # noqa: BLE001  # REASON: a failed save is the answer the test asked for
                _say(saved=None, error=f"{type(exc).__name__}: {exc}")
        elif command == "room":  # room PATH: the person goes to that room
            key = next(k for k, _label, path in project.rooms() if path.replace("\\", "/") == argument)
            session.switch(key)
            _say(room=project.current)
        elif command == "import_tileset":
            _say(**session.import_tileset(json.loads(argument)), unsaved=bool(project.is_dirty))
        elif command == "ctrl_s":
            _say(**session.ctrl_s(), unsaved=bool(project.is_dirty), rooms_unsaved=sorted(project.dirty))
        elif command == "close":
            session.close()
            _say(closed=True)
            return 0
        else:
            _say(error=f"unknown command {command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
