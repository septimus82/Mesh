"""Shared by the S1 evidence scripts: a real, hidden, muted GameWindow over throwaway scene files.

The window never shows and never activates (tooling.hidden_windows.no_activate + visible=False, as tests/conftest.py
does). Scene files and the save folder live in a temp folder that is removed afterwards. The process works from the
checkout root (the engine reads assets/ and data files relative to it); nothing is written there.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.chdir(REPO)

PICTURE = "assets/placeholder.png"
HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 100, "y": 100, "sprite": PICTURE,
        "behaviours": ["PlayerController"]}


def scene(name: str, *entities: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "schema_version": 1, "version": 1, "layers": [], "entities": list(entities)}


@contextlib.contextmanager
def hidden_game(scenes: dict[str, dict[str, Any]]) -> Iterator[tuple[Any, dict[str, str], Path]]:
    """Yield ``(window, {scene name: path}, temp folder)``; the first scene is loaded."""
    from tooling.hidden_windows import no_activate

    no_activate()
    import pyglet.window

    original = pyglet.window.Window.__init__

    def hidden(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["visible"] = False
        original(self, *args, **kwargs)

    pyglet.window.Window.__init__ = hidden  # type: ignore[method-assign]

    import engine
    from engine.config import EngineConfig
    from engine.game import GameWindow
    from engine.save_manager import SaveManager

    print("engine from", Path(engine.__file__).relative_to(REPO.parent).as_posix())
    tmp = Path(tempfile.mkdtemp(prefix="mesh_s1_evidence_"))
    window = None
    try:
        paths = {}
        for name, doc in scenes.items():
            path = tmp / f"{name}.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            paths[name] = str(path)
        cfg = EngineConfig(width=320, height=200, title="S1 evidence", vsync=False, start_scene="", world_file=None,
                           main_menu_scene=None, master_volume=0.0)
        window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
        window.audio.set_master_volume(0.0)
        window.save_manager = SaveManager(window, save_dir=tmp / "saves")
        window.scene_controller.load_scene(paths[next(iter(scenes))])
        yield window, paths, tmp
    finally:
        if window is not None:
            import engine.optional_arcade as optional_arcade

            try:
                window.close()
            finally:
                with contextlib.suppress(Exception):
                    optional_arcade.arcade.close_window()
        pyglet.window.Window.__init__ = original  # type: ignore[method-assign]
        shutil.rmtree(tmp, ignore_errors=True)  # (the temp folder this module created)


def sprite_named(window: Any, name: str) -> Any:
    return next(s for s in window.scene_controller.all_sprites if getattr(s, "mesh_name", "") == name)


def behaviour(sprite: Any, type_name: str) -> Any:
    return next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == type_name)
