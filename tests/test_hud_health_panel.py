"""#643: the player HUD's health panel draws in a real game, and follows damage.

PlayerHUD read ``window.player``, which only test doubles had: the real GameWindow finds its player through
``scene_controller._find_player_sprite()``. So ``_draw_stats`` returned at once every frame and a player with Health
never saw its HP. The debug bundle's HUD snapshot read the same attribute. Both use ``hud_model.find_player`` now.

A generated project (``mesh new``), the player given Health through Studio's project model and ops, played in a real
hidden GameWindow (``run_game``) through the real per-frame update and draw.
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

pytestmark = [pytest.mark.integration,  # (a generated project in a temporary folder; a hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

ROOM = "packs/core_regions/scenes/start.json"
NO_HEALTH_ROOM = "packs/core_regions/scenes/no_health.json"
NO_PLAYER_ROOM = "packs/core_regions/scenes/no_player.json"


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The start room's player has Health (Studio's "Has health"); two copies: without Health, without a player."""
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.studio_project import Project
    from mesh_cli.main import main as mesh

    dest = tmp_path_factory.mktemp("p643")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert mesh(["new", "game", "--template", "blank", "--dest", str(dest)]) == 0
    root = (dest / "game").resolve()
    start = json.loads((root / ROOM).read_text(encoding="utf-8"))
    player = ops.legacy_player(start) or next(e for e in start["entities"] if "player" in str(e.get("id")))
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:
        project = Project.open(root, world)
        project.edit_scene(lambda s: ops.add_behaviour(s, player["id"], "Health"))
        project.save(owner=held)

    doc = json.loads((root / ROOM).read_text(encoding="utf-8"))
    for entity in doc["entities"]:
        entity["behaviours"] = [b for b in entity.get("behaviours") or [] if b != "Health"]
        (entity.get("behaviour_config") or {}).pop("Health", None)
    (root / NO_HEALTH_ROOM).write_text(json.dumps(doc), encoding="utf-8")
    doc["entities"] = [e for e in doc["entities"] if e.get("id") != player["id"]]
    (root / NO_PLAYER_ROOM).write_text(json.dumps(doc), encoding="utf-8")
    return root


def _play(project: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from engine.editor.debug.debug_bundle import _build_hud_snapshot
    from engine.game import GameWindow
    from engine.public_api import run_game

    seen: dict[str, Any] = {}

    def play(window: Any) -> None:  # (in place of window.run())
        try:
            assert not hasattr(window, "player"), "the real window has no 'player' (the scene controller finds it)"
            hud = window.player_hud
            drawn: list[str] = []  # the panel's health and level texts, each time it draws them
            for text in (hud._health_text, hud._level_text):
                monkeypatch.setattr(text, "draw", lambda t=text, d=text.draw: (drawn.append(t.text), d())[1])

            def frame() -> dict[str, Any]:
                drawn.clear()
                window.on_update(1 / 60)
                window.on_draw()  # the real frame draw: PlayerHUD.draw -> _draw_stats
                vm = hud.get_hud_view_model()
                return {"drawn": list(drawn),
                        "vm": None if vm is None else (vm.health_state.hp, vm.health_state.max_hp)}

            sc = window.scene_controller
            frame()
            health = next(b for b in sc._find_player_sprite().mesh_behaviours_runtime if type(b).__name__ == "Health")
            seen["health"] = (health.hp, health.max_hp)
            seen["level"] = int(window.game_state_controller.get_player_stats().get("level", 1))
            seen["full"] = frame()
            seen["bundle_full"] = _build_hud_snapshot(window)["health"]
            health.apply_damage(7)
            seen["health_after"] = (health.hp, health.max_hp)
            seen["hurt"] = frame()
            seen["bundle_hurt"] = _build_hud_snapshot(window)["health"]
            for key, room in (("no_health", NO_HEALTH_ROOM), ("no_player", NO_PLAYER_ROOM)):
                sc.load_scene(str(project / room))
                frame()
                seen[key] = frame()
        finally:
            dispose_game_window(window)

    monkeypatch.setattr(GameWindow, "run", play)
    run_game(ROOM, project_root=project)
    return seen


def test_hud_health_panel_draws_the_players_health_and_follows_damage(project: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _play(project, monkeypatch)
    hp, max_hp = seen["health"]
    assert max_hp > 0 and hp == max_hp, "the player's Health starts full (#651)"
    level = f"Lv {seen['level']}"
    assert seen["full"] == {"drawn": [f"{int(hp)} / {int(max_hp)}", level], "vm": (hp, max_hp)}, "the panel draws"
    assert (seen["bundle_full"]["hp"], seen["bundle_full"]["max_hp"]) == (hp, max_hp), "debug bundle: same player"

    hurt_hp, _ = seen["health_after"]
    assert hurt_hp < hp, "the damage landed"
    assert seen["hurt"] == {"drawn": [f"{int(hurt_hp)} / {int(max_hp)}", level], "vm": (hurt_hp, max_hp)}, \
        "the HP follows"
    assert seen["bundle_hurt"]["hp"] == hurt_hp

    # A player without Health, or no player at all: no health panel, and nothing breaks.
    assert seen["no_health"] == {"drawn": [], "vm": (0.0, 0.0)}
    assert seen["no_player"] == {"drawn": [], "vm": None}
