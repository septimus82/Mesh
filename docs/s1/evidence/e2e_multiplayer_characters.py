"""S1-0 part D, workflow 7: a basic multiplayer session with preserved character progress (mesh_net N6-N8).

    py -3.13 docs/s1/evidence/e2e_multiplayer_characters.py        (PYTHONPATH = this checkout)

1. The admin CLI (``python -m mesh_net.characters``, called in-process): ``new-store``, ``create Ada`` / ``create Bo``
   with their key files.
2. Progress: both characters play the packaged expedition in-process (mesh_net.world.World with the store, driven by the
   tests' Driver: tests/test_mesh_net_world.py; it teleports between fights, so this step is NOT the client path):
   party, hub -> Layer 1 -> Layer 2, the guardian, the loot. The store is closed afterwards (the "server" is gone).
3. The real host: ``python -m mesh_net.server --expedition --store STORE --port N`` as a child process (the only other
   Python process, for a few seconds). Two socket clients (tests' Peer: what mesh_net.world_client does, without a
   window) join with their key files: both sheets must show the earned items and unlock.
4. In the same session: Ada's connection drops; she joins again with her key file and must resume as the same player
   in the same room; a second session for Bo while Bo is online must be refused.
5. ``python -m mesh_net.characters list`` afterwards.

Exits 1 when progress, resume or the one-session rule fails. The temp folder is removed afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
os.chdir(REPO)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    import engine  # noqa: F401  (only to confirm which checkout)
    import mesh_net
    from mesh_net import characters as admin
    from mesh_net import protocol as wire
    from mesh_net.characters import CharacterStore
    from mesh_net.persistence import expedition_rules
    from mesh_net.scene_room import disposable_project
    from mesh_net.world import World, check_frame, check_welcome, expedition_files
    from tests.test_mesh_net_characters import P, to_layer_2
    from tests.test_mesh_net_world import GUARDIAN, Peer, kill  # noqa: F401

    print("mesh_net from", Path(mesh_net.__file__).relative_to(REPO.parent).as_posix())
    tmp = Path(tempfile.mkdtemp(prefix="mesh_s1_net_"))
    defects: list[str] = []
    server = None
    try:
        store_path = tmp / "characters.db"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codes = [admin.main(["new-store", str(store_path)]),
                     admin.main(["create", str(store_path), "Ada", "--key-file", str(tmp / "ada.key")]),
                     admin.main(["create", str(store_path), "Bo", "--key-file", str(tmp / "bo.key")])]
        print("1. admin CLI exit codes:", codes)
        ada = {k: v for k, v in json.loads((tmp / "ada.key").read_text()).items() if k in ("id", "key")}
        bo = {k: v for k, v in json.loads((tmp / "bo.key").read_text()).items() if k in ("id", "key")}

        files = expedition_files()
        store = CharacterStore(store_path)
        with disposable_project(files, scaffold=False) as root:
            world = World(root, store=store, rules=expedition_rules())
        d = P(world)
        a, b = d.enter(ada), d.enter(bo)
        d.party(a, b)
        to_layer_2(d, a, b)
        kill(d, a, (480.0, 256.0), 2)
        for pid in (a, b):
            d.take_loot(pid, (440.0, 256.0))
        earned = {name: store.load(c["id"]) for name, c in (("Ada", ada), ("Bo", bo))}
        print("2. earned:", {n: (dict(s.items), list(s.unlocks)) for n, s in earned.items()})
        if world.progress is not None:
            world.progress.close()
        store.close()

        port = free_port()
        env = {k: v for k, v in os.environ.items() if not k.startswith("MESH_")}
        server = subprocess.Popen([sys.executable, "-m", "mesh_net.server", "--expedition", "--store", str(store_path),
                                   "--port", str(port)], cwd=str(tmp), env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        banner = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            line = server.stdout.readline() if server.stdout else ""
            if not line:
                break
            banner.append(line.strip())
            if line.startswith("Mesh lag compensation"):
                break
        print("3. server banner:", banner)
        time.sleep(0.5)

        with disposable_project(files, scaffold=False) as root2:
            local = World(root2)  # (same packaged files: the identities a client checks frames against)

        async def join(credential):
            reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
            writer.write(wire.encode({"v": wire.VERSION, "type": "join", "resume": None, "character": credential}))
            peer = Peer(reader, writer, local)
            hello = await wire.read(reader)
            if hello.get("type") == "refused":
                writer.close()
                return hello["code"]
            check_welcome(hello, local.identity)
            peer.player, peer.sheet = hello["player"], None
            return peer

        async def until(peer, predicate, timeout=10.0):
            async def loop():
                while not predicate(peer):
                    msg = await wire.read(peer.reader)
                    check_frame(msg, peer.identities)
                    if msg["type"] == "enter":
                        peer.room, peer.key, peer.entity, peer.state = msg["room"], msg["key"], msg["entity"], msg["state"]
                    elif msg["type"] == "room_state" and msg["room"] == peer.room:
                        peer.state = msg["state"]
                    elif msg["type"] == "character":
                        peer.sheet = msg
            await asyncio.wait_for(loop(), timeout)

        async def session():
            pa, pb = await join(ada), await join(bo)
            for p in (pa, pb):
                await until(p, lambda q: q.room and q.sheet)
            sheets = {p.sheet["name"]: p.sheet for p in (pa, pb)}
            for name, state in earned.items():
                got = sheets[name]
                ok = got["id"] == state.id and got["items"] == [list(i) for i in state.items] and \
                    got["unlocks"] == list(state.unlocks)
                print(f"3. {name} over sockets after a server restart: items={got['items']} unlocks={got['unlocks']} "
                      f"-> {'kept' if ok else 'LOST'}")
                if not ok:
                    defects.append(f"{name}'s progress not restored")
            for _ in range(10):  # Ada walks right for a moment (server-side movement)
                await pa.move(1, 0)
                await until(pa, lambda q, t=pa.state["tick"]: q.state["tick"] > t)
            moved_to, room, player = pa.own()[1:3], pa.room, pa.player
            pa.writer.transport.abort()  # her connection drops
            await asyncio.sleep(0.3)
            pa2 = await join(ada)
            if isinstance(pa2, str):
                print("4. Ada's rejoin refused:", pa2)
                defects.append("Ada could not rejoin")
            else:
                await until(pa2, lambda q: q.room and q.sheet)
                same = pa2.player == player and pa2.room == room
                print(f"4. Ada rejoined: player {player} -> {pa2.player}, room same: {pa2.room == room}, "
                      f"at {moved_to} -> {pa2.own()[1:3]} -> {'resumed' if same else 'NOT resumed'}")
                if not same:
                    defects.append("Ada's dropped session was not resumed")
            refused = await join(bo)
            print("4. a second session for Bo while online:", refused if isinstance(refused, str) else "ADMITTED")
            if refused != "character_in_use":
                defects.append("a second session for an online character was not refused")
                if not isinstance(refused, str):
                    await refused.close()
            for p in (pb, pa2):
                if not isinstance(p, str):
                    await p.close()

        asyncio.run(session())
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            from mesh_net import characters as admin2

            admin2.main(["list", str(tmp / "characters.db")])
        print("5. characters list:", [" ".join(x.split()[1:]) for x in out.getvalue().splitlines()])
        listing = sorted(p.name for p in tmp.iterdir())
        shutil.rmtree(tmp, ignore_errors=True)  # (the temp folder this script created)
        print("removed temp folder holding:", listing)
    if defects:
        print("DEFECTS:", "; ".join(defects))
        return 1
    print("multiplayer session with preserved character progress: works")
    return 0


if __name__ == "__main__":
    sys.exit(main())
