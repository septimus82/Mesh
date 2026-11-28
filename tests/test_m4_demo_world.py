"""M4's playable demonstration world (tooling/m4_demo_world.py) loads as one world on the real authority: the HD-2D
crossing with three bandits walking their FloorRoutes (the ground, the stairs, the deck), and a player walking west
through its door into the 2D ruins."""

from __future__ import annotations

import pytest

from mesh_net import protocol as wire
from mesh_net.scene_room import disposable_project
from mesh_net.world import World
from tooling.m4_demo_world import BANDITS, RUINS, START, files

pytestmark = pytest.mark.integration  # (builds projects in folders, loads rooms from files)


def test_the_demo_world_walks_its_bandits_and_takes_a_player_through_its_door() -> None:
    with disposable_project(files(), scaffold=False) as root:
        world = World(root, depth=8, hold=1, drain=4, rewind=True)
    crossing = world.defs[START].proto
    assert crossing.world is not None and world.defs[RUINS].proto.world is None, "HD-2D crossing, 2D ruins"
    assert sorted(crossing.enemies) == sorted(b[0] for b in BANDITS)
    assert all(e.route is not None and e.state.max_hp == 30.0 for e in crossing.enemies.values())
    pid, _ = world.connect(None)
    member = world.members[pid]
    start = world.instances[member.instance]
    before = {i: (e.body.center_x, e.body.center_y) for i, e in start.room.enemies.items()}
    for seq in range(1, 120):  # (west from where players arrive, to the door)
        world.input(pid, wire.input_frame(member.eid, seq, -1, 0, start.room.tick + 1, room=member.instance))
        world.step()
        if member.instance != start.id:
            break
    assert world.instances[member.instance].key == RUINS, "through the door into the ruins"
    moved = {i: (e.body.center_x, e.body.center_y) != before[i] for i, e in start.room.enemies.items()}
    assert all(moved.values()), f"every bandit walks on the server: {moved}"
