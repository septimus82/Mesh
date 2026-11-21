"""A delayed downlink must not prevent input reaching the room."""

import asyncio
from types import SimpleNamespace

import pytest

from mesh_net.client import Client
from mesh_net.demo import Arena
from mesh_net.server import Server

pytestmark = pytest.mark.integration


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.005)


def test_release_and_attack_reach_authority_during_nine_tick_downlink_pause():
    async def run():
        server = Server()
        port = await server.start()
        gate = asyncio.Event()
        gate.set()
        held = asyncio.Event()
        relay_tasks = set()

        async def relay(reader, writer):
            upstream, upstream_writer = await asyncio.open_connection("127.0.0.1", port)

            async def forward(source, target, downlink=False):
                while data := await source.readline():
                    if downlink and not gate.is_set():
                        held.set()
                        await gate.wait()
                    target.write(data)
                    await target.drain()

            tasks = [asyncio.create_task(forward(reader, upstream_writer)),
                     asyncio.create_task(forward(upstream, writer, True))]
            relay_tasks.update(tasks)
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                relay_tasks.difference_update(tasks)
                writer.close()
                upstream_writer.close()
                await asyncio.gather(writer.wait_closed(), upstream_writer.wait_closed(), return_exceptions=True)

        listener = await asyncio.start_server(relay, "127.0.0.1", 0)
        symbols = "W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split()
        keys = SimpleNamespace(**{name: index for index, name in enumerate(symbols)})
        arena = Arena(SimpleNamespace(push_handlers=lambda **kw: None), SimpleNamespace(key=keys))
        session = asyncio.create_task(arena.session(listener.sockets[0].getsockname()[1]))
        try:
            await until(lambda: arena.client is not None)
            player = server.room.players[arena.client.entity]
            arena.press(keys.RIGHT, 0)
            await until(lambda: player.x > 200)
            gate.clear()
            await asyncio.wait_for(held.wait(), 2)
            arena.release(keys.RIGHT, 0)
            arena.press(keys.SPACE, 0)
            tick = server.room.tick
            await until(lambda: server.room.tick >= tick + 9)
            assert player.dx == 0
            assert server.room.enemy.hp == 1
        finally:
            gate.set()
            session.cancel()
            await asyncio.gather(session, return_exceptions=True)
            listener.close()
            await listener.wait_closed()
            await asyncio.gather(*relay_tasks, return_exceptions=True)
            await server.close()
    asyncio.run(run())


def test_session_shutdown_joins_input_even_if_cancellation_is_swallowed(monkeypatch):
    async def delayed_input(self, dx, dy, action=None):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            # A completed drain can consume a concurrent cancellation. The
            # production stream must still be closed before joining this task.
            if self.writer.is_closing():
                raise OSError("stream closed") from None

    monkeypatch.setattr(Client, "input", delayed_input)

    async def run():
        server = Server()
        port = await server.start()
        arena = Arena(SimpleNamespace(push_handlers=lambda **kw: None), SimpleNamespace(key=SimpleNamespace(**{
            name: index for index, name in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})))
        session = asyncio.create_task(arena.session(port))
        try:
            await until(lambda: arena.client is not None)
            await asyncio.sleep(0.02)
            session.cancel()
            done, _ = await asyncio.wait([session], timeout=2)
            assert done, "client input task outlived session shutdown"
            assert session.cancelled()
        finally:
            if arena.client:
                arena.client.writer.close()
            session.cancel()
            await asyncio.gather(session, return_exceptions=True)
            await server.close()
    asyncio.run(run())
