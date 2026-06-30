"""Runtime shell for monster battles.

This module is the first integration layer for the pure monster battle core.
It owns pause/overlay/event/game-state handoff only; battle math and turn
resolution remain in the pure controller modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence, cast

import engine.optional_arcade as optional_arcade
from engine.events import MeshEvent
from engine.text_draw import TextCache, draw_text_cached
from engine.ui.menu_toolkit import MenuStackOverlay, SelectableItem, SelectableListScreen
from engine.ui_overlays.common import UIElement, _draw_tb_rectangle_filled, _draw_tb_rectangle_outline

from .battle_controller import BattleLogEntry, BattleResult, MonsterBattleController, OpponentActionProvider
from .battle_model import MonsterInstance, Move, RandomLike, Species, TypeChart, resolve_move
from .battle_sprite_view import BattleSpriteDisplay
from .capture import CaptureResult, resolve_capture
from .collection import (
    COMPANION_MIND_INSTANCE_KEY,
    DEFAULT_POCKET_BALL_COUNT,
    MAX_PARTY_SIZE,
    MONSTER_BOX_KEY,
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    add_caught_monster,
    consume_pocket_ball,
    ensure_monster_collection,
    get_pocket_ball_count,
    load_companion_mind_for_instance,
    persist_companion_mind,
    serialize_monster_instance,
)
from .companion_mind import (
    ATTACK,
    DEFEND,
    FLEE,
    CompanionMind,
    DecisionContext,
    decide,
    praise,
    scold,
    wait,
)
from .progression import apply_experience, award_xp_for_victory

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
    player_clip: str | None = None
    opponent_clip: str | None = None


def _battle_combatant_layout(left: float, right: float, top: float) -> dict[str, tuple[float, float]]:
    """Sprite and HP anchor positions for classic JRPG side alignment."""

    return {
        "opponent_sprite": (left + 204.0, top - 175.0),
        "player_sprite": (right - 204.0, top - 317.0),
        "opponent_hp": (left + 24.0, top - 48.0),
        "player_hp": (right - 384.0, top - 190.0),
    }


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
        self._player_sprite = BattleSpriteDisplay(window)
        self._opponent_sprite = BattleSpriteDisplay(window)

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
        if not self.visible:
            return
        self._sync_battle_sprites_if_needed()
        self._player_sprite.update(dt)
        self._opponent_sprite.update(dt)
        if self.menu_state != "presenting":
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
        if self.mode.companion_mode:
            name = _display_name(controller.player)
            self.log_line = f"Go, {name}! Your companion is ready."
        else:
            name = _display_name(controller.opponent)
            self.log_line = f"A wild {name} appeared!"
        self.sync_displayed_hp()
        self.sync_battle_sprites()

    def sync_battle_sprites(self) -> None:
        controller = self.mode.controller
        if controller is None:
            self._player_sprite.reload(_empty_species())
            self._opponent_sprite.reload(_empty_species())
            return
        self._player_sprite.reload(controller.player.species)
        self._opponent_sprite.reload(controller.opponent.species)

    def _sync_battle_sprites_if_needed(self) -> None:
        controller = self.mode.controller
        if controller is None:
            return
        player_id = controller.player.species.id
        opponent_id = controller.opponent.species.id
        if self._player_sprite.species_id != player_id:
            self._player_sprite.reload(controller.player.species)
        if self._opponent_sprite.species_id != opponent_id:
            self._opponent_sprite.reload(controller.opponent.species)

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
        layout = _battle_combatant_layout(left, right, top)
        self._opponent_sprite.draw(*layout["opponent_sprite"])
        self._player_sprite.draw(*layout["player_sprite"])
        self._draw_monster_block(
            controller.opponent,
            *layout["opponent_hp"],
            width=360,
            hp=self.displayed_opponent_hp,
        )
        self._draw_monster_block(
            controller.player,
            *layout["player_hp"],
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
        if self.mode.companion_mode and self.mode.companion_awaiting_reinforcement:
            return [
                ("companion:praise", "Praise"),
                ("companion:scold", "Scold"),
                ("companion:wait", "Wait"),
            ]
        return [("menu:fight", "Fight"), ("menu:bag", "Bag"), ("menu:switch", "Switch"), ("run", "Run")]

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
        if action == "menu:switch":
            self.mode.open_switch_screen(forced=False)
            return
        if action == "companion:praise":
            self.mode.submit_companion_reinforcement("praise")
            self.selected_index = 0
            return
        if action == "companion:scold":
            self.mode.submit_companion_reinforcement("scold")
            self.selected_index = 0
            return
        if action == "companion:wait":
            self.mode.submit_companion_reinforcement("wait")
            self.selected_index = 0
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
            self._apply_presentation_clips(step)
            return
        self._finish_presentation()

    def _apply_presentation_clips(self, step: BattlePresentationStep) -> None:
        if step.player_clip:
            self._player_sprite.play_clip(step.player_clip)
        if step.opponent_clip:
            self._opponent_sprite.play_clip(step.opponent_clip)

    def _finish_presentation(self) -> None:
        result = self._pending_battle_result
        self._pending_battle_result = None
        self._presentation_elapsed = 0.0
        if result is not None and self.mode.active:
            self.menu_state = "ended"
            self.mode.complete_presented_battle(result)
            return
        if self.mode.companion_mode:
            if self.mode._presenting_reinforcement:
                self.mode._presenting_reinforcement = False
                controller = self.mode.controller
                if controller is not None and controller.result is None and controller.phase == "choose_action":
                    self.mode._run_companion_monster_turn()
                return
            if self.mode._presenting_companion_switch:
                self.mode._presenting_companion_switch = False
                controller = self.mode.controller
                if controller is not None and controller.result is None and controller.phase == "choose_action":
                    self.mode._run_companion_monster_turn()
                return
            controller = self.mode.controller
            if controller is not None and controller.phase == "must_switch":
                self.mode.auto_switch_companion_bench()
                return
            self.mode.companion_awaiting_reinforcement = True
            self.menu_state = "root"
            self.selected_index = 0
            self.log_line = "How do you respond?"
            return
        controller = self.mode.controller
        if controller is not None and controller.phase == "must_switch":
            self.menu_state = "root"
            self.selected_index = 0
            self.mode.open_switch_screen(forced=True)
            return
        self.menu_state = "root"
        self.selected_index = 0


class BattleSwitchScreen(SelectableListScreen):
    """In-battle party picker built on the shared menu toolkit."""

    def __init__(self, mode: "MonsterBattleMode", *, forced: bool) -> None:
        self.mode = mode
        self.forced = forced
        controller = mode.controller
        items: list[SelectableItem] = []
        if controller is not None:
            for index, monster in enumerate(controller.player_party):
                name = _display_name(monster)
                max_hp = max(1, int(monster.stats.hp if monster.stats else monster.current_hp or 1))
                hp = max(0, int(monster.current_hp or 0))
                fainted = monster.fainted
                suffix = "  FNT" if fainted else ""
                label = f"{name}  Lv.{monster.level}  HP {hp}/{max_hp}{suffix}"
                items.append(
                    SelectableItem(
                        id=str(index),
                        label=label,
                        detail_lines=(
                            f"Species: {monster.species.id}",
                            f"Level: {monster.level}",
                            f"HP: {hp}/{max_hp}",
                        ),
                        enabled=not fainted and index != controller.active_index,
                    ),
                )
        super().__init__(
            title="Choose a monster",
            items=items,
            on_activate=lambda item: mode.submit_player_switch(int(item.id)),
            empty_detail="No usable monsters.",
        )

    def on_key_press(self, key: int, modifiers: int, stack: MenuStackOverlay) -> bool:
        arcade_key = optional_arcade.arcade.key
        if self.forced and key == arcade_key.ESCAPE:
            return True
        return super().on_key_press(key, modifiers, stack)


class MonsterBattleMode:
    """GameWindow-owned monster battle runtime mode."""

    def __init__(self, window: "GameWindow") -> None:
        self.window = window
        self.controller: MonsterBattleController | None = None
        self.overlay: MonsterBattleOverlay | None = None
        self.return_context: dict[str, Any] = {}
        self._prior_paused = False
        self.active = False
        self.player_party_instance_ids: list[str | None] = []
        self.companion_mode = False
        self.companion_mind: CompanionMind | None = None
        self.companion_ctx = DecisionContext()
        self.companion_awaiting_reinforcement = False
        self._presenting_reinforcement = False
        self._presenting_companion_switch = False
        self._last_companion_behavior: str = ""
        self._companion_instance_id: str | None = None

    def start_battle(
        self,
        *,
        player_monster: MonsterInstance,
        opponent_monster: MonsterInstance,
        moves: Mapping[str, Move],
        player_party: Sequence[MonsterInstance] | None = None,
        player_party_instance_ids: Sequence[str | None] | None = None,
        opponent_party: Sequence[MonsterInstance] | None = None,
        companion_mode: bool = False,
        companion_mind: CompanionMind | None = None,
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
        party = list(player_party) if player_party is not None else [player_monster]
        if player_party_instance_ids is not None:
            self.player_party_instance_ids = list(player_party_instance_ids)
        else:
            self.player_party_instance_ids = [None] * len(party)
        self.companion_mode = bool(companion_mode)
        active_instance_id = self.player_party_instance_ids[0] if self.player_party_instance_ids else None
        self._companion_instance_id = str(active_instance_id) if active_instance_id else None
        if self.companion_mode and self._companion_instance_id:
            loaded_mind = load_companion_mind_for_instance(self._state_values(), self._companion_instance_id)
            if loaded_mind is not None:
                companion_mind = loaded_mind
        self.companion_mind = companion_mind if companion_mind is not None else CompanionMind()
        self.companion_ctx = DecisionContext()
        self.companion_awaiting_reinforcement = False
        self._presenting_reinforcement = False
        self._presenting_companion_switch = False
        self._last_companion_behavior = ""
        self.controller = MonsterBattleController(
            player=player_monster,
            opponent=opponent_monster,
            player_party=player_party,
            opponent_party=opponent_party,
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
        if self.companion_mode:
            self._run_companion_monster_turn()
        return self.controller

    def submit_companion_reinforcement(self, kind: str) -> None:
        if not self.active or not self.companion_mode or self.controller is None or self.companion_mind is None:
            raise RuntimeError("companion battle mode is not active")
        if not self.companion_awaiting_reinforcement:
            raise RuntimeError("companion battle is not awaiting reinforcement")

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
        reinforcement = str(kind)
        if reinforcement == "praise":
            self.companion_mind = praise(self.companion_mind)
        elif reinforcement == "scold":
            self.companion_mind = scold(self.companion_mind)
        elif reinforcement == "wait":
            self.companion_mind = wait(self.companion_mind)
        else:
            raise ValueError(f"Unknown companion reinforcement '{kind}'")

        self.companion_awaiting_reinforcement = False
        self._presenting_reinforcement = True
        result = self.controller.result
        if self.overlay is not None:
            steps = _build_companion_reinforcement_steps(
                reinforcement,
                _display_name(self.controller.player),
                before_player_hp,
                before_opponent_hp,
            )
            self.overlay.begin_turn_presentation(steps, result=result)

    def _run_companion_monster_turn(self) -> BattleResult | None:
        if not self.companion_mode or self.controller is None or self.companion_mind is None:
            raise RuntimeError("companion battle mode is not active")
        if self.controller.result is not None:
            return self.controller.result
        if self.controller.player.fainted:
            return self.controller.result
        if self.controller.phase != "choose_action":
            return self.controller.result

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
        rng = self.controller.rng if self.controller.rng is not None else self._capture_rng()
        max_hp = max(1, int(self.controller.player.stats.hp if self.controller.player.stats else self.controller.player.current_hp or 1))
        current_hp = max(0, int(self.controller.player.current_hp or 0))
        self.companion_ctx = DecisionContext(hp_fraction=current_hp / max_hp)
        self.companion_mind, decision = decide(self.companion_mind, self.companion_ctx, rng)
        behavior = decision.behavior_id
        self._last_companion_behavior = behavior

        if behavior == FLEE:
            result = self._companion_flee_result()
            self.companion_awaiting_reinforcement = False
            self._presenting_reinforcement = False
            if self.overlay is not None:
                name = _display_name(self.controller.player)
                steps = [
                    BattlePresentationStep(f"{name} flees!", before_player_hp, before_opponent_hp),
                    BattlePresentationStep("It abandoned you.", before_player_hp, before_opponent_hp),
                ]
                self.overlay.begin_turn_presentation(steps, result=result)
            else:
                self.end_battle(result)
            return result

        if behavior == ATTACK:
            result = self.controller.submit_action("player", _first_damaging_move_id(self.controller))
        elif behavior == DEFEND:
            result = self.controller.submit_player_pass_turn(guarding=True)
        else:
            result = self.controller.submit_player_pass_turn(guarding=False)

        self.companion_awaiting_reinforcement = False
        self._presenting_reinforcement = False
        if self.overlay is not None:
            name = _display_name(self.controller.player)
            companion_clip: str | None = None
            if behavior == ATTACK:
                companion_clip = "attack"
            elif behavior == DEFEND:
                companion_clip = "defend"
            steps = [
                BattlePresentationStep(
                    _companion_autonomous_line(behavior, name),
                    before_player_hp,
                    before_opponent_hp,
                    player_clip=companion_clip,
                ),
            ]
            steps.extend(self._build_presentation_steps(before_len, before_player_hp, before_opponent_hp))
            if result is not None and result.outcome == "won":
                steps.extend(self._apply_victory_progression_steps(before_player_hp, before_opponent_hp))
            self.overlay.begin_turn_presentation(steps, result=result)
        elif result is not None:
            if result.outcome == "won":
                self._apply_victory_progression_steps(before_player_hp, before_opponent_hp)
            self.end_battle(result)
        return result

    def auto_switch_companion_bench(self) -> BattleResult | None:
        """Send out the next healthy companion when the active one faints."""

        if not self.active or not self.companion_mode or self.controller is None:
            raise RuntimeError("companion battle mode is not active")
        if self.controller.phase != "must_switch":
            return self.controller.result

        next_index = self._next_player_bench_index()
        if next_index is None:
            return self.controller.result

        fainted_name = _display_name(self.controller.player)
        before_opponent_hp = int(
            self.overlay.displayed_opponent_hp
            if self.overlay is not None and self.overlay.displayed_opponent_hp is not None
            else self.controller.opponent.current_hp,
        )
        next_name = _display_name(self.controller.player_party[next_index])

        self._persist_active_companion_mind()
        result = self.controller.submit_switch(next_index)
        self._attach_companion_mind_for_active_index(next_index)

        before_player_hp = int(self.controller.player.current_hp or 0)
        self.companion_awaiting_reinforcement = False
        self._presenting_reinforcement = False
        if self.overlay is not None:
            self._presenting_companion_switch = True
            self.overlay.begin_turn_presentation(
                [
                    BattlePresentationStep(
                        f"{fainted_name} fainted!",
                        0,
                        before_opponent_hp,
                        player_clip="faint",
                    ),
                    BattlePresentationStep(f"Go, {next_name}!", before_player_hp, before_opponent_hp),
                ],
                result=result,
            )
            self.overlay.sync_displayed_hp()
        elif result is not None:
            self.end_battle(result)
        elif self.controller.phase == "choose_action":
            self._run_companion_monster_turn()
        return result

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
            if result is not None and result.outcome == "won":
                steps.extend(self._apply_victory_progression_steps(before_player_hp, before_opponent_hp))
            self.overlay.begin_turn_presentation(steps, result=result)
        elif result is not None:
            if result.outcome == "won":
                self._apply_victory_progression_steps(before_player_hp, before_opponent_hp)
            self.end_battle(result)
        return result

    def submit_player_switch(self, party_index: int) -> BattleResult | None:
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
        self._pop_switch_screen_if_open()
        result = self.controller.submit_switch(int(party_index))
        if self.overlay is not None:
            steps = self._build_presentation_steps(before_len, before_player_hp, before_opponent_hp)
            if result is not None and result.outcome == "won":
                steps.extend(self._apply_victory_progression_steps(before_player_hp, before_opponent_hp))
            self.overlay.begin_turn_presentation(steps, result=result)
            self.overlay.sync_displayed_hp()
        elif result is not None:
            if result.outcome == "won":
                self._apply_victory_progression_steps(before_player_hp, before_opponent_hp)
            self.end_battle(result)
        return result

    def open_switch_screen(self, *, forced: bool) -> None:
        if not self.active or self.controller is None:
            raise RuntimeError("monster battle mode is not active")
        stack = self._ensure_menu_stack()
        stack.push(BattleSwitchScreen(self, forced=forced))

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
            self.return_context.update({"caught_instance_id": caught.instance_id, "caught_storage": caught.storage})
            if self.overlay is not None:
                player_hp = int(
                    self.overlay.displayed_player_hp
                    if self.overlay.displayed_player_hp is not None
                    else self.controller.player.current_hp,
                )
                opponent_hp = int(
                    self.overlay.displayed_opponent_hp
                    if self.overlay.displayed_opponent_hp is not None
                    else self.controller.opponent.current_hp,
                )
                storage_line = "Sent to the Box!" if caught.storage == "box" else "Sent to your party!"
                self.overlay.begin_turn_presentation(
                    [
                        BattlePresentationStep(
                            f"Gotcha! {_display_name(self.controller.opponent)} was caught!",
                            player_hp,
                            opponent_hp,
                        ),
                        BattlePresentationStep(storage_line, player_hp, opponent_hp),
                    ],
                    result=result,
                )
            else:
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

        if self.companion_mode and self.companion_mind is not None and self._companion_instance_id:
            self._persist_active_companion_mind()

        payload = self._result_payload(final_result)
        self._apply_result_payload(payload)
        self._persist_party_to_instances()
        if self.companion_mode and str(getattr(final_result, "outcome", "")) == "fled":
            self._remove_fled_companion_from_party()
        self._emit_ended(payload)

        if self.overlay is not None:
            self.overlay.hide()
            self._unregister_overlay(self.overlay)

        self.controller = None
        self.overlay = None
        self.return_context = {}
        self.player_party_instance_ids = []
        self.companion_mode = False
        self.companion_mind = None
        self.companion_awaiting_reinforcement = False
        self._presenting_reinforcement = False
        self._presenting_companion_switch = False
        self._companion_instance_id = None
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
            if entry.kind == "switch":
                if entry.side == "player":
                    monster = self.controller.player_party[entry.party_index]
                    name = _display_name(monster)
                    if entry.switch_kind == "recall":
                        line = f"Come back, {name}!"
                    else:
                        line = f"Go, {name}!"
                        player_hp = int(monster.current_hp or 0)
                else:
                    monster = self.controller.opponent_party[entry.party_index]
                    name = _display_name(monster)
                    line = f"Trainer sent out {name}!"
                    opponent_hp = int(monster.current_hp or 0)
                steps.append(BattlePresentationStep(line, player_hp, opponent_hp))
                continue
            if entry.kind == "status":
                subject = _display_name(self.controller.player if entry.side == "player" else self.controller.opponent)
                if entry.status_event == "poisoned":
                    line = f"{subject} was poisoned!"
                elif entry.status_event == "poison_damage":
                    if entry.side == "player":
                        player_hp = max(0, player_hp - int(entry.status_damage))
                    else:
                        opponent_hp = max(0, opponent_hp - int(entry.status_damage))
                    line = f"{subject} is hurt by poison!"
                    hurt_clip = "hurt"
                    if entry.side == "player":
                        steps.append(
                            BattlePresentationStep(
                                line,
                                player_hp,
                                opponent_hp,
                                player_clip=hurt_clip,
                            ),
                        )
                    else:
                        steps.append(
                            BattlePresentationStep(
                                line,
                                player_hp,
                                opponent_hp,
                                opponent_clip=hurt_clip,
                            ),
                        )
                    if entry.target_fainted:
                        faint_name = _faint_line(self.controller, entry)
                        faint_clip = "faint"
                        if entry.side == "player":
                            steps.append(
                                BattlePresentationStep(
                                    faint_name,
                                    player_hp,
                                    opponent_hp,
                                    player_clip=faint_clip,
                                ),
                            )
                        else:
                            steps.append(
                                BattlePresentationStep(
                                    faint_name,
                                    player_hp,
                                    opponent_hp,
                                    opponent_clip=faint_clip,
                                ),
                            )
                    continue
                elif entry.status_event == "fell_asleep":
                    line = f"{subject} fell asleep!"
                elif entry.status_event == "woke_up":
                    line = f"{subject} woke up!"
                elif entry.status_event == "asleep_skip":
                    line = f"{subject} is fast asleep!"
                else:
                    line = f"{subject} was affected!"
                steps.append(BattlePresentationStep(line, player_hp, opponent_hp))
                if entry.target_fainted:
                    faint_name = _faint_line(self.controller, entry)
                    faint_player_clip = "faint" if entry.side == "player" else None
                    faint_opponent_clip = "faint" if entry.side == "opponent" else None
                    steps.append(
                        BattlePresentationStep(
                            faint_name,
                            player_hp,
                            opponent_hp,
                            player_clip=faint_player_clip,
                            opponent_clip=faint_opponent_clip,
                        ),
                    )
                continue
            player_clip: str | None = None
            opponent_clip: str | None = None
            if entry.side == "player":
                actor = _display_name(self.controller.player)
                target = _display_name(self.controller.opponent)
                player_clip = "attack"
                if entry.hit:
                    opponent_hp = max(0, opponent_hp - int(entry.damage))
                    opponent_clip = "hurt"
            else:
                actor = _display_name(self.controller.opponent)
                target = _display_name(self.controller.player)
                opponent_clip = "attack"
                if entry.hit:
                    player_hp = max(0, player_hp - int(entry.damage))
                    player_clip = "hurt"
            if entry.hit:
                line = f"{actor} used {entry.move_id}! {target} took {entry.damage} damage."
            else:
                line = f"{actor} used {entry.move_id}, but it missed!"
            steps.append(
                BattlePresentationStep(
                    line,
                    player_hp,
                    opponent_hp,
                    player_clip=player_clip,
                    opponent_clip=opponent_clip,
                ),
            )
            if entry.target_fainted:
                faint_name = _faint_line(self.controller, entry)
                faint_player_clip = "faint" if entry.side == "opponent" else None
                faint_opponent_clip = "faint" if entry.side == "player" else None
                steps.append(
                    BattlePresentationStep(
                        faint_name,
                        player_hp,
                        opponent_hp,
                        player_clip=faint_player_clip,
                        opponent_clip=faint_opponent_clip,
                    ),
                )
        return steps

    def _apply_victory_progression_steps(self, before_player_hp: int, before_opponent_hp: int) -> list[BattlePresentationStep]:
        if self.controller is None:
            return []
        xp = award_xp_for_victory(self.controller.opponent)
        progression = apply_experience(self.controller.player, xp)
        self.controller.player = progression.instance
        instance_id = self._persist_player_monster(progression.instance)
        self.return_context.update({"player_instance_id": instance_id, "xp_gained": progression.xp_gained})
        hp = int(progression.instance.current_hp or before_player_hp)
        opponent_hp = int(self.controller.opponent.current_hp if self.controller.opponent.current_hp is not None else before_opponent_hp)
        steps = [
            BattlePresentationStep(
                f"{_display_name(progression.instance)} gained {progression.xp_gained} XP!",
                hp,
                opponent_hp,
            ),
        ]
        for level in range(progression.previous_level + 1, progression.instance.level + 1):
            steps.append(BattlePresentationStep(f"{_display_name(progression.instance)} grew to Lv {level}!", hp, opponent_hp))
        for move_id in progression.moves_learned:
            steps.append(BattlePresentationStep(f"{_display_name(progression.instance)} learned {move_id}!", hp, opponent_hp))
        return steps

    def _persist_player_monster(self, monster: MonsterInstance) -> str:
        values = self._state_values()
        instances = values[MONSTER_INSTANCES_KEY]
        party = values[MONSTER_PARTY_KEY]
        box = values[MONSTER_BOX_KEY]
        raw_id = self.return_context.get("player_instance_id")
        instance_id = str(raw_id) if isinstance(raw_id, str) and raw_id in instances else ""
        if not instance_id:
            for candidate in party:
                candidate_id = str(candidate)
                if candidate_id in instances:
                    instance_id = candidate_id
                    break
        if not instance_id:
            stored = add_caught_monster(values, monster)
            instance_id = stored.instance_id
        elif instance_id not in party and instance_id not in box:
            if len(party) < MAX_PARTY_SIZE:
                party.append(instance_id)
            else:
                box.append(instance_id)
        instances[instance_id] = serialize_monster_instance(monster)
        return instance_id

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
        self.controller._set_monster("player", resolution.defender)
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
        self.controller.phase = "apply_faints"
        self.controller._apply_faints()
        result = self.controller.result
        if result is None and self.controller.phase == "choose_action":
            self.controller.turn_number += 1

        steps = [
            BattlePresentationStep(
                f"Threw {item_id}! {_display_name(self.controller.opponent)} broke free.",
                before_player_hp,
                before_opponent_hp,
            ),
        ]
        steps.extend(self._build_presentation_steps(len(self.controller.turn_log) - 1, before_player_hp, before_opponent_hp))
        self.overlay.begin_turn_presentation(steps, result=result)

    def _ensure_menu_stack(self) -> MenuStackOverlay:
        stack = getattr(self.window, "monster_menu_stack", None)
        if not isinstance(stack, MenuStackOverlay):
            stack = MenuStackOverlay(self.window)
            setattr(self.window, "monster_menu_stack", stack)
        ui_controller = getattr(self.window, "ui_controller", None)
        elements = getattr(ui_controller, "ui_elements", None)
        if isinstance(elements, list):
            if stack in elements:
                elements.remove(stack)
            elements.append(stack)
        elif ui_controller is not None:
            register = getattr(ui_controller, "register_ui_element", None)
            if callable(register):
                register(stack)
        return stack

    def _pop_switch_screen_if_open(self) -> None:
        stack = getattr(self.window, "monster_menu_stack", None)
        if isinstance(stack, MenuStackOverlay) and stack.screens:
            stack.pop()

    def _persist_party_to_instances(self) -> None:
        if self.controller is None:
            return
        values = self._state_values()
        instances = values[MONSTER_INSTANCES_KEY]
        for monster, instance_id in zip(self.controller.player_party, self.player_party_instance_ids, strict=False):
            if instance_id is None:
                continue
            existing = instances.get(str(instance_id))
            mind_payload = existing.get(COMPANION_MIND_INSTANCE_KEY) if isinstance(existing, dict) else None
            row = serialize_monster_instance(monster)
            if isinstance(mind_payload, dict):
                row[COMPANION_MIND_INSTANCE_KEY] = dict(mind_payload)
            instances[str(instance_id)] = row

    def _persist_active_companion_mind(self) -> None:
        if self.companion_mind is not None and self._companion_instance_id:
            persist_companion_mind(self._state_values(), self._companion_instance_id, self.companion_mind)

    def _attach_companion_mind_for_active_index(self, party_index: int) -> None:
        if party_index < 0 or party_index >= len(self.player_party_instance_ids):
            self._companion_instance_id = None
            self.companion_mind = CompanionMind()
            return
        instance_id = self.player_party_instance_ids[party_index]
        self._companion_instance_id = str(instance_id) if instance_id else None
        if self._companion_instance_id:
            loaded = load_companion_mind_for_instance(self._state_values(), self._companion_instance_id)
            if loaded is not None:
                self.companion_mind = loaded
                return
        self.companion_mind = CompanionMind()

    def _next_player_bench_index(self) -> int | None:
        if self.controller is None:
            return None
        count = len(self.controller.player_party)
        for offset in range(1, count):
            index = (self.controller.active_index + offset) % count
            if not self.controller.player_party[index].fainted:
                return index
        return None

    def _companion_flee_result(self) -> BattleResult:
        if self.controller is None:
            raise RuntimeError("monster battle mode is not active")
        return BattleResult(
            cast(Any, "fled"),
            winning_side="opponent",
            losing_side="player",
            turns=self.controller.turn_number,
        )

    def _remove_fled_companion_from_party(self) -> None:
        instance_id = self._companion_instance_id
        if not instance_id:
            return
        values = self._state_values()
        party = values[MONSTER_PARTY_KEY]
        id_str = str(instance_id)
        if id_str in party:
            party.remove(id_str)


def start_monster_battle(window: "GameWindow", **kwargs: Any) -> MonsterBattleController:
    """Convenience entrypoint for tests and future runtime triggers."""

    mode = getattr(window, "monster_battle_mode", None)
    if mode is None:
        mode = MonsterBattleMode(window)
        window.monster_battle_mode = mode
    return mode.start_battle(**kwargs)


def _empty_species() -> Species:
    from .battle_model import BattleStats

    return Species(
        id="__none__",
        base_stats=BattleStats(hp=1, atk=1, defense=1, spd=1),
        types=("normal",),
    )


def _display_name(monster: MonsterInstance) -> str:
    raw = monster.species.id.replace("_", " ").replace("-", " ")
    return raw.title()


def _first_damaging_move_id(controller: MonsterBattleController) -> str:
    for move_id in controller.player.known_moves or controller.player.species.learnset:
        move = controller.moves.get(str(move_id))
        if move is not None and int(move.power) > 0:
            return str(move.id)
    for move_id in controller.player.known_moves or controller.player.species.learnset:
        if str(move_id) in controller.moves:
            return str(move_id)
    return str(sorted(controller.moves)[0])


def _companion_autonomous_line(behavior: str, name: str) -> str:
    if behavior == ATTACK:
        return f"{name} attacks!"
    if behavior == DEFEND:
        return f"{name} braces."
    if behavior == FLEE:
        return f"{name} flees!"
    return f"{name} hesitates."


def _build_companion_reinforcement_steps(
    kind: str,
    name: str,
    player_hp: int,
    opponent_hp: int,
) -> list[BattlePresentationStep]:
    if kind == "praise":
        return [
            BattlePresentationStep(f"You praise {name}.", player_hp, opponent_hp),
            BattlePresentationStep("It looks pleased.", player_hp, opponent_hp),
        ]
    if kind == "scold":
        return [
            BattlePresentationStep(f"You scold {name}.", player_hp, opponent_hp),
            BattlePresentationStep("It flinches.", player_hp, opponent_hp),
        ]
    return [
        BattlePresentationStep("You wait calmly.", player_hp, opponent_hp),
        BattlePresentationStep("It watches you.", player_hp, opponent_hp),
    ]


def _faint_line(controller: MonsterBattleController, entry: BattleLogEntry) -> str:
    if entry.party_index >= 0:
        opponent_fainted = (entry.kind == "move" and entry.side == "player") or (
            entry.kind == "status" and entry.side == "opponent"
        )
        if opponent_fainted:
            monster = controller.opponent_party[entry.party_index]
            return f"Foe {_display_name(monster)} fainted!"
        monster = controller.player_party[entry.party_index]
        return f"{_display_name(monster)} fainted!"
    subject = _display_name(controller.player if entry.side == "opponent" else controller.opponent)
    return f"{subject} fainted!"


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
