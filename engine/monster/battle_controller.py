"""Pure 1v1 monster battle controller state machine.

No GameWindow, scene, save, event-bus, UI, or Arcade dependencies belong here.
The controller orchestrates MON-0a battle math using injected data and RNG.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Literal, Mapping, Sequence

from .battle_model import MonsterInstance, Move, MoveResolution, RandomLike, TypeChart, resolve_move
from .data_load import MonsterCatalog
from .status import POISON, SLEEP, apply_status, can_act, inflict_event_for, tick_end_of_turn

BattleSideId = Literal["player", "opponent"]
BattlePhase = Literal["choose_action", "resolve", "apply_faints", "must_switch", "won", "lost"]
BattleOutcome = Literal["won", "lost"]


class InvalidBattleActionError(ValueError):
    """Raised when an action is submitted outside the legal controller phase."""


@dataclass(frozen=True, slots=True)
class MoveAction:
    side: BattleSideId
    move_id: str


@dataclass(frozen=True, slots=True)
class BattleLogEntry:
    turn: int
    side: BattleSideId
    kind: Literal["move", "status", "switch"] = "move"
    move_id: str = ""
    damage: int = 0
    hit: bool = False
    target_fainted: bool = False
    status_event: str = ""
    status_damage: int = 0
    switch_kind: str = ""
    party_index: int = -1


@dataclass(frozen=True, slots=True)
class BattleResult:
    outcome: BattleOutcome
    winning_side: BattleSideId
    losing_side: BattleSideId
    turns: int


OpponentActionProvider = Callable[["MonsterBattleController"], MoveAction | str | Move]


class MonsterBattleController:
    """Headless monster battle loop with multi-monster player and opponent parties."""

    def __init__(
        self,
        *,
        player: MonsterInstance,
        opponent: MonsterInstance,
        moves: Mapping[str, Move],
        player_party: Sequence[MonsterInstance] | None = None,
        active_index: int = 0,
        opponent_party: Sequence[MonsterInstance] | None = None,
        opponent_active_index: int = 0,
        type_chart: TypeChart | None = None,
        rng: RandomLike | None = None,
        opponent_action_provider: OpponentActionProvider | None = None,
    ) -> None:
        party = list(player_party) if player_party is not None else [player]
        if not party:
            party = [player]
        index = max(0, min(int(active_index), len(party) - 1))
        self.player_party = list(party)
        self.player_party[index] = player
        self.active_index = index
        self.player = self.player_party[self.active_index]

        opp_party = list(opponent_party) if opponent_party is not None else [opponent]
        if not opp_party:
            opp_party = [opponent]
        opp_index = max(0, min(int(opponent_active_index), len(opp_party) - 1))
        self.opponent_party = list(opp_party)
        self.opponent_party[opp_index] = opponent
        self.opponent_active_index = opp_index
        self.opponent = self.opponent_party[self.opponent_active_index]

        self.moves = dict(moves)
        self.type_chart = type_chart
        self.rng = rng
        self.opponent_action_provider = opponent_action_provider
        self.phase: BattlePhase = "choose_action"
        self.turn_number = 1
        self.turn_log: list[BattleLogEntry] = []
        self.result: BattleResult | None = None
        self._guarding_this_turn = False

    def submit_action(self, side: BattleSideId, move: Move | str) -> BattleResult | None:
        """Submit a move for the player side and resolve a full turn."""

        if self.phase != "choose_action":
            raise InvalidBattleActionError(f"Cannot submit action while battle phase is '{self.phase}'")
        if self.result is not None:
            raise InvalidBattleActionError("Cannot submit action after battle is complete")
        if side != "player":
            raise InvalidBattleActionError("MON-0c accepts submitted actions for the player side only")

        player_action = MoveAction(side="player", move_id=self._move_id(move))
        opponent_action = self._choose_opponent_action()

        self.phase = "resolve"
        self._resolve_turn(player_action, opponent_action)

        self.phase = "apply_faints"
        self._apply_faints()

        if self.result is None and self.phase != "must_switch":
            self.phase = "choose_action"
            self.turn_number += 1
        return self.result

    def submit_switch(self, party_index: int) -> BattleResult | None:
        """Switch the active player monster. Forced switches are free; voluntary switches cost the turn."""

        if self.phase not in {"choose_action", "must_switch"}:
            raise InvalidBattleActionError(f"Cannot switch while battle phase is '{self.phase}'")
        if self.result is not None:
            raise InvalidBattleActionError("Cannot switch after battle is complete")

        index = int(party_index)
        if index < 0 or index >= len(self.player_party):
            raise InvalidBattleActionError(f"Invalid party index '{party_index}'")
        if index == self.active_index:
            raise InvalidBattleActionError("That monster is already active")
        if self.player_party[index].fainted:
            raise InvalidBattleActionError("Cannot switch to a fainted monster")

        forced = self.phase == "must_switch"
        old_index = self.active_index
        self.active_index = index
        self.player = self.player_party[index]
        if not forced:
            self._append_switch_log("player", old_index, kind="recall")
        self._append_switch_log("player", index, kind="send_out")

        if forced:
            self.phase = "choose_action"
            return self.result

        opponent_action = self._choose_opponent_action()
        self.phase = "resolve"
        self._resolve_actions((opponent_action,))
        self._apply_end_of_turn_ticks()

        self.phase = "apply_faints"
        self._apply_faints()

        if self.result is None and self.phase != "must_switch":
            self.phase = "choose_action"
            self.turn_number += 1
        return self.result

    def submit_player_pass_turn(self, *, guarding: bool = False) -> BattleResult | None:
        """Skip the player's action and let the opponent act (companion hesitate/defend)."""

        if self.phase != "choose_action":
            raise InvalidBattleActionError(f"Cannot pass while battle phase is '{self.phase}'")
        if self.result is not None:
            raise InvalidBattleActionError("Cannot pass after battle is complete")

        self._guarding_this_turn = bool(guarding)
        try:
            opponent_action = self._choose_opponent_action()
            self.phase = "resolve"
            self._resolve_actions((opponent_action,))
            self._apply_end_of_turn_ticks()
            self.phase = "apply_faints"
            self._apply_faints()
            if self.result is None and self.phase != "must_switch":
                self.phase = "choose_action"
                self.turn_number += 1
            return self.result
        finally:
            self._guarding_this_turn = False

    def snapshot(self) -> dict[str, object]:
        """Return a deterministic summary useful for tests and future handoff."""

        return {
            "phase": self.phase,
            "turn_number": self.turn_number,
            "player_hp": self.player.current_hp,
            "opponent_hp": self.opponent.current_hp,
            "active_index": self.active_index,
            "party_size": len(self.player_party),
            "opponent_active_index": self.opponent_active_index,
            "opponent_party_size": len(self.opponent_party),
            "result": self.result,
            "turn_log": tuple(self.turn_log),
        }

    def _resolve_turn(self, player_action: MoveAction, opponent_action: MoveAction) -> None:
        ordered = sorted(
            (player_action, opponent_action),
            key=lambda action: (-self._monster_for(action.side).stats.spd, 0 if action.side == "player" else 1),
        )
        self._resolve_actions(ordered)
        self._apply_end_of_turn_ticks()

    def _resolve_actions(self, actions: Sequence[MoveAction]) -> None:
        for action in actions:
            attacker_side = action.side
            attacker = self._monster_for(attacker_side)
            if attacker.fainted:
                continue

            may_act, status_events, attacker = can_act(attacker, self.rng)
            self._set_monster(attacker_side, attacker)
            for event in status_events:
                self._append_status_log(attacker_side, event.kind)
            if not may_act:
                continue

            defender_side = self._other_side(attacker_side)
            defender = self._monster_for(defender_side)
            if defender.fainted:
                continue
            move = self._require_move(action.move_id)
            resolution = resolve_move(attacker, defender, move, self.type_chart, self.rng)
            if self._guarding_this_turn and defender_side == "player" and resolution.hit:
                full_damage = int(resolution.damage)
                guarded_damage = max(0, int(full_damage * 0.75))
                if guarded_damage != full_damage:
                    healed_hp = min(
                        defender.stats.hp if defender.stats else guarded_damage + (resolution.defender.current_hp or 0),
                        (resolution.defender.current_hp or 0) + (full_damage - guarded_damage),
                    )
                    resolution = replace(
                        resolution,
                        damage=guarded_damage,
                        defender=replace(resolution.defender, current_hp=healed_hp),
                        fainted=healed_hp <= 0,
                    )
            self._set_monster(defender_side, resolution.defender)
            self._append_log(action, resolution)
            if resolution.hit:
                self._try_inflict_status(defender_side, move)

    def _apply_end_of_turn_ticks(self) -> None:
        for side in ("player", "opponent"):
            monster = self._monster_for(side)
            if monster.fainted:
                continue
            updated, tick_events = tick_end_of_turn(monster)
            self._set_monster(side, updated)
            for event in tick_events:
                self._append_status_log(
                    side,
                    event.kind,
                    damage=event.damage,
                    target_fainted=updated.fainted and event.kind == "poison_damage",
                )

    def _try_inflict_status(self, defender_side: BattleSideId, move: Move) -> None:
        inflict = move.status_inflict
        if inflict is None or inflict.condition not in {POISON, SLEEP}:
            return
        roll = 0.0 if self.rng is None else float(self.rng.random())
        if roll >= float(inflict.chance):
            return
        defender = self._monster_for(defender_side)
        updated = apply_status(defender, inflict.condition)
        self._set_monster(defender_side, updated)
        self._append_status_log(defender_side, inflict_event_for(inflict.condition))

    def _apply_faints(self) -> None:
        self._auto_switch_opponent_if_needed()

        opponent_all_fainted = all(monster.fainted for monster in self.opponent_party)
        player_all_fainted = all(monster.fainted for monster in self.player_party)

        if opponent_all_fainted:
            self.phase = "won"
            self.result = BattleResult("won", winning_side="player", losing_side="opponent", turns=self.turn_number)
            return

        if player_all_fainted:
            self.phase = "lost"
            self.result = BattleResult("lost", winning_side="opponent", losing_side="player", turns=self.turn_number)
            return

        if self.player.fainted and self._has_player_bench():
            self.phase = "must_switch"

    def _auto_switch_opponent_if_needed(self) -> None:
        if not self.opponent.fainted:
            return
        if all(monster.fainted for monster in self.opponent_party):
            return
        next_index = self._next_opponent_bench_index()
        if next_index is None:
            return
        self.opponent_active_index = next_index
        self.opponent = self.opponent_party[next_index]
        self._append_switch_log("opponent", next_index, kind="send_out")

    def _next_opponent_bench_index(self) -> int | None:
        count = len(self.opponent_party)
        for offset in range(1, count):
            index = (self.opponent_active_index + offset) % count
            if not self.opponent_party[index].fainted:
                return index
        return None

    def _has_player_bench(self) -> bool:
        return any(not monster.fainted for index, monster in enumerate(self.player_party) if index != self.active_index)

    def _choose_opponent_action(self) -> MoveAction:
        if self.opponent_action_provider is not None:
            provided = self.opponent_action_provider(self)
            if isinstance(provided, MoveAction):
                if provided.side != "opponent":
                    return replace(provided, side="opponent")
                return provided
            return MoveAction(side="opponent", move_id=self._move_id(provided))

        for move_id in self.opponent.known_moves:
            if move_id in self.moves:
                return MoveAction(side="opponent", move_id=move_id)
        for move_id in self.opponent.species.learnset:
            if move_id in self.moves:
                return MoveAction(side="opponent", move_id=move_id)
        if self.moves:
            return MoveAction(side="opponent", move_id=sorted(self.moves)[0])
        raise InvalidBattleActionError("Opponent has no usable move")

    def _append_log(self, action: MoveAction, resolution: MoveResolution) -> None:
        fainted_index = -1
        if resolution.fainted:
            fainted_index = self.opponent_active_index if action.side == "player" else self.active_index
        self.turn_log.append(
            BattleLogEntry(
                turn=self.turn_number,
                side=action.side,
                kind="move",
                move_id=action.move_id,
                damage=resolution.damage,
                hit=resolution.hit,
                target_fainted=resolution.fainted,
                party_index=fainted_index,
            ),
        )

    def _append_switch_log(self, side: BattleSideId, party_index: int, *, kind: str) -> None:
        self.turn_log.append(
            BattleLogEntry(
                turn=self.turn_number,
                side=side,
                kind="switch",
                switch_kind=kind,
                party_index=int(party_index),
            ),
        )

    def _append_status_log(
        self,
        side: BattleSideId,
        status_event: str,
        *,
        damage: int = 0,
        target_fainted: bool = False,
    ) -> None:
        fainted_index = -1
        if target_fainted:
            fainted_index = self.opponent_active_index if side == "opponent" else self.active_index
        self.turn_log.append(
            BattleLogEntry(
                turn=self.turn_number,
                side=side,
                kind="status",
                status_event=status_event,
                status_damage=damage,
                target_fainted=target_fainted,
                party_index=fainted_index,
            ),
        )

    def _move_id(self, move: Move | str) -> str:
        return move.id if isinstance(move, Move) else str(move)

    def _require_move(self, move_id: str) -> Move:
        try:
            return self.moves[move_id]
        except KeyError as exc:
            raise InvalidBattleActionError(f"Unknown move id '{move_id}'") from exc

    def _monster_for(self, side: BattleSideId) -> MonsterInstance:
        return self.player if side == "player" else self.opponent

    def _set_monster(self, side: BattleSideId, monster: MonsterInstance) -> None:
        if side == "player":
            self.player_party[self.active_index] = monster
            self.player = monster
        else:
            self.opponent_party[self.opponent_active_index] = monster
            self.opponent = monster

    def _other_side(self, side: BattleSideId) -> BattleSideId:
        return "opponent" if side == "player" else "player"


def controller_from_catalog(
    catalog: MonsterCatalog,
    *,
    player: MonsterInstance,
    opponent: MonsterInstance,
    player_party: Sequence[MonsterInstance] | None = None,
    active_index: int = 0,
    opponent_party: Sequence[MonsterInstance] | None = None,
    opponent_active_index: int = 0,
    rng: RandomLike | None = None,
    opponent_action_provider: OpponentActionProvider | None = None,
) -> MonsterBattleController:
    """Convenience constructor that reuses MON-0b catalog data."""

    return MonsterBattleController(
        player=player,
        opponent=opponent,
        player_party=player_party,
        active_index=active_index,
        opponent_party=opponent_party,
        opponent_active_index=opponent_active_index,
        moves=catalog.moves,
        type_chart=catalog.type_chart,
        rng=rng,
        opponent_action_provider=opponent_action_provider,
    )
