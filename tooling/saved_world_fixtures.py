"""Saved games made by a real engine run (#390: the saved world): the projects, the play, the save.

    py -3.13 tooling/saved_world_fixtures.py OUT_DIR     # writes OUT_DIR/{hd2d,2d}_slot.json (hidden windows only)

``build_project`` makes a project deterministically from a template: the HD-2D one with sculpted ground, scatter,
a wind and animation (what a save used to copy whole), the 2D one as the starter. ``play_and_save`` plays it in a
hidden window: the player walks, a flag and a variable are set, an authored object (the HD-2D Sign; the 2D Guide) is
removed as if collected, and the game is saved to a slot by the engine's own ``SaveManager``.

The committed fixtures (``tests/fixtures/saved_world/pre390_*.json``) were written by this script on the engine
before #390's change: saves in the old format, to prove they still load.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
ROOM = "packs/core_regions/scenes/start.json"
GONE = {"hd2d": "start_welcome_sign", "2d": "start_guide_320_128_0_0"}  # (removed during play: room memory)


def build_project(root: Path, kind: str) -> Path:
    """A project from the template, its start room as a creator might have built it."""
    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    if root.exists():
        shutil.rmtree(root)
    create_project(root, "Saved world", "hd2d_rpg" if kind == "hd2d" else "starter")
    if kind == "hd2d":
        path = root / ROOM
        scene = json.loads(path.read_text(encoding="utf-8"))
        for x, y in ((420, 160), (520, 220), (600, 300)):
            scene = ops.sculpt_terrain(scene, "raise", x, y, 96, 24)
        scene = ops.set_scatter(scene, {"grass_tuft": [[x, y, (x * 7) % 360, 100] for x in range(380, 700, 24)
                                                       for y in range(120, 360, 40)]})
        scene = ops.set_wind(scene, speed=4, direction=20, gust=0.4)
        scene = ops.set_motion(scene, enabled=True)
        path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return root


def play_and_save(project: Path, kind: str, slot: str = "slot1") -> Path:
    """Play the start room in a hidden window, change what play changes, save to ``slot``. Returns the save file."""
    from hd2d_demo import HiddenGame

    game = HiddenGame(project)
    try:
        game.load(ROOM)
        game.step(10)
        player = game.player()
        player.center_x += 64.0
        player.center_y += 32.0
        game.step(2)
        state = game.window.game_state_controller
        state.set_flag("met_the_elder", True)
        state.set_var("coins", 7)
        gone = next(s for s in game.window.scene_controller.all_sprites
                    if (getattr(s, "mesh_entity_data", None) or {}).get("id") == GONE[kind])
        gone.remove_from_sprite_lists()
        game.step(2)
        manager = game.window.save_manager
        assert manager.save_game(slot), "the engine refused to save"
        return Path(manager.get_save_path(slot)).resolve()
    finally:
        game.close()


def player_of(game: Any) -> Any:
    return next(s for s in game.window.scene_controller.all_sprites if getattr(s, "mesh_tag", None) == "player")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("hd2d", "2d"):
        project = build_project(out / f"project_{kind}", kind)
        save = play_and_save(project, kind)
        shutil.copyfile(save, out / f"{kind}_slot.json")
        print(kind, save.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
