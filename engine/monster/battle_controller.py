"""Pure 1v1 monster battle controller state machine.

No GameWindow, scene, save, event-bus, UI, or Arcade dependencies belong here.
The controller orchestrates MON-0a battle math using injected data and RNG.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Literal, Mapping

from .battle_model import MonsterInstance, Move, MoveResolution, RandomLike, TypeChart, resolve_move
from .data_load import MonsterCatalog
from .status import POISON, SLEEP, apply_status, can_act, inflict_event_for, tick_end_of_turn

BattleSideId = Literal["player", "opponent"]
BattlePhase = Literal["choose_action", "resolve", "apply_faints", "won", "lost"]
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
    kind: Literal["move", "status"] = "move"
    move_id: str = ""
    damage: int = 0
    hit: bool = False
    target_fainted: bool = False
    status_event: str = ""
    status_damage: int = 0


@dataclass(frozen=True, slots=True)
class BattleResult:
    outcome: BattleOutcome
    winning_side: BattleSideId
    losing_side: BattleSideId
    turns: int


OpponentActionProvider = Callable[["MonsterBattleController"], MoveAction | str | Move]


class MonsterBattleController:
    """Headless 1v1 monster battle loop.

    ``submit_action("player", move)`` runs one full turn synchronously:
    choose_action -> resolve -> apply_faints -> choose_action/won/lost.
    """

    def __init__(
        self,
        *,
        player: MonsterInstance,
        opponent: MonsterInstance,
        moves: Mapping[str, Move],
        type_chart: TypeChart | None = None,
        rng: RandomLike | None = None,
        opponent_action_provider: OpponentActionProvider | None = None,
    ) -> None:
        self.player = player
        self.opponent = opponent
        self.moves = dict(moves)
        self.type_chart = type_chart
        self.rng = rng
        self.opponent_action_provider = opponent_action_provider
        self.phase: BattlePhase = "choose_action"
        self.turn_number = 1
        self.turn_log: list[BattleLogEntry] = []
        self.result: BattleResult | None = None

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

        if self.result is None:
            self.phase = "choose_action"
            self.turn_number += 1
        return self.result

    def snapshot(self) -> dict[str, object]:
        """Return a deterministic summary useful for tests and future handoff."""

        return {
            "phase": self.phase,
            "turn_number": self.turn_number,
            "player_hp": self.player.current_hp,
            "opponent_hp": self.opponent.current_hp,
            "result": self.result,
            "turn_log": tuple(self.turn_log),
        }

    def _resolve_turn(self, player_action: MoveAction, opponent_action: MoveAction) -> None:
        ordered = sorted(
            (player_action, opponent_action),
            key=lambda action: (-self._monster_for(action.side).stats.spd, 0 if action.side == "player" else 1),
        )
        for action in ordered:
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
            self._set_monster(defender_side, resolution.defender)
            self._append_log(action, resolution)
            if resolution.hit:
                self._try_inflict_status(defender_side, move)

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
        player_fainted = self.player.fainted
        opponent_fainted = self.opponent.fainted
        if opponent_fainted and not player_fainted:
            self.phase = "won"
            self.result = BattleResult("won", winning_side="player", losing_side="opponent", turns=self.turn_number)
        elif player_fainted and not opponent_fainted:
            self.phase = "lost"
            self.result = BattleResult("lost", winning_side="opponent", losing_side="player", turns=self.turn_number)
        elif player_fainted and opponent_fainted:
            # 1v1 deterministic tie-break: player action priority wins simultaneous double-faint.
            self.phase = "won"
            self.result = BattleResult("won", winning_side="player", losing_side="opponent", turns=self.turn_number)

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
        self.turn_log.append(
            BattleLogEntry(
                turn=self.turn_number,
                side=action.side,
                kind="move",
                move_id=action.move_id,
                damage=resolution.damage,
                hit=resolution.hit,
                target_fainted=resolution.fainted,
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
        self.turn_log.append(
            BattleLogEntry(
                turn=self.turn_number,
                side=side,
                kind="status",
                status_event=status_event,
                status_damage=damage,
                target_fainted=target_fainted,
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
            self.player = monster
        else:
            self.opponent = monster

    def _other_side(self, side: BattleSideId) -> BattleSideId:
        return "opponent" if side == "player" else "player"


def controller_from_catalog(
    catalog: MonsterCatalog,
    *,
    player: MonsterInstance,
    opponent: MonsterInstance,
    rng: RandomLike | None = None,
    opponent_action_provider: OpponentActionProvider | None = None,
) -> MonsterBattleController:
    """Convenience constructor that reuses MON-0b catalog data."""

    return MonsterBattleController(
        player=player,
        opponent=opponent,
        moves=catalog.moves,
        type_chart=catalog.type_chart,
        rng=rng,
        opponent_action_provider=opponent_action_provider,
    )
