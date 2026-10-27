"""#390: the saved world. Real saves (made by a hidden-window game through the engine's SaveManager) restore the
player's progress while the game's authored world stays authoritative: a room re-sculpted, re-scattered or given a
new wind after the save shows its new self; objects added since appear, objects deleted since don't, objects play
removed stay removed; the player's place, flags, variables and objects' inner states are restored. Saves made before
the change (committed fixtures, written by the engine before it) still load the same way. GL-gated: MESH_GL_SMOKE=1.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
FIXTURES = REPO / "tests" / "fixtures" / "saved_world"


def _edit_room(project: Path, change: Any) -> None:
    import saved_world_fixtures as fx

    path = project / fx.ROOM
    path.write_text(json.dumps(change(json.loads(path.read_text(encoding="utf-8"))), indent=2), encoding="utf-8")


def _load(project: Path, slot: str = "slot1") -> Any:
    """A hidden game that loads ``slot`` as a player's Continue would; returns it (close it)."""
    import saved_world_fixtures as fx
    from hd2d_demo import HiddenGame

    game = HiddenGame(project)
    game.load(fx.ROOM)
    game.step(2)
    assert game.window.save_manager.load_game(slot)
    game.step(4)
    return game


def _ids(game: Any) -> set[str]:
    return {str((getattr(s, "mesh_entity_data", None) or {}).get("id")) for s in game.window.scene_controller.all_sprites}


def _saved_player(save: dict) -> tuple[float, float]:
    player = next(e for e in save["entities"] if e.get("prefab_id") == "player")
    return float(player["x"]), float(player["y"])


@pytest.mark.parametrize("kind", ["hd2d", "2d"])
def test_a_save_from_before_the_change_loads_with_the_room_as_it_is_now(tmp_path: Path, kind: str) -> None:
    import saved_world_fixtures as fx

    from engine import project_ops as ops

    project = fx.build_project(tmp_path / kind, kind)
    fixture = FIXTURES / f"pre390_{kind}.json"
    old = json.loads(fixture.read_text(encoding="utf-8"))
    (project / "saves").mkdir(exist_ok=True)
    shutil.copyfile(fixture, project / "saves" / "slot1.json")
    if kind == "hd2d":  # (since the save: the ground re-sculpted, the scatter cleared, a new wind)
        _edit_room(project, lambda s: ops.set_wind(ops.clear_scatter(ops.sculpt_terrain(s, "raise", 520, 220, 128, 64)),
                                                   speed=12, direction=180))
    game = _load(project)
    try:
        player = fx.player_of(game)
        assert (round(player.center_x), round(player.center_y)) == tuple(round(v) for v in _saved_player(old))
        state = game.window.game_state_controller
        assert state.get_flag("met_the_elder") and state.get_var("coins") == 7
        assert fx.GONE[kind] not in _ids(game)  # (removed by play: still gone)
        if kind == "hd2d":
            hd = game.window.hd2d_renderer
            assert hd is not None and (hd.scatter is None or hd.scatter.count() == 0)  # (the room's: cleared since)
            assert hd.wind.speed == 12.0  # (the room's new wind, not the save's 4 m/s)
            assert hd.terrain is not None and hd.terrain.height(520, 220) > 64  # (the room's new ground)
    finally:
        game.close()


def test_a_new_save_is_small_and_follows_the_room_after_edits(tmp_path: Path) -> None:
    import saved_world_fixtures as fx

    from engine import project_ops as ops

    project = fx.build_project(tmp_path / "hd2d", "hd2d")
    save_path = fx.play_and_save(project, "hd2d")
    save = json.loads(save_path.read_text(encoding="utf-8"))
    old_size = (FIXTURES / "pre390_hd2d.json").stat().st_size
    assert "hd2d" not in json.dumps(save.get("settings")) and save_path.stat().st_size < old_size / 2
    assert "start_mara" in save["meta"]["room_entity_ids"]

    def since(scene: dict) -> dict:  # (after the save: Mara deleted, a new villager placed, the ground raised)
        scene = dict(scene)
        scene["entities"] = [e for e in scene["entities"] if e.get("id") != "start_mara"]
        scene, _new = ops.place_blank(scene, "start", "Newcomer", 300, 200)
        return ops.sculpt_terrain(scene, "raise", 600, 300, 96, 48)

    _edit_room(project, since)
    game = _load(project)
    try:
        ids = _ids(game)
        assert "start_mara" not in ids  # (deleted from the room since: not brought back by the save)
        assert any(i.startswith("start_newcomer") or "newcomer" in i.lower() for i in ids)  # (added since)
        assert fx.GONE["hd2d"] not in ids and "start_elder" in ids
        player = fx.player_of(game)
        assert (round(player.center_x), round(player.center_y)) == tuple(round(v) for v in _saved_player(save))
        hd = game.window.hd2d_renderer
        assert hd is not None and hd.scatter is not None and hd.scatter.count() == sum(
            len(v) for v in json.loads((project / fx.ROOM).read_text(encoding="utf-8"))["settings"]["hd2d"]["scatter"].values())
        assert hd.terrain.height(600, 300) > 40
        assert game.window.game_state_controller.get_flag("met_the_elder")
    finally:
        game.close()


def test_a_save_whose_room_is_gone_loads_its_own_copy(tmp_path: Path) -> None:
    import saved_world_fixtures as fx

    project = fx.build_project(tmp_path / "hd2d", "hd2d")
    (project / "saves").mkdir(exist_ok=True)
    shutil.copyfile(FIXTURES / "pre390_hd2d.json", project / "saves" / "slot1.json")
    game = _load(project)  # (the room, loaded first, then deleted: the save names a room that is gone)
    try:
        (project / fx.ROOM).unlink()
        assert game.window.save_manager.load_game("slot1")
        game.step(4)
        hd = game.window.hd2d_renderer
        assert hd is not None and hd.scatter is not None and hd.scatter.count() > 0  # (the save's own copy)
        assert game.window.game_state_controller.get_var("coins") == 7
    finally:
        game.close()
