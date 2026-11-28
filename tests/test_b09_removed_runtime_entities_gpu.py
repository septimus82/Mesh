"""B-09 through fresh processes: a projectile-like (id-less) object spawned, saved, then expired after a load stays
gone on the next load, and the slot's object list stays flat over cycles. Each step is its own hidden-window process
with the production SaveManager (tests/_b09_worker.py). GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from engine import optional_arcade
from tests._b09_worker import run_step

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]


def test_an_expired_runtime_object_does_not_come_back_on_the_next_load(tmp_path: Path) -> None:
    work = tmp_path / "w"
    run_step(work, "--mutate", "spawn:1:0", "--save", "slot1")
    r2 = run_step(work, "--load", "slot1", "--mutate", "expire", "--save", "slot1")
    assert "proj_0_0" in r2["after_load"] and "proj_0_0" not in r2["live"]
    assert r2["slot"]["entities"] == ["Goblin", "Hero"]  # (not written again)
    r3 = run_step(work, "--load", "slot1")
    assert r3["after_load"] == ["Goblin", "Hero"]
    shutil.rmtree(work, ignore_errors=True)


def test_the_slot_does_not_grow_with_each_cycles_spawns(tmp_path: Path) -> None:
    """load, last cycle's projectiles expire, new ones spawn, save: the slot keeps this cycle's alone."""
    work = tmp_path / "w"
    run_step(work, "--mutate", "spawn:5:0", "--save", "slot1")
    counts = []
    for cycle in range(1, 4):
        r = run_step(work, "--load", "slot1", "--mutate", "expire", "--mutate", f"spawn:5:{cycle}", "--save", "slot1")
        counts.append(len(r["slot"]["entities"]))
    assert counts == [7, 7, 7]  # Hero, Goblin and the five live projectiles
    shutil.rmtree(work, ignore_errors=True)


def _reverse_slot_entities(work: Path) -> None:
    import json

    path = work / "saves" / "slot1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entities"].reverse()  # (the runtime object before the room's, whatever order a save came to have)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("reverse", [False, True])
def test_a_same_named_runtime_twin_of_an_id_less_room_object_never_costs_the_room_object(tmp_path: Path, reverse: bool) -> None:
    work = tmp_path / "w"
    run_step(work, "--wolf", "--mutate", "wolf_runtime", "--mutate", "move_wolf", "--save", "slot1")
    if reverse:
        _reverse_slot_entities(work)
    # (1) the runtime twin expires, the room's wolf stays live where play left it
    r = run_step(work, "--wolf", "--load", "slot1", "--mutate", "expire_runtime_wolf", "--save", "slot1")
    assert 420.0 in r["slot"]["wolves"]
    assert run_step(work, "--wolf", "--load", "slot1")["after_load"].count("wolf") >= 1  # (the expired twin may linger: told apart by nothing)
    # (2) both have no sprite (removed in play): the room's wolf is still carried, never dropped for its twin
    r = run_step(work, "--wolf", "--load", "slot1", "--mutate", "expire_all_wolves", "--save", "slot1")
    assert 420.0 in r["slot"]["wolves"]
    shutil.rmtree(work, ignore_errors=True)
