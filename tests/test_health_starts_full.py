"""#651: Health the author didn't give a starting value starts full; the player's Health and Combat use its stats.

Three causes, each covered here through the real entry points:
1. ``project_ops.add_behaviour`` (Mesh Studio, ``mesh author``, MCP) wrote Health ``hp``/``max_hp`` and Combat
   ``damage`` defaults into the file. It writes none of ``project_ops.DERIVED_WHEN_UNSET`` now.
2. The scene factory builds behaviours from a config with every default filled in, so every setting counted as the
   author's (``_explicit_params``). Only the keys the author wrote count now (``base.AUTHORED_PARAMS``).
3. Health read max_hp from its (filled) config before the player's stats. It reads the stats unless the author set it.

A generated project (``mesh new``), authored through Studio's project model and ops, ``mesh author apply`` and MCP
``apply_ops``, plus a creator's hand-written configs, played in a real hidden GameWindow (``run_game``). Files the old
tools wrote keep their explicit values (owner decision D12): ``mesh doctor`` flags them, tests/test_doctor_health_defaults.py.
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
PICTURE = "assets/sprites/starter_sign.png"


def _mesh(argv: list[str]) -> tuple[int, str]:
    from mesh_cli.main import main as mesh

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = mesh(argv)
    return code, out.getvalue()


def _author(root: Path) -> None:
    """A "Health 50" enemy by each tool, the player given Health and Combat in Studio, and hand-written configs."""
    from engine import project_ops as ops
    from engine.editor import project_ownership
    from engine.mcp_server import tools
    from engine.studio_project import Project

    start = json.loads((root / ROOM).read_text(encoding="utf-8"))
    player = ops.legacy_player(start) or next(e for e in start["entities"] if "player" in str(e.get("id")))
    px, py = float(player["x"]), float(player["y"])
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    with project_ownership.acquire(root, project_ownership.STUDIO) as held:  # Studio: its project model and ops
        project = Project.open(root, world)
        made: dict[str, str] = {}

        def place(scene: dict[str, Any]) -> dict[str, Any]:
            scene, made["id"] = ops.place_blank(scene, project.current, "WolfS", px + 200, py)
            return scene

        project.edit_scene(place)
        wolf = made["id"]
        project.edit_scene(lambda s: ops.set_picture(s, wolf, PICTURE))
        project.edit_scene(lambda s: ops.add_behaviour(s, wolf, "Health"))  # the picker's "Has health"
        project.edit_scene(lambda s: ops.set_behaviour_param(s, wolf, "Health", "max_hp", 50))  # its "Health"
        project.edit_scene(lambda s: ops.add_behaviour(s, player["id"], "Health"))
        project.edit_scene(lambda s: ops.add_behaviour(s, player["id"], "Combat"))
        project.save(owner=held)
    changes = [
        {"op": "place_blank", "room": "start", "name": "WolfA", "x": px + 200, "y": py + 160},
        {"op": "set_picture", "room": "start", "entity_id": "@0", "sprite": PICTURE},
        {"op": "add_behaviour", "room": "start", "entity_id": "@0", "behaviour": "Health"},
        {"op": "set_behaviour_param", "room": "start", "entity_id": "@0", "behaviour": "Health", "param": "max_hp",
         "value": 50},
        {"op": "place_blank", "room": "start", "name": "WolfM", "x": px + 200, "y": py + 320},
        {"op": "set_picture", "room": "start", "entity_id": "@4", "sprite": PICTURE},
    ]
    (root.parent / "changes.json").write_text(json.dumps(changes), encoding="utf-8")
    code, out = _mesh(["author", "apply", str(root.parent / "changes.json"), "--project", str(root)])
    assert code == 0 and json.loads(out)["ok"], out
    result = tools.apply_ops(operations=[{"type": "set_behaviour_params", "scene_path": ROOM, "entity_id": "WolfM",
                                          "behaviour_name": "Health", "params": {"max_hp": 50}}], root=str(root))
    assert result.get("ok"), result
    doc = json.loads((root / ROOM).read_text(encoding="utf-8"))
    doc["entities"] += [  # a creator's own, by hand: a partial config, and an explicit start below full
        {"id": "bear", "name": "Bear", "x": px + 400, "y": py, "sprite": PICTURE, "tag": "enemy",
         "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 50}}},
        {"id": "elk", "name": "Elk", "x": px + 400, "y": py + 160, "sprite": PICTURE, "tag": "enemy",
         "behaviours": ["Health"], "behaviour_config": {"Health": {"hp": 10, "max_hp": 50}}},
    ]
    (root / ROOM).write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_camera_follow_built_by_the_factory_keeps_its_filled_defaults() -> None:
    """The other "not set" readers keep what the factory always gave them: CameraFollow's unset zoom is 1.0 (never the
    scene's or the entity's), follow_strength doesn't replace lerp_factor; LightSource's unset flicker_seed is None."""
    from types import SimpleNamespace

    from engine.behaviours import load_builtin_behaviours
    from engine.behaviours.registry import create_behaviour

    load_builtin_behaviours()
    entity = SimpleNamespace(mesh_entity_data={"zoom": 2.0}, mesh_tag="player", center_x=0.0, center_y=0.0)
    window = SimpleNamespace(engine_config=None, lighting=None)
    camera = create_behaviour("CameraFollow", entity, window, config={"follow_strength": 9.0})
    assert (camera.zoom_target, camera.lerp_factor) == (1.0, 5.0)
    light = create_behaviour("LightSource", entity, window, config={"flicker_enabled": True})
    assert light._legacy_flicker_seed_value() is None


def _states(node: Any) -> list[dict[str, Any]]:
    """Every saved Health state in a save file (dicts holding hp and max_hp)."""
    if isinstance(node, dict):
        found = [node] if {"hp", "max_hp"} <= node.keys() else []
        return found + [s for v in node.values() for s in _states(v)]
    return [s for v in node for s in _states(v)] if isinstance(node, list) else []


@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_tool_authored_health_starts_full_and_the_player_uses_its_stats(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import project_ops as ops
    from engine.game import GameWindow
    from engine.public_api import run_game

    code, _ = _mesh(["new", "game", "--template", "blank", "--dest", str(tmp_path)])
    root = (tmp_path / "game").resolve()
    assert code == 0
    _author(root)

    room = {e.get("name"): e for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]}
    for name in ("WolfS", "WolfA", "WolfM"):  # cause 1: only what the author set (and invulnerable's default)
        assert room[name]["behaviour_config"]["Health"] == {"max_hp": 50.0, "invulnerable": False}, name
    prefabs = json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8"))
    shared = next(p["entity"] for p in prefabs if p.get("id") == ops.PLAYER_PREFAB)["behaviour_config"]
    assert shared["Health"] == {"invulnerable": False} and "damage" not in shared["Combat"], shared

    seen: dict[str, Any] = {}

    def play(window: Any, phase: str) -> None:  # (in place of window.run())
        try:
            sc = window.scene_controller

            def health(name: str) -> Any:
                sprite = next((s for s in sc.all_sprites if getattr(s, "mesh_name", "") == name), None)
                return next((b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Health"), None) \
                    if sprite is not None else None

            hero = sc._find_player_sprite()
            behaviours = {type(b).__name__: b for b in hero.mesh_behaviours_runtime}
            seen[phase] = {"stats": window.game_state_controller.get_player_stats(),
                           "player": (behaviours["Health"].hp, behaviours["Health"].max_hp),
                           "damage": behaviours["Combat"].damage,
                           "hp": {n: (health(n).hp, health(n).max_hp) for n in ("WolfS", "WolfA", "WolfM", "Bear", "Elk")}}
            if phase == "first":
                for name in ("WolfS", "WolfA", "WolfM", "Bear"):
                    health(name).apply_damage(1.0, source_entity="player")
                for _ in range(5):
                    window.dispatch_event("on_update", 1 / 60)
                seen["after_one_damage"] = {n: health(n).hp if health(n) else None
                                            for n in ("WolfS", "WolfA", "WolfM", "Bear")}
                assert window.save_manager.save_game("quicksave")
                seen["save"] = Path(window.save_manager.save_dir) / "quicksave.json"
            else:
                assert window.save_manager.load_game("quicksave")
                player = next(b for b in sc._find_player_sprite().mesh_behaviours_runtime
                              if type(b).__name__ == "Health")
                seen["loaded"] = {"player": (player.hp, player.max_hp), "WolfS": (health("WolfS").hp, health("WolfS").max_hp)}
        finally:
            dispose_game_window(window)

    monkeypatch.setattr(GameWindow, "run", lambda self: play(self, "first"))
    run_game(ROOM, project_root=root)
    first = seen["first"]
    stats_hp, stats_attack = float(first["stats"]["max_hp"]), float(first["stats"]["attack"])
    assert stats_hp > 1 and stats_attack > 1, first["stats"]
    assert first["player"] == (stats_hp, stats_hp), "cause 3: the player's Health takes max_hp from its stats"
    assert first["damage"] == stats_attack, "cause 2: the player's Combat deals its stats' attack"
    assert first["hp"] == {"WolfS": (50.0, 50.0), "WolfA": (50.0, 50.0), "WolfM": (50.0, 50.0),  # causes 1 and 2
                           "Bear": (50.0, 50.0),  # cause 2: a hand-written {"max_hp": 50}
                           "Elk": (10.0, 50.0)}  # an explicit start is the author's
    assert seen["after_one_damage"] == {"WolfS": 49.0, "WolfA": 49.0, "WolfM": 49.0, "Bear": 49.0}

    # A save from before the fix: its Health states are what they were (1 of 1, 1 of 50), and they load as saved.
    save = json.loads(seen["save"].read_text(encoding="utf-8"))
    states = _states(save)
    assert states, "the save holds Health states"
    for state in states:
        state["hp"] = 1.0
        state["max_hp"] = 1.0 if state["max_hp"] == stats_hp else state["max_hp"]
    seen["save"].write_text(json.dumps(save), encoding="utf-8")
    monkeypatch.setattr(GameWindow, "run", lambda self: play(self, "second"))
    run_game(ROOM, project_root=root)
    assert seen["loaded"] == {"player": (1.0, 1.0), "WolfS": (1.0, 50.0)}, "an old save loads as it was saved"
