"""The command channel of the real-window networking tests: one hidden client window per process (tooling/net_world_probe.py,
tooling/net_window_probe.py, tooling/net_scene_probe.py), driven over its stdin/stdout. Shared by the tests and the tooling
that drives windows (tooling/m3_two_client_evidence.py)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from typing import Any

worker_logs: defaultdict[Any, deque[str]] = defaultdict(lambda: deque(maxlen=30))


async def command(proc: Any, cmd: str) -> Any:
    """Send one command; return the window's ``NET_PROOF`` reply (its other output kept in ``worker_logs``)."""
    proc.stdin.write((cmd + "\n").encode())
    await proc.stdin.drain()
    async with asyncio.timeout(90):
        while line := await proc.stdout.readline():
            if line.startswith(b"NET_PROOF "):
                return json.loads(line[len(b"NET_PROOF "):])
            worker_logs[proc].append(line.decode(errors="replace").rstrip())
        raise RuntimeError(f"window process exited with {await proc.wait()}: {list(worker_logs[proc])}")


async def stop_workers(procs: list[Any]) -> list[str]:
    """Quit every window and wait for it (killed after 8 s); what went wrong, if anything."""
    problems = []
    for proc in procs:
        if proc.stdin and not proc.stdin.is_closing():
            if proc.returncode is None:
                try:
                    proc.stdin.write(b"quit\n")
                    await proc.stdin.drain()
                except OSError:
                    pass
            proc.stdin.close()
    for proc in procs:
        reader = asyncio.create_task(proc.stdout.read())
        try:
            await asyncio.wait_for(proc.wait(), 8)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            problems.append("worker timed out and was killed")
        output = await reader
        if proc.returncode != 0:
            problems.append(f"worker exited {proc.returncode}: {list(worker_logs[proc])}, {output[-2000:]!r}")
    return problems


def require_clean_workers(problems: list[str]) -> None:
    if problems:
        raise AssertionError("; ".join(problems))
