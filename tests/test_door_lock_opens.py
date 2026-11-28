"""#639a: an unlocked "Locked until an event" door lets the player through and shows its open picture; the "Button"
shows its used picture.

DoorLock used to write ``entity.properties["solid"]``, which nothing reads: solidity is membership of
``scene_controller.solid_sprites``. Its "Picture when open" and the Button's "Picture once used" were never applied.

A generated project (``mesh new``) authored through Mesh Studio's project model and ops (the picker's "Button" and
"Locked until an event", the inspector's solid), played in a real hidden GameWindow (``run_game``): the interact key's
``perform_interaction`` and the player walking through the game's own update (PlayerController's mover).
The persistence half (#639b: the unlock and an "Only once" press surviving re-entry and save/load) is not here.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window

pytestmark = pytest.mark.integration  # (a generated project in a temporary folder; a hidden game window)

ROOM = "packs/core_regions/scenes/start.json"
BUTTON, USED = "assets/sprites/starter_sign.png", "assets/sprites/starter_villager.png"
DOOR, OPEN = "assets/sprites/door.png", "assets/sprites/starter_sign.png"
SOUTH_ROW = 220.0  # (px below the player's row: the starts-unlocked door is off the gate's path)


def _author(root: Path) -> None:
    """East of the player on its row: a solid gate locked until "gate_open", with the Button that sends it just before
    the gate. On a row of its own further south: a solid door that starts unlocked (its open picture's file missing)."""
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.studio_project import Project
    from mesh_cli.main import main as mesh

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert mesh(["new", "game", "--template", "blank", "--dest", str(root.parent)]) == 0
    start = json.loads((root / ROOM).read_text(encoding="utf-8"))
    player = ops.legacy_player(start) or next(e for e in start["entities"] if "player" in str(e.get("id")))
    px, py = float(player["x"]), float(player["y"])
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:
        project = Project.open(root, world)

        def place(name: str, x: float, y: float) -> str:
            made: dict[str, str] = {}

            def edit(scene: dict[str, Any]) -> dict[str, Any]:
                scene, made["id"] = ops.place_blank(scene, project.current, name, x, y)
                return scene

            project.edit_scene(edit)
            return made["id"]

        def door(name: str, x: float, y: float, *, starts_locked: bool, open_picture: str) -> None:
            ident = place(name, x, y)
            project.edit_scene(lambda s: ops.set_picture(s, ident, DOOR))
            project.edit_scene(lambda s: ops.add_behaviour(s, ident, "DoorLock"))  # "Locked until an event"
            project.edit_scene(lambda s: ops.set_behaviour_param(s, ident, "DoorLock", "unlock_event", "gate_open"))
            project.edit_scene(lambda s: ops.set_behaviour_param(s, ident, "DoorLock", "starts_locked", starts_locked))
            project.edit_scene(lambda s: ops.set_behaviour_param(s, ident, "DoorLock", "open_sprite", open_picture))
            project.edit_scene(lambda s: ops.set_solid(s, ident, True))

        door("Gate", px + 330, py, starts_locked=True, open_picture=OPEN)
        door("Open door", px + 130, py + SOUTH_ROW, starts_locked=False, open_picture="assets/sprites/missing.png")
        button = place("Button", px + 285, py + 30)
        project.edit_scene(lambda s: ops.set_picture(s, button, BUTTON))
        project.edit_scene(lambda s: ops.add_behaviour(s, button, "SwitchInteract"))  # "Button"
        project.edit_scene(lambda s: ops.set_behaviour_param(s, button, "SwitchInteract", "event_id", "gate_open"))
        project.edit_scene(lambda s: ops.set_behaviour_param(s, button, "SwitchInteract", "one_shot", True))
        project.edit_scene(lambda s: ops.set_behaviour_param(s, button, "SwitchInteract", "active_sprite", USED))
        project.save(owner=held)


@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_a_pressed_button_opens_its_gate_and_both_show_their_pictures(tmp_path: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.game import GameWindow
    from engine.interaction import perform_interaction
    from engine.public_api import run_game

    root = (tmp_path / "game").resolve()
    _author(root)
    seen: dict[str, Any] = {}

    def play(window: Any) -> None:  # (in place of window.run())
        try:
            key = optional_arcade.arcade.key
            sc = window.scene_controller
            window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
            menu = getattr(window, "main_menu_overlay", None)
            if menu is not None and menu.visible:
                menu.close()
            named = {getattr(s, "mesh_name", ""): s for s in sc.all_sprites}
            hero, opened, gate, button = sc._find_player_sprite(), named["Open door"], named["Gate"], named["Button"]
            door_picture = opened.texture
            seen["at_load"] = {"gate solid": gate in sc.solid_sprites, "open door solid": opened in sc.solid_sprites}

            def walk_east(frames: int) -> None:
                window.dispatch_event("on_key_press", key.D, 0)
                for _ in range(frames):
                    window.dispatch_event("on_update", 1 / 60)
                window.dispatch_event("on_key_release", key.D, 0)
                window.dispatch_event("on_update", 1 / 60)

            start = (hero.center_x, hero.center_y)
            walk_east(150)  # far enough to reach the gate
            stopped_at = hero.center_x
            walk_east(20)
            seen["before"] = {"past gate": hero.left > gate.right, "stuck": hero.center_x == stopped_at,
                              "hero right": hero.right, "gate left": gate.left,
                              "button picture": button.texture is window.assets.get_texture(BUTTON)}
            seen["pressed"] = perform_interaction(window, actor=hero)  # the interact key, next to the button
            walk_east(60)
            seen["after"] = {"past gate": hero.left > gate.right, "gate solid": gate in sc.solid_sprites,
                             "open picture": gate.texture is window.assets.get_texture(OPEN),
                             "used picture": button.texture is window.assets.get_texture(USED),
                             "not placeholders": window.assets.get_texture(OPEN)
                             is not window.assets.get_texture("assets/placeholder.png")}
            hero.center_x, hero.center_y = start[0], start[1] + SOUTH_ROW  # west of the starts-unlocked door
            walk_east(90)
            seen["open door"] = {"walked past": hero.left > opened.right, "solid": opened in sc.solid_sprites,
                                 "picture kept (open picture's file missing)": opened.texture is door_picture}
        finally:
            dispose_game_window(window)

    monkeypatch.setattr(GameWindow, "run", play)
    run_game(ROOM, project_root=root)

    assert seen["at_load"] == {"gate solid": True, "open door solid": True}, "authored solid in Studio"
    before = seen["before"]
    assert not before["past gate"] and before["stuck"], f"the locked gate stops the player: {before}"
    assert before["button picture"], "the button shows its own picture until used"
    assert seen["pressed"] is True, "the interact key used the button"
    assert seen["after"] == {"past gate": True, "gate solid": False, "open picture": True, "used picture": True,
                             "not placeholders": True}, seen["after"]
    assert seen["open door"] == {"walked past": True, "solid": False,
                                 "picture kept (open picture's file missing)": True}, "starts_locked: false never blocks"
