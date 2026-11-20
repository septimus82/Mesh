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
