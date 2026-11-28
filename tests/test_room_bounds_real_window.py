"""In a real (hidden) GameWindow the player can't walk off a 2D room without border walls (round-3 audit #751).

The Lantern Road playtest walked south from the Village's start for good, into black void: only the camera was kept in
the room. A new project's blank room has no walls at all; holding a direction toward each edge for long enough to
cross the room twice, the player's collider ends flush with that edge, the camera's own rectangle. A door placed on
the edge line (half of it outside the room) still takes a player who walks into it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.optional_arcade as optional_arcade
from engine import authoring
from engine.project_scaffold import create_project
from engine.studio_project import Project
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

EDGE_DOOR = (768.0, 240.0)  # the blank room is 24 x 16 tiles of 32 px: 768 x 512; this door straddles its right edge


def _project(root: Path) -> tuple[Project, str, str]:
    create_project(root, "Game", template_id="blank")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    start = project.current
    yard = project.add_room("Yard")
    authoring.apply(project, [{"op": "link_rooms", "key_a": start, "at_a": list(EDGE_DOOR),
                               "key_b": yard, "at_b": [320.0, 224.0]}])
    project.save()
    return project, start, yard


def _window(root: Path, monkeypatch: pytest.MonkeyPatch):
    from engine.config import load_config
    from engine.game import GameWindow

    monkeypatch.chdir(root)
    monkeypatch.setenv("MESH_SAVE_DIR", str(root.parent / "saves"))
    config = load_config(str(root / "config.json"))
    config.tour_completed = True
    window = GameWindow(width=640, height=480, title=config.title, vsync=False, config=config)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    return window


def _hold(window, key: int, frames: int, until=None) -> bool:
    window.dispatch_event("on_key_press", key, 0)
    try:
        for _ in range(frames):
            if until is not None and until():
                return True
            window.on_update(1 / 30)
        return until() if until is not None else False
    finally:
        window.dispatch_event("on_key_release", key, 0)


def test_holding_toward_each_edge_keeps_the_player_inside_flush(tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.physics_model import entity_aabb

    project, start, _ = _project(tmp_path / "game")
    window = _window(tmp_path / "game", monkeypatch)
    try:
        window.load_scene(project.path(start))
        if window.main_menu_overlay.visible:
            window.main_menu_overlay.close()
        window.on_update(1 / 30)
        sc = window.scene_controller
        assert not list(sc.solid_sprites), "precondition: a room with no walls at all"
        rect = window.camera_controller.world_rect()
        assert rect == (0.0, 0.0, 768.0, 512.0), "the camera's rectangle is the map's"
        key = optional_arcade.arcade.key
        for k, edge, expected in ((key.S, "bottom", rect[1]), (key.A, "left", rect[0]),
                                  (key.W, "top", rect[3]), (key.D, "right", rect[2])):
            _hold(window, k, 240)  # 8 s at 150 px/s: 1200 px, more than across the room
            box = entity_aabb(sc._find_player_sprite())
            assert getattr(box, edge) == pytest.approx(expected), f"walked off the {edge} edge: {box}"
        box = entity_aabb(sc._find_player_sprite())
        assert (box.right, box.top) == (pytest.approx(768.0), pytest.approx(512.0)), "in the top-right corner"
    finally:
        dispose_game_window(window)


def test_a_door_on_the_edge_still_takes_the_player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, start, yard = _project(tmp_path / "game")
    window = _window(tmp_path / "game", monkeypatch)
    sc = window.scene_controller
    try:
        window.load_scene(project.path(start))
        if window.main_menu_overlay.visible:
            window.main_menu_overlay.close()
        window.on_update(1 / 30)
        door = next(s for s in sc.all_sprites if getattr(s, "mesh_tag", "") == "door")
        assert door.center_x == EDGE_DOOR[0] and door.right > 768.0, "precondition: the door straddles the edge"
        player = sc._find_player_sprite()
        player.center_x, player.center_y = 600.0, door.center_y
        went = _hold(window, optional_arcade.arcade.key.D, 240,
                     until=lambda: str(sc.current_scene_path or "").replace("\\", "/").endswith(project.path(yard)))
        assert went, "the edge door must still take a player who walks into it"
    finally:
        dispose_game_window(window)
