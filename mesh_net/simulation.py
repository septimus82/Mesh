"""Fixed 20 Hz room simulation. Only its owner calls step()."""

from __future__ import annotations

from dataclasses import dataclass

from engine.combat_model import AttackSpec, TargetState, resolve_attack

from .protocol import ENEMY_AT, ENEMY_HP, HEIGHT, HZ, MAX_PLAYERS, WIDTH, Invalid, Message, movement


@dataclass
class Player:
    x: int = 200
    y: int = 135
    dx: int = 0
    dy: int = 0
    seq: int = 0
    last_input: int = -100
    action: str | None = None
    attack_after: int = 0
    loot: bool = False


class Room:
    def __init__(self) -> None:
        self.tick = 0
        self.enemy = TargetState(hp=ENEMY_HP, max_hp=ENEMY_HP)
        self.pickup = False
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
        p.action = None
        return p

    def input(self, eid: int, msg: Message) -> None:
        seq, dx, dy, action = movement(msg, eid)
        p = self.players[eid]
        if seq > p.seq:
            p.seq, p.dx, p.dy, p.last_input = seq, dx, dy, self.tick
            if p.action is None:
                p.action = action

    def step(self) -> None:
        self.tick += 1
        for eid, p in self.players.items():
            if self.tick - p.last_input <= HZ // 4:
                p.x = max(8, min(WIDTH - 8, p.x + p.dx * 4))
                p.y = max(8, min(HEIGHT - 8, p.y + p.dy * 4))

            action, p.action = p.action, None
            if action is None or (p.x - ENEMY_AT[0]) ** 2 + (p.y - ENEMY_AT[1]) ** 2 > 36 ** 2:
                continue
            if action == "attack" and not self.enemy.dead and self.tick >= p.attack_after:
                hit = AttackSpec(str(eid), "sentinel", 1, 0, "room")
                self.enemy, result = resolve_attack(hit, self.enemy)
                p.attack_after = self.tick + 8
                self.pickup = result.target_dead
            elif action == "take" and self.pickup:
                p.loot, self.pickup = True, False

    def snapshot(self) -> Message:
        return {"v": 1, "type": "state", "tick": self.tick,
                "enemy_hp": int(self.enemy.hp), "pickup": self.pickup,
                "holder": next((eid for eid, p in self.players.items() if p.loot), None),
                "players": [[eid, p.x, p.y] for eid, p in self.players.items()]}
