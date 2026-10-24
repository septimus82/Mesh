"""A room exactly as the game draws it, rendered in a hidden window: no mouse, no keyboard, no focus taken.

The real GameWindow (its window forced hidden in this process only) loads the room through the real scene loader,
runs the game for a moment (past the room's fade-in), draws one frame and saves it. For visual checks that must not
take over the owner's desktop.

    py -3.13 tooling/scene_snapshot.py PROJECT_DIR SCENE_PATH OUT.png [--player X Y] [--seconds 2]

SCENE_PATH is relative to PROJECT_DIR (as the world file lists it). Set MESH_USER_DIR / MESH_PROJECTS_DIR to keep
the run's recent-projects list out of the owner's.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def snapshot(project: Path, scene_path: str, out: Path, *, player: tuple[float, float] | None = None,
             seconds: float = 2.0, size: tuple[int, int] = (960, 540), studio: bool = False,
             select: str | None = None, tab: str | None = None) -> dict[str, Any]:
    """Render the room (as the game, or in Mesh Studio's edit view with ``studio``, optionally with the object
    named ``select`` selected and its inspector on ``tab``); returns what was drawn beside the saved picture."""
    import engine.optional_arcade as optional_arcade  # first: DPI-unaware, as the engine runs

    arcade = optional_arcade.arcade
    original_init = arcade.Window.__init__

    def hidden_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["visible"] = False  # never shown: nothing on the owner's screen, no focus taken
        original_init(self, *args, **kwargs)

    arcade.Window.__init__ = hidden_init
    os.chdir(project)
    from engine.config import load_config
    from engine.game import GameWindow

    config = load_config(str(project / "config.json"))
    window = GameWindow(width=size[0], height=size[1], title="Mesh snapshot", vsync=False, config=config,
                        config_path=str(project / "config.json"))
    try:
        window.load_scene(scene_path)
        editor = None
        if studio:
            from engine.studio import open_studio

            editor = open_studio(window, project, getattr(config, "world_file", None), scene_path)
            if editor is not None and select:
                found = next((e for e in editor.project.scene().get("entities", []) if e.get("name") == select), None)
                if found is not None:
                    editor.select(found["id"])
                    if tab:
                        editor.tab = tab
                    editor._rebuild()
        sprites = list(window.scene_controller.all_sprites)
        if player is not None:
            for sprite in sprites:
                if (getattr(sprite, "mesh_entity_data", None) or {}).get("tag") == "player":
                    sprite.center_x, sprite.center_y = player
        # Through the event stack (the Studio, when open, handles them first), run now: pyglet otherwise queues
        # events for its own loop, which never runs here.
        window._allow_dispatch_event = True
        for _ in range(int(seconds * 60)):
            window.dispatch_event("on_update", 1 / 60)
        window.dispatch_event("on_draw")
        image = arcade.get_image(0, 0, *size)
        out.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(out)
        lighting = getattr(window, "lighting", None)
        from engine.sprite_shadow_model import compute_sprite_multi_shadow

        drawn = [s for s in window.scene_controller.all_sprites if s.visible and getattr(s, "mesh_drawn", True)]
        return {"sprites": [{"name": getattr(s, "mesh_name", None), "visible": bool(s.visible), "drawn": s in drawn,
                             "ground_shadow": s in drawn and compute_sprite_multi_shadow(s) is not None,
                             "at": [round(s.center_x, 1), round(s.center_y, 1)]} for s in window.scene_controller.all_sprites],
                "lighting": dict(getattr(lighting, "_last_lighting_stats", None) or {}),
                "camera": [round(c, 1) for c in window.camera.position], "zoom": float(window.camera.zoom)}
    finally:
        window.close()
        arcade.Window.__init__ = original_init


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", type=Path)
    parser.add_argument("scene")
    parser.add_argument("out", type=Path)
    parser.add_argument("--player", type=float, nargs=2)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--studio", action="store_true", help="Mesh Studio's edit view instead of the game")
    parser.add_argument("--select", help="with --studio: the object (by name) to select")
    parser.add_argument("--tab", help="with --select: the inspector tab (look, behaviours, ...)")
    parser.add_argument("--size", type=int, nargs=2, default=(960, 540), help="window size (Mesh Studio: 1280 720)")
    args = parser.parse_args()
    import json

    print(json.dumps(snapshot(args.project.resolve(), args.scene, args.out.resolve(),
                              player=tuple(args.player) if args.player else None, seconds=args.seconds,
                              studio=args.studio, select=args.select, tab=args.tab, size=tuple(args.size)),
                     indent=1, default=str))
