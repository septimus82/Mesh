from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from engine.game import GameWindow
from engine.game_state_controller import GameStateController
from engine.monster.companion_mind import (
    FLEE,
    FLEE_RELATIONSHIP_THRESHOLD,
    DecisionContext,
    scold,
    score_behaviors,
)
from tests._typing import as_any

pytestmark = pytest.mark.fast


def _debug_companion_window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.console_log = MagicMock()
    window.monster_battle_mode = types.SimpleNamespace(active=False)
    window.game_state_controller = GameStateController(window)
    window.scene_controller = types.SimpleNamespace(current_scene_path="scenes/test.json")
    captured: dict[str, object] = {}

    def _capture_start_monster_battle(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    window.start_monster_battle = _capture_start_monster_battle
    window._captured_battle_kwargs = captured
    return window


def test_fresh_f8_starter_mind_is_bonded_and_wont_flee_at_low_hp() -> None:
    window = _debug_companion_window()

    GameWindow.start_debug_companion_monster_battle(as_any(window))

    mind = window._captured_battle_kwargs["companion_mind"]
    assert (mind.trust + mind.bond) / 2.0 >= FLEE_RELATIONSHIP_THRESHOLD
    scores = score_behaviors(mind, DecisionContext(hp_fraction=0.1))
    assert FLEE not in scores


def test_scolded_f8_starter_becomes_flee_eligible_at_low_hp() -> None:
    window = _debug_companion_window()

    GameWindow.start_debug_companion_monster_battle(as_any(window))

    mind = window._captured_battle_kwargs["companion_mind"]
    for _ in range(5):
        mind = scold(mind)

    assert (mind.trust + mind.bond) / 2.0 < FLEE_RELATIONSHIP_THRESHOLD
    scores = score_behaviors(mind, DecisionContext(hp_fraction=0.1))
    assert FLEE in scores
