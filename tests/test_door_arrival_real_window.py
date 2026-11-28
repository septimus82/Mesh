"""A player who comes back through a door is never stuck in a wall (found by the final acceptance smoke).

In a real (hidden) GameWindow: two rooms linked through the supported authoring op (``link_rooms``), with a wall tile
where the door's usual arrival spot (96 px below it) would put the player's feet. Walking through the other room's
door, the player arrives clear of every wall and walks back through. And for a door authored before the fix, whose
arrival spot is in the wall, the player can still walk out of it to the door (the movement fix alone). Arriving
inside a whole row of wall tiles, it walks along the row and away from it every way (#764).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine import authoring
from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_project import Project
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

DOOR = (336.0, 304.0)
USUAL_ARRIVAL = (336.0, 208.0)  # 96 px below the door: the feet (y 184..196) in the wall tile y 160..192


def _linked(root: Path) -> tuple[Project, str, str]:
    create_project(root, "Game", template_id="blank")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    start = project.current
    yard = project.add_room("Yard")
    under = ops.cell_at(ops.map_info(project.scene(start)), USUAL_ARRIVAL[0], 176.0)
    authoring.apply(project, [
        {"op": "paint_tiles", "room": start, "layer": ops.WALLS, "cells": [list(under)], "tile": ops.STARTER_WALL},
        {"op": "link_rooms", "key_a": start, "at_a": list(DOOR), "key_b": yard, "at_b": [320.0, 224.0]},
    ])
    return project, start, yard


def _arrival(project: Project, room: str) -> dict:
    return next(e for e in project.scene(room)["entities"] if e.get("tag") == "spawn_point")


def _frames_until(window: Any, done, limit: int = 600) -> bool:
    for _ in range(limit):
        if done():
            return True
        window.on_update(1 / 60)
    return done()


def _room(window: Any) -> str:
    return str(window.scene_controller.current_scene_path or "").replace("\\", "/")


@contextmanager
def _arrived(root: Path, project: Project, start: str, yard: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """A hidden GameWindow whose player has just walked into the yard's door and arrived in the start room."""
    from engine.config import load_config
    from engine.game import GameWindow

    monkeypatch.chdir(root)
    monkeypatch.setenv("MESH_SAVE_DIR", str(root.parent / "saves"))
    config = load_config(str(root / "config.json"))
    config.tour_completed = True
    window = GameWindow(width=640, height=480, title=config.title, vsync=False, config=config)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    sc = window.scene_controller
    try:
        window.load_scene(project.path(yard))
        if window.main_menu_overlay.visible:
            window.main_menu_overlay.close()
        window.on_update(1 / 60)
        door = next(s for s in sc.all_sprites if getattr(s, "mesh_tag", "") == "door")
        player = sc._find_player_sprite()
        player.center_x, player.center_y = door.center_x, door.center_y
        assert _frames_until(window, lambda: _room(window).endswith(project.path(start))), "the yard's door didn't lead back"
        assert _frames_until(window, lambda: (sc._find_player_sprite().center_x, sc._find_player_sprite().center_y)
                             == (_arrival(project, start)["x"], _arrival(project, start)["y"]), 60)
        yield window
    finally:
        dispose_game_window(window)


def _feet_and_walls(window: Any):
    from engine.physics_model import entity_aabb
    from engine.physics_runtime import _sprite_to_aabb

    sc = window.scene_controller
    return entity_aabb(sc._find_player_sprite()), [_sprite_to_aabb(s) for s in sc.solid_sprites]


def _hold(window: Any, key: int, frames: int) -> None:
    window.dispatch_event("on_key_press", key, 0)
    for _ in range(frames):
        window.on_update(1 / 60)
    window.dispatch_event("on_key_release", key, 0)


def _play_back_through_the_door(root: Path, project: Project, start: str, yard: str,
                                monkeypatch: pytest.MonkeyPatch) -> tuple[tuple[float, float], int, bool]:
    """Walk into the yard's door, arrive in the start room, then hold the key toward its door. Returns where the player
    arrived, how many walls its collider overlapped there, and whether it got back to the yard."""
    with _arrived(root, project, start, yard, monkeypatch) as window:
        player = window.scene_controller._find_player_sprite()
        arrived = (player.center_x, player.center_y)
        feet, walls = _feet_and_walls(window)
        in_walls = sum(1 for w in walls if feet.intersection(w))

        dx, dy = DOOR[0] - arrived[0], DOOR[1] - arrived[1]
        key = optional_arcade.arcade.key
        toward = (key.D if dx > 0 else key.A) if abs(dx) > abs(dy) else (key.W if dy > 0 else key.S)
        window.dispatch_event("on_key_press", toward, 0)
        back = _frames_until(window, lambda: _room(window).endswith(project.path(yard)), 300)
        window.dispatch_event("on_key_release", toward, 0)
        return arrived, in_walls, back


def test_arriving_through_a_door_puts_the_player_clear_of_walls_and_it_walks_back(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, start, yard = _linked(tmp_path / "game")
    spot = _arrival(project, start)
    assert (spot["x"], spot["y"]) != USUAL_ARRIVAL, "the arrival spot must avoid the wall under the usual one"
    project.save()

    arrived, in_walls, back = _play_back_through_the_door(tmp_path / "game", project, start, yard, monkeypatch)
    assert arrived == (spot["x"], spot["y"])
    assert in_walls == 0, "the player arrived inside a wall"
    assert back, "the player couldn't walk back through the door"


def test_a_door_authored_with_its_arrival_in_a_wall_still_lets_the_player_walk_out(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, start, yard = _linked(tmp_path / "game")
    authoring.apply(project, [{"op": "move_entity", "room": start, "entity_id": _arrival(project, start)["id"],
                               "x": USUAL_ARRIVAL[0], "y": USUAL_ARRIVAL[1]}])  # as a door made before the fix
    project.save()

    arrived, in_walls, back = _play_back_through_the_door(tmp_path / "game", project, start, yard, monkeypatch)
    assert arrived == USUAL_ARRIVAL and in_walls == 1, "precondition: the feet start in the wall below"
    assert back, "stuck: walking up toward the door must free the player from the wall it stands in"


def test_arriving_inside_a_wall_row_the_player_walks_along_it_and_away_every_way(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A legacy door's arrival spot inside a row of wall tiles (feet 8 px into it): D and A slide along the row's top
    (#764: they used to pin against the next tile), W walks away, and S stops flush on the row, never deeper."""
    project, start, yard = _linked(tmp_path / "game")
    info = ops.map_info(project.scene(start))
    row = [list(ops.cell_at(info, x, 176.0)) for x in range(208, 465, 32)]  # wall tiles x 192..480, y 160..192
    authoring.apply(project, [
        {"op": "paint_tiles", "room": start, "layer": ops.WALLS, "cells": row, "tile": ops.STARTER_WALL},
        {"op": "move_entity", "room": start, "entity_id": _arrival(project, start)["id"],
         "x": USUAL_ARRIVAL[0], "y": USUAL_ARRIVAL[1]},  # as a door made before the arrival fix
    ])
    project.save()

    with _arrived(tmp_path / "game", project, start, yard, monkeypatch) as window:
        player = window.scene_controller._find_player_sprite()
        assert (player.center_x, player.center_y) == USUAL_ARRIVAL
        feet, walls = _feet_and_walls(window)
        assert feet.bottom == pytest.approx(184.0) and any(feet.intersection(w) for w in walls), \
            "precondition: the feet start 8 px into the row"
        key = optional_arcade.arcade.key
        for pressed, axis, sign in ((key.D, 0, 1), (key.A, 0, -1), (key.W, 1, 1), (key.S, 1, -1)):
            player.center_x, player.center_y = USUAL_ARRIVAL
            _hold(window, pressed, 12)
            feet, walls = _feet_and_walls(window)
            assert _room(window).endswith(project.path(start)), "it left the room"
            assert not any(feet.intersection(w) for w in walls), (pressed, feet)
            moved = (player.center_x - USUAL_ARRIVAL[0], player.center_y - USUAL_ARRIVAL[1])
            if pressed == key.S:
                assert moved == (0.0, pytest.approx(8.0)), "into the row: lifted out, then flush on it, never deeper"
            else:
                assert moved[axis] * sign > 10.0, (pressed, moved)
                assert moved[1 - axis] == pytest.approx(8.0 if axis == 0 else 0.0), (pressed, moved)
                if axis == 0:
                    assert feet.bottom == pytest.approx(192.0), "slides along the row's top, flush"
