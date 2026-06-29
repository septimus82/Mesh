"""Runtime shell for monster battles.

This module is the first integration layer for the pure monster battle core.
It owns pause/overlay/event/game-state handoff only; battle math and turn
resolution remain in the pure controller modules.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Mapping

from engine.events import MeshEvent
from engine.ui_overlays.common import UIElement

from .battle_controller import BattleResult, MonsterBattleController, OpponentActionProvider
from .battle_model import MonsterInstance, Move, RandomLike, TypeChart

if TYPE_CHECKING:
    from engine.game import GameWindow


MONSTER_BATTLE_RESULT_KEY = "monster_battle_last_result"
MONSTER_BATTLE_RETURN_CONTEXT_KEY = "monster_battle_return_context"
MONSTER_BATTLE_ENDED_EVENT = "monster_battle_ended"


class MonsterBattleOverlay(UIElement):
    """Minimal placeholder overlay for MON-0d.

    The real HP bars, menus, and move selection arrive in MON-0f. For now this
    surface exists to block gameplay input and provide a visible draw hook.
    """

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self.draw_calls = 0

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
        self.overlay = MonsterBattleOverlay(self.window)
        self.overlay.show()
        self._register_overlay(self.overlay)
        self.active = True
        self.window.paused = True
        self.window.monster_battle_mode_active = True
        return self.controller

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


def start_monster_battle(window: "GameWindow", **kwargs: Any) -> MonsterBattleController:
    """Convenience entrypoint for tests and future runtime triggers."""

    mode = getattr(window, "monster_battle_mode", None)
    if mode is None:
        mode = MonsterBattleMode(window)
        window.monster_battle_mode = mode
    return mode.start_battle(**kwargs)
