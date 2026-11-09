"""Fixed 20 Hz room simulation. Only its owner calls step()."""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import HEIGHT, HZ, MAX_PLAYERS, WIDTH, Invalid, Message, movement


@dataclass
class Player:
    x: int = 200
    y: int = 135
    dx: int = 0
    dy: int = 0
    seq: int = 0
    last_input: int = -100


class Room:
    def __init__(self) -> None:
        self.tick = 0
        self.next_id = 1
        self.players: dict[int, Player] = {}

    def join(self, player: Player | None = None) -> int:
        if len(self.players) >= MAX_PLAYERS:
            raise Invalid("room full")
        eid = self.next_id
        self.next_id += 1
        self.players[eid] = player if player is not None else Player(x=200 + 8 * ((eid - 1) % MAX_PLAYERS))
        return eid

    def leave(self, eid: int) -> Player:
        p = self.players.pop(eid)
        p.dx = p.dy = p.seq = 0
        p.last_input = -100
        return p

    def input(self, eid: int, msg: Message) -> None:
        seq, dx, dy = movement(msg, eid)
        p = self.players[eid]
        if seq > p.seq:
            p.seq, p.dx, p.dy, p.last_input = seq, dx, dy, self.tick

    def step(self) -> None:
        self.tick += 1
        for p in self.players.values():
            if self.tick - p.last_input <= HZ // 4:
                p.x = max(8, min(WIDTH - 8, p.x + p.dx * 4))
                p.y = max(8, min(HEIGHT - 8, p.y + p.dy * 4))

    def snapshot(self) -> Message:
        return {"v": 1, "type": "state", "tick": self.tick,
                "players": [[eid, p.x, p.y] for eid, p in self.players.items()]}
