"""S1-0 part B, triage item T-1 end to end: one MCP edit can stop a project from starting (game AND editor).

1. A new project from the real scaffold (engine.project_scaffold.create_project, template "blank") in a temp folder.
2. The MCP tool function engine.mcp_server.tools.apply_ops with one operation, {"type": "add_cutscene", "id": "intro",
   "steps": [{"type": "fade_to_black"}]} (a plausible step name; the schema's step types are say/wait/move_entity/...).
   The op reports ok; its own validation pass does not look at cutscenes.json.
3. A real, hidden, muted GameWindow constructed the way `mesh play` / `mesh edit` do it: CWD = the project.
   GameWindow.__init__ loads cutscenes.json (engine/game.py:592-595) and catches only FileNotFoundError, so the
   SchemaValidationError escapes the constructor: neither the game nor Studio/the legacy editor can open the project.

Exits 1 when the window constructor raises after an MCP op reported success.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import engine  # noqa: E402

print("engine from", Path(engine.__file__).relative_to(REPO.parent).as_posix())
tmp = Path(tempfile.mkdtemp(prefix="mesh_s1_t1_"))
project = tmp / "Proj"
window = None
raised = None
try:
    from engine.project_scaffold import create_project

    create_project(project, "Proj", "blank")
    from engine.mcp_server.tools import apply_ops

    result = apply_ops([{"type": "add_cutscene", "id": "intro", "steps": [{"type": "fade_to_black"}]}],
                       root=str(project))
    print("MCP apply_ops ok:", result.get("ok"), "| op:", [(r.get("type"), r.get("ok"), r.get("message"))
                                                         for r in result.get("results", [])])
    print("MCP validation ok:", (result.get("validation") or {}).get("ok"))
    print("cutscenes.json now:", json.loads((project / "cutscenes.json").read_text(encoding="utf-8")))

    from tooling.hidden_windows import no_activate

    no_activate()
    import pyglet.window

    original = pyglet.window.Window.__init__

    def hidden(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["visible"] = False
        original(self, *args, **kwargs)

    pyglet.window.Window.__init__ = hidden  # type: ignore[method-assign]
    from engine.config import EngineConfig
    from engine.game import GameWindow

    os.chdir(project)  # as `mesh play` / `mesh edit` (engine/game_launch.py) do
    try:
        cfg = EngineConfig(width=320, height=200, title="S1 T-1", vsync=False, start_scene="", world_file=None,
                           main_menu_scene=None, master_volume=0.0)
        window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    except Exception as exc:  # noqa: BLE001
        raised = exc
    finally:
        os.chdir(REPO)
        pyglet.window.Window.__init__ = original  # type: ignore[method-assign]
    print("GameWindow constructor:", "OK" if raised is None else f"raised {type(raised).__name__}: {str(raised)[:200]}")
finally:
    if window is not None:
        window.close()
    import contextlib

    import engine.optional_arcade as optional_arcade

    with contextlib.suppress(Exception):
        optional_arcade.arcade.close_window()
    shutil.rmtree(tmp, ignore_errors=True)  # (the temp folder this script created)

if raised is not None and result.get("ok"):
    print("DEFECT REPRODUCED: an MCP cutscene edit that reported success makes the project unopenable")
    sys.exit(1)
print("not reproduced")
