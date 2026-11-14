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


def _runtime(game: Any, entity_id: str) -> Any:
    return next(s for s in game.window.scene_controller.all_sprites
                if (getattr(s, "mesh_entity_data", None) or {}).get("id") == entity_id)


def _behaviour(sprite: Any, name: str) -> Any:
    return next((b for b in getattr(sprite, "mesh_behaviours_runtime", []) if type(b).__name__ == name), None)


def test_authored_changes_reach_a_save_and_play_s_state_stays(tmp_path: Path) -> None:
    """After a save, the creator rewrites the Elder's dialogue, repaints a barrel and gives Mara a new behaviour: the
    save shows all three. What play changed stays: the barrel's damage (its Health), where the barrel and the player
    stand, the flag."""
    import saved_world_fixtures as fx
    from hd2d_demo import HiddenGame

    project = fx.build_project(tmp_path / "hd2d", "hd2d")

    def barrel(scene: dict) -> dict:
        scene["entities"].append({"id": "start_barrel", "name": "Barrel", "x": 700.0, "y": 300.0, "layer": "entities",
                                  "sprite": "assets/sprites/starter_sign.png", "behaviours": ["Health"],
                                  "behaviour_config": {"Health": {"max_hp": 10.0, "hp": 10.0}}})
        return scene

    _edit_room(project, barrel)
    game = HiddenGame(project)
    try:
        game.load(fx.ROOM)
        game.step(10)
        cask = _runtime(game, "start_barrel")
        _behaviour(cask, "Health").apply_damage(6.0)
        cask.center_x += 40.0
        fx.player_of(game).center_x += 64.0
        game.window.game_state_controller.set_flag("met_the_elder", True)
        game.step(2)
        at = (round(cask.center_x), round(cask.center_y), round(fx.player_of(game).center_x))
        assert game.window.save_manager.save_game("slot1")
    finally:
        game.close()

    def since(scene: dict) -> dict:
        by = {e.get("id"): e for e in scene["entities"]}
        by["start_elder"]["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["text"] = "New words, after the save."
        by["start_barrel"]["sprite"] = "assets/sprites/hd2d_merchant.png"
        by["start_mara"]["behaviours"] = [*by["start_mara"]["behaviours"], "Health"]
        by["start_mara"].setdefault("behaviour_config", {})["Health"] = {"max_hp": 7.0}
        return scene

    _edit_room(project, since)
    game = _load(project)
    try:
        elder, cask, mara = (_runtime(game, i) for i in ("start_elder", "start_barrel", "start_mara"))
        talk = _behaviour(elder, "Dialogue")
        assert "New words, after the save." in repr((talk._script, talk._graph_nodes))  # (what the Elder says: as now)
        assert cask.mesh_entity_data["sprite"] == "assets/sprites/hd2d_merchant.png"  # (the picture, as authored now)
        assert _behaviour(mara, "Health") is not None and _behaviour(mara, "Health").max_hp == 7.0  # (a new behaviour)
        assert _behaviour(cask, "Health").hp == 4.0  # (play's damage: kept)
        assert (round(cask.center_x), round(cask.center_y), round(fx.player_of(game).center_x)) == at  # (where play left them)
        assert game.window.game_state_controller.get_flag("met_the_elder")
    finally:
        game.close()


def test_a_new_save_whose_room_is_missing_is_refused_and_kept(tmp_path: Path) -> None:
    """A save made since #390 has no copy of its room. With the room gone, loading it is refused clearly, before
    anything changes: the running game stays as it was and the save file is untouched; with the room back, it loads."""
    import saved_world_fixtures as fx

    project = fx.build_project(tmp_path / "hd2d", "hd2d")
    save_path = fx.play_and_save(project, "hd2d")
    before = save_path.read_bytes()
    room = project / fx.ROOM
    game = _load(project)  # (the save loaded once, the room present)
    try:
        held = room.with_name("start.json.away")
        room.rename(held)
        player = fx.player_of(game)
        player.center_x += 96.0
        where = (game.window.scene_controller.current_scene_path, round(player.center_x), round(player.center_y))
        assert game.window.save_manager.load_game("slot1") is False  # (refused)
        game.step(4)
        player = fx.player_of(game)
        assert (game.window.scene_controller.current_scene_path, round(player.center_x), round(player.center_y)) == where
        assert save_path.read_bytes() == before  # (the save: kept as it was)
        held.rename(room)
        assert game.window.save_manager.load_game("slot1")  # (the room back: it loads)
        game.step(4)
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
