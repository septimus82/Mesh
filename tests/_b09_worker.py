"""B-09 worker: ONE step of a player's session as its own process (``python -m tests._b09_worker``).

    python -m tests._b09_worker WORKDIR [--load SLOT] [--mutate spawn:N:SALT|expire|move] [--save SLOT]

A hidden GameWindow (MESH_GL_SMOKE=1), the production SaveManager, a real room file in WORKDIR. It starts a fresh
game, optionally loads a slot as Continue does, optionally changes the game, optionally saves, prints ONE JSON line
and exits (a trimmed copy of the GAME-1 worker's approach).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests._b01_arena import PIC, Arena, close_window, goblin, hero, make_window

PROJECTILE = {"x": 30, "y": 30, "sprite": PIC, "layer": "entities"}  # id-less, as a shooter's projectile


def run_step(workdir: Path, *args: str) -> dict[str, Any]:
    env = {**os.environ, "MESH_GL_SMOKE": "1"}
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-m", "tests._b09_worker", str(workdir), *args], cwd=repo, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("B09_RESULT ")]
    assert proc.returncode == 0 and len(lines) == 1, (proc.returncode, proc.stdout[-1500:], proc.stderr[-1500:])
    result: dict[str, Any] = json.loads(lines[0][len("B09_RESULT "):])
    return result


def mutate(arena: Arena, name: str) -> None:
    if name.startswith("spawn:"):  # spawn:COUNT[:SALT]  (named proj_SALT_N, one entity each)
        count, _, salt = name.split(":", 1)[1].partition(":")
        for n in range(int(count)):
            arena.spawn(dict(PROJECTILE, name=f"proj_{salt or 0}_{n}", x=200 + n))
    elif name == "expire":  # projectile.py: remove_from_sprite_lists()
        for sprite in [s for s in arena.sprites() if s.mesh_name.startswith("proj_")]:
            sprite.remove_from_sprite_lists()
    else:
        raise SystemExit(f"unknown mutation {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir", type=Path)
    parser.add_argument("--load")
    parser.add_argument("--mutate", action="append", default=[])
    parser.add_argument("--save")
    args = parser.parse_args(argv)
    window = make_window()
    try:
        arena = Arena(window, args.workdir)
        arena.saves.mkdir(parents=True, exist_ok=True)
        if not arena.room.exists():
            arena.write_room(hero(), goblin("gob_a", 100, 100))
        arena.enter()
        out: dict[str, Any] = {}
        if args.load:
            assert arena.load(args.load)
        out["after_load"] = sorted(s.mesh_name for s in arena.sprites())
        for name in args.mutate:
            mutate(arena, name)
        if args.save:
            assert arena.manager.save_game(args.save), "the save was refused"
            data = arena.read(args.save)
            out["slot"] = {"size": (arena.slot(args.save)).stat().st_size,
                           "entities": sorted(str(e.get("name")) for e in data["entities"])}
        out["live"] = sorted(s.mesh_name for s in arena.sprites())
        print("B09_RESULT " + json.dumps(out, sort_keys=True))
        sys.stdout.flush()
    finally:
        close_window(window)
    return 0


if __name__ == "__main__":
    sys.exit(main())
