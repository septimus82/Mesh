"""Runtime shell for monster battles.

This module is the first integration layer for the pure monster battle core.
It owns pause/overlay/event/game-state handoff only; battle math and turn
resolution remain in the pure controller modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping, cast

import engine.optional_arcade as optional_arcade
from engine.events import MeshEvent
from engine.text_draw import TextCache, draw_text_cached
from engine.ui_overlays.common import UIElement, _draw_tb_rectangle_filled, _draw_tb_rectangle_outline

from .battle_controller import BattleLogEntry, BattleResult, MonsterBattleController, OpponentActionProvider
from .battle_model import MonsterInstance, Move, RandomLike, TypeChart, resolve_move
from .capture import CaptureResult, resolve_capture
from .collection import (
    DEFAULT_POCKET_BALL_COUNT,
    add_caught_monster,
    consume_pocket_ball,
    ensure_monster_collection,
    get_pocket_ball_count,
)

if TYPE_CHECKING:
    from engine.game import GameWindow


MONSTER_BATTLE_RESULT_KEY = "monster_battle_last_result"
MONSTER_BATTLE_RETURN_CONTEXT_KEY = "monster_battle_return_context"
MONSTER_BATTLE_ENDED_EVENT = "monster_battle_ended"
MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT = "monster_battle_capture_attempt"

BattleMenuState = Literal["root", "fight", "bag", "presenting", "ended"]
PRESENTATION_STEP_SECONDS = 0.7


@dataclass(frozen=True, slots=True)
class BattlePresentationStep:
    line: str
    player_hp: int
    opponent_hp: int


class MonsterBattleOverlay(UIElement):
    """Minimal keyboard/mouse battle UI for MON-0f."""

    def __init__(self, window: "GameWindow", mode: "MonsterBattleMode") -> None:
        super().__init__(window)
        self.mode = mode
        self.visible = False
        self.draw_calls = 0
        self.menu_state: BattleMenuState = "root"
        self.selected_index = 0
        self.log_line = ""
        self.button_rects: dict[str, tuple[float, float, float, float]] = {}
        self.displayed_player_hp: int | None = None
        self.displayed_opponent_hp: int | None = None
        self.presentation_queue: list[BattlePresentationStep] = []
        self._pending_battle_result: BattleResult | None = None
        self._presentation_elapsed = 0.0
        self._text_cache = TextCache(max_size=256)

    @property
    def blocks_input(self) -> bool:
        return bool(self.visible)

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def draw(self) -> None:
        if not self.visible:
            return
        self.draw_calls += 1
        self._draw_panel()

    def update(self, dt: float) -> None:
        if not self.visible or self.menu_state != "presenting":
            return
        self._presentation_elapsed += max(0.0, float(dt))
        if self._presentation_elapsed >= PRESENTATION_STEP_SECONDS:
            self._advance_presentation()

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        arcade_key = optional_arcade.arcade.key
        if key in (arcade_key.UP, arcade_key.W):
            self._move_selection(-1)
            return True
        if key in (arcade_key.DOWN, arcade_key.S):
            self._move_selection(1)
            return True
        if key in (arcade_key.ENTER, arcade_key.RETURN, arcade_key.SPACE):
            if self.menu_state == "presenting":
                self._advance_presentation()
                return True
            self._activate_selected()
            return True
        if key == arcade_key.ESCAPE:
            self._back()
            return True
        return True

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return True
        for action, rect in list(self.button_rects.items()):
            if _contains(rect, float(x), float(y)):
                self._activate_action(action)
                return True
        return True

    def snapshot(self) -> dict[str, Any]:
        controller = self.mode.controller
        player = controller.player if controller is not None else None
        opponent = controller.opponent if controller is not None else None
        return {
            "visible": self.visible,
            "menu_state": self.menu_state,
            "selected_index": self.selected_index,
            "log_line": self.log_line,
            "player_hp": self.displayed_player_hp if self.displayed_player_hp is not None else getattr(player, "current_hp", None),
            "opponent_hp": self.displayed_opponent_hp if self.displayed_opponent_hp is not None else getattr(opponent, "current_hp", None),
            "presenting": self.menu_state == "presenting",
            "queued_steps": len(self.presentation_queue),
            "buttons": tuple(self.button_rects.keys()),
        }

    def set_intro_log(self) -> None:
        controller = self.mode.controller
        if controller is None:
            self.log_line = "A wild monster appeared!"
            return
        name = _display_name(controller.opponent)
        self.log_line = f"A wild {name} appeared!"
        self.sync_displayed_hp()

    def sync_displayed_hp(self) -> None:
        controller = self.mode.controller
        if controller is None:
            return
        self.displayed_player_hp = int(controller.player.current_hp)
        self.displayed_opponent_hp = int(controller.opponent.current_hp)

    def begin_turn_presentation(
        self,
        steps: list[BattlePresentationStep],
        *,
        result: BattleResult | None,
    ) -> None:
        self.menu_state = "presenting"
        self.selected_index = 0
        self.button_rects.clear()
        self.presentation_queue = list(steps)
        self._pending_battle_result = result
        self._presentation_elapsed = 0.0
        self.log_line = "..."
        if not self.presentation_queue:
            self._finish_presentation()

    def _draw_panel(self) -> None:
        width = float(getattr(self.window, "width", 1280) or 1280)
        height = float(getattr(self.window, "height", 720) or 720)
        left = width * 0.12
        right = width * 0.88
        top = height * 0.86
        bottom = height * 0.12
        _draw_tb_rectangle_filled(left, right, top, bottom, (16, 18, 28, 230))
        _draw_tb_rectangle_outline(left, right, top, bottom, (230, 230, 245, 255), 2)
        self.button_rects.clear()
        self._draw_combatants(left, right, top)
        draw_text_cached(
            self.log_line or "Choose an action.",
            left + 24,
            bottom + 118,
            color=(245, 245, 245, 255),
            font_size=14,
            cache=self._text_cache,
        )
        self._draw_menu(left + 24, bottom + 24)

    def _draw_combatants(self, left: float, right: float, top: float) -> None:
        controller = self.mode.controller
        if controller is None:
            return
        self._draw_monster_block(
            controller.opponent,
            left + 24,
            top - 48,
            width=360,
            hp=self.displayed_opponent_hp,
        )
        self._draw_monster_block(
            controller.player,
            right - 384,
            top - 190,
            width=360,
            hp=self.displayed_player_hp,
        )

    def _draw_monster_block(self, monster: MonsterInstance, x: float, y: float, *, width: float, hp: int | None = None) -> None:
        name = _display_name(monster)
        max_hp = max(1, int(monster.stats.hp if monster.stats else monster.current_hp or 1))
        hp = max(0, int(monster.current_hp if hp is None else hp))
        ratio = max(0.0, min(1.0, hp / max_hp))
        draw_text_cached(f"{name}  Lv.{monster.level}", x, y, color=(255, 255, 255, 255), font_size=15, cache=self._text_cache)
        bar_top = y - 24
        _draw_tb_rectangle_filled(x, x + width, bar_top, bar_top - 16, (55, 55, 65, 255))
        _draw_tb_rectangle_filled(x, x + (width * ratio), bar_top, bar_top - 16, (80, 210, 110, 255))
        _draw_tb_rectangle_outline(x, x + width, bar_top, bar_top - 16, (230, 230, 240, 255), 1)
        draw_text_cached(f"HP {hp}/{max_hp}", x, bar_top - 38, color=(220, 220, 230, 255), font_size=12, cache=self._text_cache)

    def _draw_menu(self, x: float, y: float) -> None:
        for index, (action, label) in enumerate(self._current_actions()):
            rect = (x + (index % 2) * 170, y + (1 - index // 2) * 42, 150, 32)
            self.button_rects[action] = rect
            color = (250, 240, 160, 255) if index == self.selected_index else (220, 220, 230, 255)
            _draw_button(rect, label, color, self._text_cache)

    def _current_actions(self) -> list[tuple[str, str]]:
        if self.menu_state == "presenting":
            return []
        if self.menu_state == "fight":
            controller = self.mode.controller
            if controller is None:
                return []
            actions: list[tuple[str, str]] = []
            for move_id in controller.player.known_moves or controller.player.species.learnset:
                move = controller.moves.get(move_id)
                if move is None:
                    continue
                actions.append((f"move:{move.id}", f"{move.id} {move.type} PP {move.pp}"))
            return actions or [("back", "Back")]
        if self.menu_state == "bag":
            return [("capture:pocket_ball", f"Pocket Ball x{self.mode.pocket_ball_count()}"), ("back", "Back")]
        if self.menu_state == "ended":
            return [("close", "Close")]
        return [("menu:fight", "Fight"), ("menu:bag", "Bag"), ("run", "Run")]

    def _move_selection(self, delta: int) -> None:
        actions = self._current_actions()
        if not actions:
            self.selected_index = 0
            return
        self.selected_index = (self.selected_index + int(delta)) % len(actions)

    def _activate_selected(self) -> None:
        actions = self._current_actions()
        if not actions:
            return
        self._activate_action(actions[self.selected_index][0])

    def _activate_action(self, action: str) -> None:
        if self.menu_state == "presenting":
            return
        if action == "menu:fight":
            self.menu_state = "fight"
            self.selected_index = 0
            self.log_line = "Choose a move."
            return
        if action == "menu:bag":
            self.menu_state = "bag"
            self.selected_index = 0
            self.log_line = "Choose an item."
            return
        if action == "back":
            self._back()
            return
        if action.startswith("move:"):
            self.mode.submit_player_move(action.split(":", 1)[1])
            self.selected_index = 0
            return
        if action.startswith("capture:"):
            self.mode.attempt_capture(item_id=action.split(":", 1)[1])
            self.selected_index = 0
            return
        if action == "run":
            self.mode.run_from_battle()
            self.menu_state = "ended"
            return
        if action == "close":
            self.hide()

    def _back(self) -> None:
        if self.menu_state == "presenting":
            return
        if self.menu_state in {"fight", "bag"}:
            self.menu_state = "root"
            self.selected_index = 0
            self.log_line = "Choose an action."
        else:
            self.log_line = "Choose an action."

    def _advance_presentation(self) -> None:
        self._presentation_elapsed = 0.0
        if self.presentation_queue:
            step = self.presentation_queue.pop(0)
            self.log_line = step.line
            self.displayed_player_hp = step.player_hp
            self.displayed_opponent_hp = step.opponent_hp
            return
        self._finish_presentation()

    def _finish_presentation(self) -> None:
        result = self._pending_battle_result
        self._pending_battle_result = None
        self._presentation_elapsed = 0.0
        if result is not None and self.mode.active:
            self.menu_state = "ended"
            self.mode.complete_presented_battle(result)
            return
        self.menu_state = "root"
        self.selected_index = 0


class MonsterBattleMode:
    """GameWindow-owned monster battle runtime mode."""

    def __init__(self, window: "GameWindow") -> None:
        self.window = window
        self.controller: MonsterBattleController | None = None
        self.overlay: MonsterBattleOverlay | None = None
        self.return_context: dict[str, Any] = {}
        self._prior_paused = False
        self.active = False

    def start_battle(
        self,
        *,
        player_monster: MonsterInstance,
        opponent_monster: MonsterInstance,
        moves: Mapping[str, Move],
        return_context: Mapping[str, Any] | None = None,
        type_chart: TypeChart | None = None,
        rng: RandomLike | None = None,
        opponent_action_provider: OpponentActionProvider | None = None,
    ) -> MonsterBattleController:
        """Enter battle mode and return the created pure controller."""

        if self.active:
            raise RuntimeError("monster battle mode is already active")

        self._prior_paused = bool(getattr(self.window, "paused", False))
        self.return_context = dict(return_context or {})
        self.controller = MonsterBattleController(
            player=player_monster,
            opponent=opponent_monster,
            moves=moves,
            type_chart=type_chart,
            rng=rng,
            opponent_action_provider=opponent_action_provider,
        )
        self._ensure_collection_state()
        self.overlay = MonsterBattleOverlay(self.window, self)
        self.overlay.show()
        self.overlay.set_intro_log()
        self._register_overlay(self.overlay)
        self.active = True
        self.window.paused = True
        self.window.monster_battle_mode_active = True
        return self.controller

    def submit_player_move(self, move_id: str) -> BattleResult | None:
        if not self.active or self.controller is None:
            raise RuntimeError("monster battle mode is not active")
        before_player_hp = int(
            self.overlay.displayed_player_hp
            if self.overlay is not None and self.overlay.displayed_player_hp is not None
            else self.controller.player.current_hp,
        )
        before_opponent_hp = int(
            self.overlay.displayed_opponent_hp
            if self.overlay is not None and self.overlay.displayed_opponent_hp is not None
            else self.controller.opponent.current_hp,
        )
        before_len = len(self.controller.turn_log)
        result = self.controller.submit_action("player", str(move_id))
        if self.overlay is not None:
            steps = self._build_presentation_steps(before_len, before_player_hp, before_opponent_hp)
            self.overlay.begin_turn_presentation(steps, result=result)
        elif result is not None:
            self.end_battle(result)
        return result

    def complete_presented_battle(self, result: BattleResult) -> BattleResult:
        """End a completed battle after the overlay has shown its final line."""

        return self.end_battle(result)

    def attempt_capture(self, *, item_id: str = "pocket_ball") -> CaptureResult | None:
        if not self.active or self.controller is None:
            raise RuntimeError("monster battle mode is not active")
        values = self._state_values()
        balls_before = get_pocket_ball_count(values)
        if not consume_pocket_ball(values):
            self._emit_capture_attempt(
                {
                    "item_id": str(item_id),
                    "species_id": self.controller.opponent.species.id,
                    "level": self.controller.opponent.level,
                    "caught": False,
                    "blocked": True,
                    "balls_before": balls_before,
                    "balls_remaining": 0,
                    "return_context": dict(self.return_context),
                },
            )
            if self.overlay is not None:
                self.overlay.log_line = "No Pocket Balls left!"
                self.overlay.menu_state = "bag"
            return None
        capture = resolve_capture(self.controller.opponent, ball_bonus=1.0, rng=self._capture_rng())
        payload = {
            "item_id": str(item_id),
            "species_id": self.controller.opponent.species.id,
            "level": self.controller.opponent.level,
            "caught": capture.caught,
            "roll": capture.roll,
            "chance": capture.chance,
            "balls_remaining": get_pocket_ball_count(values),
            "return_context": dict(self.return_context),
        }
        self._emit_capture_attempt(payload)
        if capture.caught:
            caught = add_caught_monster(values, self.controller.opponent)
            result = BattleResult(
                cast(Any, "caught"),
                winning_side="player",
                losing_side="opponent",
                turns=self.controller.turn_number,
            )
            if self.overlay is not None:
                self.overlay.log_line = f"Gotcha! {_display_name(self.controller.opponent)} was caught."
            self.return_context.update({"caught_instance_id": caught.instance_id, "caught_storage": caught.storage})
            self.end_battle(result)
            return capture

        self._resolve_failed_capture_response(item_id=item_id, capture=capture)
        return capture

    def pocket_ball_count(self) -> int:
        return get_pocket_ball_count(self._state_values())

    def run_from_battle(self) -> BattleResult:
        if not self.active or self.controller is None:
            raise RuntimeError("monster battle mode is not active")
        result = BattleResult(
            cast(Any, "ran"),
            winning_side="opponent",
            losing_side="player",
            turns=self.controller.turn_number,
        )
        if self.overlay is not None:
            self.overlay.log_line = "Got away safely!"
        self.end_battle(result)
        return result

    def end_battle(self, result: BattleResult | None = None) -> BattleResult:
        """Apply result, remove overlay, clear mode, and restore prior pause."""

        if not self.active or self.controller is None:
            raise RuntimeError("monster battle mode is not active")

        final_result = result or self.controller.result
        if final_result is None:
            raise RuntimeError("cannot end monster battle without a result")

        payload = self._result_payload(final_result)
        self._apply_result_payload(payload)
        self._emit_ended(payload)

        if self.overlay is not None:
            self.overlay.hide()
            self._unregister_overlay(self.overlay)

        self.controller = None
        self.overlay = None
        self.return_context = {}
        self.active = False
        self.window.monster_battle_mode_active = False
        self.window.paused = self._prior_paused
        return final_result

    def _register_overlay(self, overlay: MonsterBattleOverlay) -> None:
        ui_controller = getattr(self.window, "ui_controller", None)
        register = getattr(ui_controller, "register_ui_element", None)
        if callable(register):
            register(overlay)

    def _unregister_overlay(self, overlay: MonsterBattleOverlay) -> None:
        ui_controller = getattr(self.window, "ui_controller", None)
        elements = getattr(ui_controller, "ui_elements", None)
        if isinstance(elements, list) and overlay in elements:
            elements.remove(overlay)

    def _result_payload(self, result: BattleResult) -> dict[str, Any]:
        payload = asdict(result)
        payload["return_context"] = dict(self.return_context)
        return payload

    def _apply_result_payload(self, payload: dict[str, Any]) -> None:
        controller = getattr(self.window, "game_state_controller", None)
        state = getattr(controller, "state", None)
        values = getattr(state, "values", None)
        if isinstance(values, dict):
            values[MONSTER_BATTLE_RESULT_KEY] = dict(payload)
            values[MONSTER_BATTLE_RETURN_CONTEXT_KEY] = dict(payload.get("return_context", {}))

    def _state_values(self) -> dict[str, Any]:
        controller = getattr(self.window, "game_state_controller", None)
        state = getattr(controller, "state", None)
        values = getattr(state, "values", None)
        if not isinstance(values, dict):
            values = {}
            if state is not None:
                state.values = values
                state.variables = values
        ensure_monster_collection(values)
        return values

    def _ensure_collection_state(self) -> None:
        values = self._state_values()
        values.setdefault("pocket_ball_count", DEFAULT_POCKET_BALL_COUNT)
        ensure_monster_collection(values)

    def _capture_rng(self) -> RandomLike:
        if self.controller is not None and self.controller.rng is not None:
            return self.controller.rng
        import random  # noqa: PLC0415

        rng = random.Random(0)
        if self.controller is not None:
            self.controller.rng = rng
        return rng

    def _emit_ended(self, payload: dict[str, Any]) -> None:
        emitter = getattr(self.window, "emit_event", None)
        event = MeshEvent(MONSTER_BATTLE_ENDED_EVENT, dict(payload))
        if callable(emitter):
            emitter(event)
            return
        event_bus = getattr(self.window, "event_bus", None)
        emit_event = getattr(event_bus, "emit_event", None)
        if callable(emit_event):
            emit_event(event)

    def _emit_capture_attempt(self, payload: dict[str, Any]) -> None:
        emitter = getattr(self.window, "emit_event", None)
        event = MeshEvent(MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT, dict(payload))
        if callable(emitter):
            emitter(event)
            return
        event_bus = getattr(self.window, "event_bus", None)
        emit_event = getattr(event_bus, "emit_event", None)
        if callable(emit_event):
            emit_event(event)

    def _build_presentation_steps(
        self,
        before_len: int,
        before_player_hp: int,
        before_opponent_hp: int,
    ) -> list[BattlePresentationStep]:
        if self.controller is None:
            return []
        entries = self.controller.turn_log[before_len:]
        if not entries:
            return [BattlePresentationStep("Nothing happened.", before_player_hp, before_opponent_hp)]
        player_hp = int(before_player_hp)
        opponent_hp = int(before_opponent_hp)
        steps: list[BattlePresentationStep] = []
        for entry in entries:
            if entry.side == "player":
                actor = _display_name(self.controller.player)
                target = _display_name(self.controller.opponent)
                if entry.hit:
                    opponent_hp = max(0, opponent_hp - int(entry.damage))
            else:
                actor = _display_name(self.controller.opponent)
                target = _display_name(self.controller.player)
                if entry.hit:
                    player_hp = max(0, player_hp - int(entry.damage))
            if entry.hit:
                line = f"{actor} used {entry.move_id}! {target} took {entry.damage} damage."
            else:
                line = f"{actor} used {entry.move_id}, but it missed!"
            steps.append(BattlePresentationStep(line, player_hp, opponent_hp))
            if entry.target_fainted:
                steps.append(BattlePresentationStep(f"{target} fainted!", player_hp, opponent_hp))
        return steps

    def _resolve_failed_capture_response(self, *, item_id: str, capture: CaptureResult) -> None:
        if self.controller is None or self.overlay is None:
            return
        before_player_hp = int(self.overlay.displayed_player_hp if self.overlay.displayed_player_hp is not None else self.controller.player.current_hp)
        before_opponent_hp = int(
            self.overlay.displayed_opponent_hp if self.overlay.displayed_opponent_hp is not None else self.controller.opponent.current_hp,
        )
        try:
            opponent_action = self.controller._choose_opponent_action()
            move = self.controller._require_move(opponent_action.move_id)
        except Exception:  # noqa: BLE001  # REASON: failed capture should still return control if no opponent move is available
            self.overlay.begin_turn_presentation(
                [
                    BattlePresentationStep(
                        f"Threw {item_id}! {_display_name(self.controller.opponent)} broke free.",
                        before_player_hp,
                        before_opponent_hp,
                    )
                ],
                result=None,
            )
            return

        resolution = resolve_move(
            self.controller.opponent,
            self.controller.player,
            move,
            self.controller.type_chart,
            self.controller.rng,
        )
        self.controller.player = resolution.defender
        self.controller.turn_log.append(
            BattleLogEntry(
                turn=self.controller.turn_number,
                side="opponent",
                move_id=move.id,
                damage=resolution.damage,
                hit=resolution.hit,
                target_fainted=resolution.fainted,
            ),
        )
        result = None
        if self.controller.player.fainted:
            self.controller.result = BattleResult("lost", winning_side="opponent", losing_side="player", turns=self.controller.turn_number)
            self.controller.phase = "lost"
            result = self.controller.result
        else:
            self.controller.turn_number += 1
            self.controller.phase = "choose_action"

        steps = [
            BattlePresentationStep(
                f"Threw {item_id}! {_display_name(self.controller.opponent)} broke free.",
                before_player_hp,
                before_opponent_hp,
            ),
        ]
        steps.extend(self._build_presentation_steps(len(self.controller.turn_log) - 1, before_player_hp, before_opponent_hp))
        self.overlay.begin_turn_presentation(steps, result=result)


def start_monster_battle(window: "GameWindow", **kwargs: Any) -> MonsterBattleController:
    """Convenience entrypoint for tests and future runtime triggers."""

    mode = getattr(window, "monster_battle_mode", None)
    if mode is None:
        mode = MonsterBattleMode(window)
        window.monster_battle_mode = mode
    return mode.start_battle(**kwargs)


def _display_name(monster: MonsterInstance) -> str:
    raw = monster.species.id.replace("_", " ").replace("-", " ")
    return raw.title()


def _contains(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    left, bottom, width, height = rect
    return left <= x <= left + width and bottom <= y <= bottom + height


def _draw_button(rect: tuple[float, float, float, float], label: str, color: Any, cache: TextCache) -> None:
    left, bottom, width, height = rect
    _draw_tb_rectangle_filled(left, left + width, bottom + height, bottom, (36, 40, 56, 245))
    _draw_tb_rectangle_outline(left, left + width, bottom + height, bottom, (210, 210, 230, 255), 1)
    draw_text_cached(
        label,
        left + 10,
        bottom + 9,
        color=color,
        font_size=11,
        cache=cache,
    )
