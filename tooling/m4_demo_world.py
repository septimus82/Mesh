"""M4's playable two-client demonstration: an HD-2D room with walking enemies, and a 2D room through a door.

    py -3.13 tooling/m4_demo_world.py server [--port 46870] [--queue drain|deep|small] [--rewind on|off]
    py -3.13 tooling/m4_demo_world.py client [--port 46870]
    py -3.13 tooling/m4_demo_world.py files OUT     # the world as a project folder (for tooling/net_world_probe.py)

The authority is mesh_net.server's WorldServer, with its input-queue presets and lag compensation switch (the same
``--queue`` / ``--rewind`` and MESH_NET_* variables as ``python -m mesh_net.server``); the client is
mesh_net.world_client's window. Both build the world from the same files, made here from what the repository has:

- ``start`` (where players arrive): the floors demo's crossing (HD-2D, tooling/hd2d_floors_demo.py: open ground, two
  platforms 2 m up with a staircase each, a railed bridge deck between them over an underpass). Three bandits (the
  co-op room's, given 30 HP so a fight lasts) walk FloorRoutes on the server (M4-4), on tooling/m4_latency_probe.py's
  routes: on the open ground just east of where players arrive, up and down the west stairs, and along the bridge
  deck. A walk-in door on the open ground to the west leads to the ruins. (The floors demo's warden, a
  non-enemy that walks only in single-player, is left out: it would stand still online.)
- ``ancient_ruins_layer_1``: the packaged expedition's Layer 1 (2D), here an ordinary shared room (no party needed),
  with its lever, gate and standing bandit; its door to Layer 2 is left out, its door back leads to the crossing.

A demonstration, not content: nothing here changes a rule, the protocol or single-player.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from contextlib import ExitStack
from functools import cache
from importlib.resources import files as package_files
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):  # (run as a script: the checkout's packages)
    sys.path.insert(0, str(REPO))

START, RUINS = "start", "ancient_ruins_layer_1"
START_SCENE = "packs/core_regions/scenes/start.json"
RUINS_SCENE = "packs/core_regions/scenes/ancient_ruins_layer_1.json"
WORLD_FILE = "packs/core_regions/worlds/main.json"  # (mesh_net.world.WORLD_FILE)
HP = 30.0
SPAWN = (512.0, 114.0)  # px: the floors demo's player (a sprite centre on the open ground; feet 18 px below)
# Bandits: (id, sprite centre x, y, elevation px, FloorRoute feet points) on tooling/m4_latency_probe.py's routes.
BANDITS = (
    ("bandit_ground", 552.0, 122.0, 0.0, [[552.0, 104.0, 0.0], [664.0, 104.0, 0.0]]),  # GROUND_ROUTE
    ("bandit_stairs", 328.0, 170.0, 0.0, [[328.0, 152.0, 4.0], [328.0, 264.0, 60.0]]),  # STAIRS_ROUTE
    ("bandit_deck", 472.0, 402.0, 64.0, [[472.0, 384.0, 64.0], [584.0, 384.0, 64.0]]),  # DECK_ROUTE
)
SPEED = 70.0  # px/s as authored (the probe's)
DOOR = (64.0, 114.0)  # px: the walk-in door to the ruins, on the open ground west of the spawn
ARRIVAL = (176.0, 114.0)  # px: where a player back from the ruins arrives, clear of that door


@cache
def files() -> dict[str, bytes]:
    """The demonstration world's project files (built once a process)."""
    from mesh_net.world import expedition_files  # noqa: PLC0415
    from tooling.m4_latency_probe import crossing_files  # noqa: PLC0415

    expedition, crossing = expedition_files(), crossing_files()
    out = {**expedition, **crossing}  # (the crossing's own project: its prefabs, map and tileset where they meet)
    scene = json.loads(crossing[START_SCENE])
    hub = json.loads(expedition[START_SCENE])
    door = copy.deepcopy(next(e for e in hub["entities"] if e.get("tag") == "door"))  # (the hub's walk-in door)
    door.update(id="start_door_to_ruins", name="Door to the Ruins", x=DOOR[0], y=DOOR[1])
    door["behaviour_config"]["SceneTransition"]["target_scene"] = RUINS
    arrival = {"id": "start_arrival_from_ruins", "name": "Arrival from the Ruins", "spawn_id": f"from_{RUINS}",
               "tag": "spawn_point", "x": ARRIVAL[0], "y": ARRIVAL[1]}
    coop = json.loads(package_files("mesh_net").joinpath("coop", "scene.json").read_text(encoding="utf-8"))
    template = next(e for e in coop["entities"] if e.get("tag") == "enemy")
    bandits = []
    for bid, x, y, z, route in BANDITS:
        b = copy.deepcopy(template)
        b.update(id=bid, x=x, y=y, elevation=z)
        b["behaviours"] = [*b["behaviours"], "FloorRoute"]
        b["behaviour_config"]["FloorRoute"] = {"route": route, "speed": SPEED, "wait": 0.0}
        b["behaviour_config"]["Health"].update(hp=HP, max_hp=HP)
        bandits.append(b)
    scene["name"] = "M4 demo: the crossing"
    scene["entities"] = [e for e in scene["entities"] if e["id"] != "warden"] + bandits + [door, arrival]
    out[START_SCENE] = json.dumps(scene, indent=1).encode()
    ruins = json.loads(expedition[RUINS_SCENE])
    ruins["entities"] = [e for e in ruins["entities"]
                         if (e.get("behaviour_config") or {}).get("SceneTransition", {}).get("target_scene") != "ancient_ruins_layer_2"]
    out[RUINS_SCENE] = json.dumps(ruins, indent=1).encode()
    world = {"id": "m4_demo", "name": "M4 demo", "start_scene": START,
             "scenes": {START: {"label": "The crossing (HD-2D)", "path": START_SCENE, "tags": ["start"]},
                        RUINS: {"label": "The ruins (2D)", "path": RUINS_SCENE, "tags": []}}}
    out[WORLD_FILE] = json.dumps(world, indent=1).encode()
    return out


def write(out: Path) -> Path:
    """The world as a project folder ``out`` (new or empty)."""
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    for rel, data in files().items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return out


def serve(args: argparse.Namespace) -> None:
    from mesh_net.scene_room import disposable_project  # noqa: PLC0415
    from mesh_net.server import WorldServer, queue_from, rewind_from  # noqa: PLC0415
    from mesh_net.server import serve as run  # noqa: PLC0415
    from mesh_net.world import World  # noqa: PLC0415

    try:
        queue, rewind = queue_from(args), rewind_from(args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    with ExitStack() as stack:
        root = stack.enter_context(disposable_project(files(), scaffold=False))
        world = World(root, depth=queue["depth"], hold=queue["hold"], drain=queue["drain"], rewind=rewind)
        print(f"Mesh world {world.identity[:12]} (M4 demo)", flush=True)
        print("Mesh input queue " + " ".join(f"{k} {v}" for k, v in queue.items()), flush=True)
        print(f"Mesh lag compensation {'on' if rewind else 'off'}", flush=True)
        try:
            asyncio.run(run(args.port, world, WorldServer))
        except KeyboardInterrupt:
            pass


def client(args: argparse.Namespace) -> None:
    from mesh_net.demo import open_arena  # noqa: PLC0415
    from mesh_net.world_client import SIZE, WorldArena  # noqa: PLC0415

    with open_arena(files(), SIZE, WorldArena) as arena:
        asyncio.run(arena.run(args.port))


def main(argv: list[str] | None = None) -> None:
    from mesh_net.scene_room import QUEUE, QUEUE_PRESETS  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("server", help="host the demonstration world (one per PC, before the clients)")
    server.add_argument("--port", type=int, default=46870)
    server.add_argument("--queue", choices=sorted(QUEUE_PRESETS),
                        help=f"the input queue's preset ({QUEUE} is the provisional default; else MESH_NET_QUEUE)")
    server.add_argument("--rewind", choices=("on", "off"),
                        help="lag compensation (M4-5); else MESH_NET_REWIND (1/0), else on")
    window = sub.add_parser("client", help="one player's window (run two)")
    window.add_argument("--port", type=int, default=46870, help="the server's port, or a delay proxy's in front of it")
    folder = sub.add_parser("files", help="write the world as a project folder")
    folder.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "server":
        serve(args)
    elif args.command == "client":
        client(args)
    else:
        print(write(args.out))


if __name__ == "__main__":
    main(sys.argv[1:])
