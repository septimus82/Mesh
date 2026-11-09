"""Room authority and deterministic pickup arbitration."""
import pytest

from mesh_net import protocol as wire
from mesh_net.simulation import Room

pytestmark = pytest.mark.fast


def test_range_cooldown_duplicate_attack_and_single_award():
    room = Room()
    a, b = room.join(), room.join()

    def act(owner, seq, action):
        room.input(owner, {"v": 1, "type": "input", "entity": owner, "seq": seq, "dx": 0, "dy": 0, "action": action})

    room.players[a].x = 20
    act(a, 1, "attack")
    room.step()
    assert room.enemy.hp == 2
    room.players[a].x = 200
    act(a, 2, "attack")
    room.step()
    assert room.enemy.hp == 1
    act(a, 3, "attack")
    room.step()
    assert room.enemy.hp == 1
    for _ in range(8):
        room.step()
    act(a, 3, "attack")
    room.step()
    assert room.enemy.hp == 1
    act(b, 1, "attack")
    room.step()
    assert room.enemy.dead and room.pickup
    # A new connection with an old entity id cannot claim loot.
    with pytest.raises(wire.Invalid):
        room.input(b, {"v": 1, "type": "input", "entity": a, "seq": 4, "dx": 0, "dy": 0, "action": "take"})
    act(b, 2, "take")
    act(a, 4, "take")
    room.step()
    assert room.snapshot()["holder"] == a and not room.pickup
    act(b, 3, "take")
    room.step()
    assert not room.players[b].loot
    character = room.leave(a)
    assert room.snapshot()["holder"] is None
    resumed = room.join(character)
    assert resumed != a and room.snapshot()["holder"] == resumed and room.enemy.dead


def test_headless_authority_does_not_load_graphics_or_studio():
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", "import sys; from mesh_net.server import Server; Server(); "
                    "assert not any(k in sys.modules for k in ('arcade', 'pyglet', 'engine.game', 'engine.studio'))"],
                   check=True)
