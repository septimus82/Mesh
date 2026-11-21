"""GAME-1: a player's game survives save -> full exit -> fresh launch -> load, repeatedly (#462 reliability).

Every numbered step runs in its OWN Python process (tests/_game1_worker.py: a hidden GameWindow, the production
SaveManager, real room and save files); the process exits between steps, so nothing survives but the slot file.
Real v2 saves (the committed fixtures) are loaded and re-saved the same way. GL-gated: MESH_GL_SMOKE=1 (the gpu lane).
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
from tests._game1_worker import FIXTURES, QUEST, prepare_v2_idless, run_step

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _game(state: dict[str, Any]) -> dict[str, Any]:
    """The game's state without the transient toasts."""
    return {k: v for k, v in state.items() if k != "toasts"}


def _sprite(state: dict[str, Any], ident: str | None, name: str | None = None, x: float | None = None) -> dict[str, Any]:
    found = [s for s in state["sprites"] if s["id"] == ident and (name is None or s["name"] == name)
             and (x is None or s["x"] == x)]
    assert len(found) == 1, (ident, name, x, found)
    return found[0]


def _check_first(state: dict[str, Any]) -> None:
    assert _sprite(state, "hero")["hp"] == 4.0 and _sprite(state, "hero")["tag"] == "player"
    assert state["quest"]["status"] == "active" and state["quest"]["completed_stages"] == ["s1"]
    assert state["quest"]["current_stage"] == "s2"
    assert state["inventory"] == {"healing_potion": 3, "rusty_sword": 1}
    assert state["flags"] == {"met_elder": True} and state["coins"] == 7
    gob = _sprite(state, "gob_a")
    assert (gob["x"], gob["y"], gob["hp"]) == (140.0, 160.0, 6.0)
    elder = _sprite(state, "elder")
    assert elder["tag"] == "merchant" and elder["tags"] == ["alpha", "merchant", "vip", "zeta"]
    assert (_sprite(state, "twin_a")["hp"], _sprite(state, "twin_b")["hp"]) == (3.0, 17.0)
    scout = _sprite(state, None, "Scout_7")
    assert (scout["x"], scout["y"], scout["hp"]) == (33.0, 31.0, 5.0)


def _check_second(state: dict[str, Any]) -> None:
    assert _sprite(state, "hero")["hp"] == 2.0
    assert state["quest"]["completed_stages"] == ["s1", "s2"] and state["quest"]["current_stage"] == "s3"
    assert state["inventory"] == {"healing_potion": 4, "rusty_sword": 1}
    gob = _sprite(state, "gob_a")
    assert (gob["x"], gob["y"], gob["hp"]) == (150.0, 170.0, 1.0)
    assert _sprite(state, "elder")["tag"] == "merchant"  # (untouched since the first save: still there)
    assert (_sprite(state, "twin_a")["hp"], _sprite(state, "twin_b")["hp"]) == (3.0, 11.0)
    scout = _sprite(state, None, "Scout_7")
    assert (scout["x"], scout["y"], scout["hp"]) == (35.0, 32.0, 2.0)


def test_a_players_game_survives_repeated_save_exit_fresh_launch_load(tmp_path: Path) -> None:
    work = tmp_path / "game"
    # 1. a new game: change the world and save
    first = run_step(work, "--mutate", "first", "--save", "slot1")
    _check_first(first["state"])
    assert first["slot"]["unresolved"] == 0
    elder = next(r for r in first["slot"]["entities"] if r.get("mesh_id") == "elder")
    assert elder["primary_tag"] == "merchant" and elder["tags"] == ["alpha", "merchant", "vip", "zeta"]
    # 2. a fresh process: everything is back exactly; change more and save
    second = run_step(work, "--load", "slot1", "--mutate", "second", "--save", "slot1")
    assert second["loaded"] and _game(second["after_load"]) == _game(first["state"])
    _check_second(second["state"])
    # 3. fresh processes: loaded as saved, and further save/load cycles with no change are stable
    previous = second
    for cycle in range(4):
        again = run_step(work, "--load", "slot1", "--save", "slot1")
        assert again["loaded"] and _game(again["after_load"]) == _game(previous["state"]), cycle
        _check_second(again["after_load"])
        assert "could not be matched" not in " ".join(again["after_load"]["toasts"])
        assert again["slot"]["entities"] == second["slot"]["entities"], cycle
        assert again["slot"]["unresolved_records"] == [] and again["after_load"]["held_unresolved"] == 0
        previous = again
    assert QUEST in json.loads((work / "saves" / "slot1.json").read_text(encoding="utf-8"))["state"]["quests"]["quests"]


def test_a_real_v2_save_loads_is_backed_up_byte_for_byte_and_reloads_in_a_fresh_process(tmp_path: Path) -> None:
    work = tmp_path / "v2"
    slot = prepare_v2_idless(work)
    original = slot.read_bytes()
    loaded = run_step(work, "--load", "slot1", "--save", "slot1")
    state = loaded["after_load"]
    assert _sprite(state, None, "spawned_7")["hp"] == 4.0
    assert sorted(s["hp"] for s in state["sprites"] if s["name"] == "proj_Hero") == [2.0, 6.0]
    assert _sprite(state, "hero")["hp"] == 10.0 and _sprite(state, "gob_b")["hp"] == 20.0
    assert state["held_unresolved"] == 2 and "could not be matched" in " ".join(state["toasts"])
    assert (work / "saves" / "slot1.json.v2.bak").read_bytes() == original
    assert json.loads(slot.read_text(encoding="utf-8"))["save_schema_version"] == 3
    again = run_step(work, "--load", "slot1", "--save", "slot1")
    assert _game(again["after_load"])["sprites"] == _game(state)["sprites"]
    assert again["slot"]["unresolved"] == loaded["slot"]["unresolved"] == 2
    assert (work / "saves" / "slot1.json.v2.bak").read_bytes() == original  # (a v3 save never replaces the backup)


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_a_pre390_save_loads_is_backed_up_byte_for_byte_and_reloads_in_a_fresh_process(tmp_path: Path, kind: str) -> None:
    import saved_world_fixtures as fx

    project = fx.build_project(tmp_path / kind, kind)
    (project / "saves").mkdir(exist_ok=True)
    slot = project / "saves" / "slot1.json"
    shutil.copyfile(FIXTURES / f"pre390_{kind}.json", slot)
    original = slot.read_bytes()
    saved = next(r for r in json.loads(original)["saved_entities"]["entities"] if r["entity_id"] == "Player")
    loaded = run_step(project, "--project", "--load", "slot1", "--save", "slot1")
    assert loaded["player"] == [round(saved["x"]), round(saved["y"])]
    assert loaded["flag"] is True and loaded["coins"] == 7 and loaded["held_unresolved"] == 0
    assert loaded["schema"] == 3 and loaded["unresolved"] == 0
    assert (project / "saves" / "slot1.json.v2.bak").read_bytes() == original
    again = run_step(project, "--project", "--load", "slot1", "--save", "slot1")
    assert {k: again[k] for k in ("player", "flag", "coins", "ids")} == {k: loaded[k] for k in ("player", "flag", "coins", "ids")}
    assert again["unresolved"] == 0 and (project / "saves" / "slot1.json.v2.bak").read_bytes() == original


def test_two_entities_with_one_id_in_one_place_are_never_guessed_and_stay_unresolved(tmp_path: Path) -> None:
    work = tmp_path / "ambiguous"
    first = run_step(work, "--room", "dup", "--mutate", "dup", "--save", "slot1")
    assert sorted(s["hp"] for s in first["state"]["sprites"] if s["id"] == "gob_a") == [5.0, 11.0]
    counts = []
    for cycle in range(4):
        step = run_step(work, "--load", "slot1", "--save", "slot1")
        goblins = [s for s in step["after_load"]["sprites"] if s["id"] == "gob_a"]
        assert [g["hp"] for g in goblins] == [20.0, 20.0], cycle  # neither saved state (5 / 11) was picked for either
        assert any("could not be matched" in t for t in step["after_load"]["toasts"]), cycle  # the player is told
        held = sorted(r["record"]["behaviour_state"]["Health"]["hp"] for r in step["slot"]["unresolved_records"])
        assert 5.0 in held and 11.0 in held, cycle  # both original records are kept, unresolved
        assert all(r["reason"] for r in step["slot"]["unresolved_records"])
        counts.append(step["slot"]["unresolved"])
    assert counts[1:] == [counts[1]] * 3, counts  # bounded: it settles after the first re-save
