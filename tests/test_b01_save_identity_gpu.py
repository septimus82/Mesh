"""B-01 on a real GPU context (MESH_GL_SMOKE=1, the gpu lane): saves made by the v2 engine (the committed pre-#390
fixtures, which need a real room: a template project) load with every record bound and every object's state in place,
the first v3 save over such a slot makes a verified backup, and two objects named alike keep their own states through
a save and a load of a template project. The default-lane cycles (tests/test_b01_save_identity.py) use a plain hidden
window; this one runs the engine as a player does (a project, its config, the HD-2D room).
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
IDENTITY_CODES = ("entity_id_ambiguous", "entity_legacy_ambiguous", "entity_nameclash", "entities_unbound",
                  "entities_unresolved")


def _load(project: Path, slot: str = "slot1") -> Any:
    import saved_world_fixtures as fx
    from hd2d_demo import HiddenGame

    game = HiddenGame(project)
    game.load(fx.ROOM)
    game.step(2)
    assert game.window.save_manager.load_game(slot)
    game.step(4)
    return game


def _codes() -> list[str]:
    from engine.save_runtime import io as save_io

    attempt = save_io.get_save_runtime_diagnostics_snapshot()["last_load_attempt"]
    return [str(r.get("code")) for r in attempt["diagnostics"]["diagnostics"]]


@pytest.mark.parametrize("kind", ["hd2d", "2d"])
def test_a_v2_save_from_the_real_engine_binds_every_record_and_is_backed_up_on_its_first_v3_save(
        tmp_path: Path, kind: str) -> None:
    import saved_world_fixtures as fx

    from engine.save_runtime.entity_state import held_unresolved

    project = fx.build_project(tmp_path / kind, kind)
    fixture = FIXTURES / f"pre390_{kind}.json"
    (project / "saves").mkdir(exist_ok=True)
    slot = project / "saves" / "slot1.json"
    shutil.copyfile(fixture, slot)
    original = slot.read_bytes()
    game = _load(project)
    try:
        assert slot.read_bytes() == original  # loading rewrote nothing
        assert not [c for c in _codes() if c.rsplit(".", 1)[-1] in IDENTITY_CODES]
        assert held_unresolved(game.window.scene_controller) == []
        records = json.loads(original)["saved_entities"]["entities"]
        player = fx.player_of(game)
        saved = next(r for r in records if r["entity_id"] == "Player")
        assert (round(player.center_x), round(player.center_y)) == (round(saved["x"]), round(saved["y"]))
        assert game.window.save_manager.save_game("slot1")
        backup = project / "saves" / "slot1.json.v2.bak"
        assert backup.read_bytes() == original
        assert json.loads(slot.read_text(encoding="utf-8"))["save_schema_version"] == 3
    finally:
        game.close()


def test_two_objects_named_alike_keep_their_own_states_in_a_template_project(tmp_path: Path) -> None:
    import saved_world_fixtures as fx

    project = fx.build_project(tmp_path / "twins", "2d")
    room = project / fx.ROOM
    scene = json.loads(room.read_text(encoding="utf-8"))
    for ident, x in (("twin_a", 420), ("twin_b", 520)):
        scene["entities"].append({"id": ident, "name": "Twin", "x": x, "y": 200, "sprite": "assets/placeholder.png",
                                  "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 20, "hp": 20}}})
    room.write_text(json.dumps(scene, indent=2), encoding="utf-8")
    from hd2d_demo import HiddenGame

    game = HiddenGame(project)
    try:
        game.load(fx.ROOM)
        game.step(2)
        sprites = {s.mesh_id: s for s in game.window.scene_controller.all_sprites if getattr(s, "mesh_id", None)}
        for ident, hp in (("twin_a", 3.0), ("twin_b", 17.0)):
            next(b for b in sprites[ident].mesh_behaviours_runtime if type(b).__name__ == "Health").hp = hp
        assert game.window.save_manager.save_game("slot1")
        game.load(fx.ROOM)  # a fresh room
        game.step(2)
        assert game.window.save_manager.load_game("slot1")
        game.step(4)
        hps = {s.mesh_id: next(b for b in s.mesh_behaviours_runtime if type(b).__name__ == "Health").hp
               for s in game.window.scene_controller.all_sprites if getattr(s, "mesh_id", None) in ("twin_a", "twin_b")}
        assert hps == {"twin_a": 3.0, "twin_b": 17.0}
    finally:
        game.close()
