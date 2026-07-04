"""Battle UI terminology loading and overlay rendering."""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine import savegame
from engine.game_state_controller import GameState
from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.battle_terms import DEFAULT_BATTLE_TERMS, BattleTerms
from engine.monster.collection import MONSTER_INSTANCES_KEY, MONSTER_PARTY_KEY, POCKET_BALL_COUNT_KEY, serialize_monster_instance
from engine.monster.data_load import load_battle_terms, parse_battle_terms
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
WATER_PULSE = Move(id="water_pulse", type="water", power=60, accuracy=100, pp=20, category="special")

PLAYER = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=12, defense=10, spd=20),
    types=("grass",),
    learnset=("tackle", "water_pulse"),
)
OPPONENT = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
    capture_rate=10,
)


def test_load_battle_terms_uses_defaults_when_file_missing(tmp_path: Path) -> None:
    terms, result = load_battle_terms(tmp_path)
    assert result.ok is True
    assert terms == DEFAULT_BATTLE_TERMS


def test_parse_battle_terms_accepts_spike_style_override() -> None:
    terms, result = parse_battle_terms(
        {
            "capture_item_name": "Net",
            "capture_item_plural": "Nets",
            "capture_item_menu_label": "Net",
            "move_resource_label": "MP",
        },
    )
    assert result.ok is True
    assert terms.capture_item_name == "Net"
    assert terms.capture_item_plural == "Nets"
    assert terms.move_resource_label == "MP"
    assert terms.format_capture_bag_row(5) == "Net x5"
    assert terms.format_no_capture_items_left() == "No Nets left!"
    assert terms.format_move_row(move_id="water_pulse", move_type="water", move_pp=20) == "water_pulse water MP 20"


def test_parse_battle_terms_rejects_unknown_keys() -> None:
    _, result = parse_battle_terms({"capture_item_name": "Net", "ball_label": "Net"})
    assert result.ok is False
    assert any("unknown key 'ball_label'" in err for err in result.errors)
    assert "capture_item_name" in " ".join(result.errors)


class _HighRoll:
    def random(self) -> float:
        return 0.99


def _window(*, values: dict[str, Any] | None = None) -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = UIController(as_any(window))
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    state = GameState()
    if values is not None:
        state.values = values
    window.game_state_controller = types.SimpleNamespace(state=state)
    return window


def _start_battle(window: types.SimpleNamespace, *, terms: BattleTerms | None = None) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=8, current_hp=24, known_moves=("tackle", "water_pulse")),
        opponent_monster=MonsterInstance(OPPONENT, level=6, current_hp=20, known_moves=("tackle",)),
        moves={"tackle": TACKLE, "water_pulse": WATER_PULSE},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    if terms is not None:
        mode.terms = terms
    return mode


def test_overlay_uses_default_pp_and_pocket_ball_labels() -> None:
    mode = _start_battle(_window())
    overlay = mode.overlay
    assert overlay is not None
    overlay.menu_state = "fight"
    labels = [label for _, label in overlay._current_actions()]
    assert labels == ["tackle normal PP 35", "water_pulse water PP 20"]

    overlay.menu_state = "bag"
    bag_labels = [label for _, label in overlay._current_actions()]
    assert bag_labels[0].startswith("Pocket Ball x")


def test_overlay_uses_spike_style_terms_when_configured() -> None:
    spike_terms = BattleTerms(
        capture_item_name="Net",
        capture_item_plural="Nets",
        capture_item_menu_label="Net",
        move_resource_label="MP",
    )
    values: dict[str, Any] = {POCKET_BALL_COUNT_KEY: 5}
    mode = _start_battle(_window(values=values), terms=spike_terms)
    overlay = mode.overlay
    assert overlay is not None

    overlay.menu_state = "fight"
    assert [label for _, label in overlay._current_actions()] == [
        "tackle normal MP 35",
        "water_pulse water MP 20",
    ]

    overlay.menu_state = "bag"
    assert [label for _, label in overlay._current_actions()] == ["Net x5", "Back"]

    values[POCKET_BALL_COUNT_KEY] = 0
    mode.attempt_capture(item_id="pocket_ball")
    assert overlay.log_line == "No Nets left!"

    values[POCKET_BALL_COUNT_KEY] = 2
    mode._capture_rng = _HighRoll  # type: ignore[method-assign]
    mode.attempt_capture(item_id="pocket_ball")
    assert overlay.presentation_queue
    assert "Threw a Net!" in overlay.presentation_queue[0].line


def test_quick_save_round_trip_preserves_pocket_ball_count_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.game_state_controller import GameStateController

    monkeypatch.chdir(tmp_path)
    (tmp_path / "saves").mkdir(parents=True, exist_ok=True)
    save_path = tmp_path / "saves" / "quick.json"

    player_row = serialize_monster_instance(
        MonsterInstance(PLAYER, level=8, known_moves=("tackle",)),
    )
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: ["sproutling_0001"],
        POCKET_BALL_COUNT_KEY: 3,
        MONSTER_INSTANCES_KEY: {"sproutling_0001": dict(player_row)},
    }
    window = _window(values=values)
    window.game_state_controller = GameStateController(window)
    window.game_state_controller.state.values = values
    window.engine_config = types.SimpleNamespace(world_file="packs/core_regions/worlds/main.json")
    window.scene_controller = types.SimpleNamespace(current_scene_path="packs/core_regions/scenes/start.json")

    assert savegame.save_quick_snapshot(window, path=save_path) is True
    payload = json.loads(save_path.read_text(encoding="utf-8"))
    assert payload["game_state"]["values"][POCKET_BALL_COUNT_KEY] == 3

    reload_window = _window()
    reload_window.game_state_controller = GameStateController(reload_window)
    reload_window.engine_config = window.engine_config
    reload_window.scene_controller = window.scene_controller
    assert savegame.load_quick_snapshot(reload_window, path=save_path) is True
    assert reload_window.game_state_controller.state.values[POCKET_BALL_COUNT_KEY] == 3
