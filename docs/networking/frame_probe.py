"""Windows/QPC or Linux/monotonic, two real Mesh windows, one TCP authority.

Run from the checkout. Measures dispatched key event to rendered pixels before swap.
Each client reads a single framebuffer row and keeps at most 4,000 frame samples.
"""
import asyncio
import json
import os
import random
import statistics
import sys
from collections import deque
from time import perf_counter
from unittest.mock import patch

from mesh_net.demo import OTHER, OWN, open_arena
from mesh_net.server import Server


async def worker(arena, port):
    frames = deque(maxlen=4000)
    draw = arena.draw

    def measured(now):
        draw(now)
        if not arena.client:
            return
        w, h = arena.window.get_framebuffer_size()
        row = arena.arcade.get_image(0, h // 2, w, 1).convert("RGB")
        pixels = list(row.getdata())  # Pillow 11 in the reviewed distribution
        def centre(color):
            indexes = [i for i, rgb in enumerate(pixels) if rgb == color]
            return (indexes[0] + indexes[-1]) / 2 if indexes else None
        state = arena.client.state
        positions = sorted(state["players"])
        frames.append([perf_counter(), centre(OWN), centre(OTHER), state["enemy_hp"],
                       (149, 224, 82) in pixels, positions])
    arena.draw = measured
    game = asyncio.create_task(arena.run(port))
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            if game.done():
                game.result()
            parts = line.split()
            if parts[0] == "quit":
                return
            t = perf_counter()
            if parts[0] in ("press", "release"):
                arena.window.dispatch_event("on_key_" + parts[0], getattr(arena.arcade.key, parts[1]), 0)
            result = list(frames) if parts[0] == "frames" else [t, arena.client.entity if arena.client else None]
            print("FRAME_PROBE " + json.dumps(result, separators=(",", ":")), flush=True)
    finally:
        arena.stop()
        await game


async def command(proc, line):
    proc.stdin.write((line + "\n").encode())
    await proc.stdin.drain()
    async with asyncio.timeout(60):
        while data := await proc.stdout.readline():
            if data.startswith(b"FRAME_PROBE "):
                return json.loads(data[12:])
        raise RuntimeError(f"window exited {await proc.wait()}")


def summary(values):
    return {"n": len(values), "median": round(statistics.median(values), 2),
            "p95": round(statistics.quantiles(values, n=20, method="inclusive")[-1], 2),
            "max": round(max(values), 2)}


async def run():
    server = Server()
    port = await server.start()
    procs = []
    rng = random.Random(3941)
    try:
        for _ in range(2):
            p = await asyncio.create_subprocess_exec(sys.executable, __file__, str(port), limit=1024 * 1024,
                                                     stdin=-1, stdout=-1, stderr=-1)
            procs.append(p)
            async with asyncio.timeout(45):
                while not (await command(p, "ready"))[1]:
                    await asyncio.sleep(0.02)
        a, b = procs  # start order fixes player ids, positions and draw order
        await asyncio.sleep(0.5)
        await command(a, "press SPACE")
        async with asyncio.timeout(2):
            while server.room.enemy.hp != 1:
                await asyncio.sleep(0.005)
        attack_t = (await command(b, "press SPACE"))[0]
        await command(b, "press UP")
        await asyncio.sleep(0.35)
        await command(b, "release UP")
        await asyncio.sleep(0.35)
        trials = []
        for i in range(16):
            key = "LEFT" if i % 2 == 0 else "RIGHT"
            await asyncio.sleep(rng.uniform(0.01, 0.055))
            start = (await command(a, f"press {key}"))[0]
            await asyncio.sleep(0.38)
            end = (await command(a, f"release {key}"))[0]
            await asyncio.sleep(0.36)
            trials.append((start, end, perf_counter(), key))
        # Eight rapid reversals through the same event path.
        turns = []
        for i in range(8):
            key = "LEFT" if i % 2 == 0 else "RIGHT"
            turns.append((await command(a, f"press {key}"))[0])
            await asyncio.sleep(0.08)
            await command(a, f"release {key}")
        await asyncio.sleep(0.5)
        # Controlled position correction on the authority with all keys released.
        player = server.room.players[1]
        target = player.x - 64
        correction = perf_counter()
        player.x = target
        await asyncio.sleep(0.5)
        both = await asyncio.gather(*(command(p, "frames") for p in procs))
        result = {}
        onsets = [{}, {}]
        for label, data, col in zip(("local", "remote"), both, (1, 2)):
            starts, stops, advances, invalid = [], [], [], 0
            for start, end, settled, key in trials:
                prior = [r for r in data if r[0] <= start][-1][col]
                rows = [r for r in data if start < r[0] <= settled]
                final = rows[-1][col]
                at_release = [r for r in rows if r[0] <= end][-1][col]
                if None in (prior, final, at_release) or any(r[col] is None for r in rows):
                    invalid += 1  # overlapping avatars can occlude one another
                    continue
                sign = -1 if key == "LEFT" else 1
                first = next((r for r in rows if (r[col] - prior) * sign >= 1), None)
                if first is None:
                    invalid += 1
                    continue
                starts.append(1000 * (first[0] - start))
                last_motion = max((i for i, r in enumerate(rows) if r[col] != final), default=-1) + 1
                stops.append(1000 * max(0, rows[last_motion][0] - end))
                advances.append(abs(final - at_release))
                onsets[col - 1][start] = first[0]
            attack = next(r[0] for r in data if r[0] > attack_t and r[4])
            track = [r for r in data if turns[0] <= r[0] <= turns[-1] + 0.45 and r[col] is not None]
            signs = [1 if y[col] > x[col] else -1 for x, y in zip(track, track[1:]) if y[col] != x[col]]
            prior = [r for r in data if r[0] < correction][-1][col]
            settled = next(r for r in data if r[0] > correction and r[col] is not None and abs(r[col] - (prior - 64)) <= 1)
            corrected = next(r for r in data if r[0] > correction and any(p[0] == 1 and p[1] == target for p in r[5]))
            result[label] = {"correction_snapshot_ms": round(1000 * (corrected[0] - correction), 2),
                             "correction_pixel_settled_ms": round(1000 * (settled[0] - correction), 2),
                             "start_ms": summary(starts), "settle_after_release_ms": summary(stops),
                             "post_release_pixels": summary(advances), "excluded_trials": invalid,
                             "fatal_attack_to_green_pixel_ms": round(1000 * (attack - attack_t), 2),
                             "rapid_visible_direction_reversals": sum(x != y for x, y in zip(signs, signs[1:])),
                             "frame_interval_ms": summary([1000 * (y[0] - x[0]) for x, y in zip(data, data[1:])])}
        common = sorted(onsets[0].keys() & onsets[1].keys())
        result["between_windows_onset_skew_ms"] = summary([1000 * abs(onsets[0][t] - onsets[1][t]) for t in common])
        print(json.dumps(result, indent=2))
    finally:
        for p in procs:
            if p.returncode is None:
                p.stdin.write(b"quit\n")
                await p.stdin.drain()
            p.stdin.close()
        for p in procs:
            try:
                await asyncio.wait_for(p.wait(), 8)
            except TimeoutError:
                p.kill()
                await p.wait()
        await server.close()
        for p in procs:
            if p.returncode:
                print((await p.stderr.read()).decode()[-3000:])
        codes = [p.returncode for p in procs]
        assert all(code == 0 for code in codes), f"window exit codes {codes}"


if __name__ == "__main__" and len(sys.argv) == 2:
    from engine import optional_arcade
    original = optional_arcade.arcade.Window.__init__

    def hidden(window, *args, **kwargs):
        original(window, *args, **{**kwargs, "visible": False})

    with patch.object(optional_arcade.arcade.Window, "__init__", hidden), open_arena() as arena:
        arena.local_interpolation = os.environ.get("MESH_NET_LOCAL_INTERPOLATION") == "1"
        asyncio.run(worker(arena, int(sys.argv[1])))
elif __name__ == "__main__":
    asyncio.run(run())
