"""A state replacement leaves the quest manager in step with the new state.

D1's runtime debugger found it: a Studio play-test starts from ``GameStateController.replace_state({})``, which
built a fresh game state but never re-synced quests, so an ``auto_start`` quest stayed ``inactive`` (no stage) and
a stage waiting on a flag never advanced. Every caller (Studio Play and Stop, both main-menu New Games) routes
through ``replace_state``, so the fix lives there; loading a save must keep the saved progress.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.game_state_controller import GameStateController
from engine.quests import QuestManager

pytestmark = pytest.mark.fast

_QUEST = {
    "id": "help_the_smith",
    "title": "Help the Smith",
    "auto_start": True,
    "stages": [
        {"id": "agree", "title": "Agree to help", "requirements": {"flags": {"agreed_to_help": True}}},
        {"id": "report", "title": "Report back"},
    ],
}


class _Window(SimpleNamespace):
    """What the quest manager needs of a game window: its game state, as GameWindow gives it."""

    @property
    def game_state(self) -> object:
        return self.game_state_controller.state

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)


def _game() -> tuple[GameStateController, QuestManager]:
    window = _Window(emit_signal=lambda *_args, **_kwargs: None)
    controller = window.game_state_controller = GameStateController(window)  # type: ignore[arg-type]
    quests = QuestManager(window)
    normalized = quests._normalize_quest(_QUEST)
    assert normalized is not None
    quests._definitions = {normalized["id"]: normalized}
    quests._rebuild_stage_lookup()
    controller.quests = quests  # type: ignore[assignment]  # one shared manager, as GameWindow sets it up
    quests.reload_from_state()
    return controller, quests


def _progress(quests: QuestManager) -> dict[str, Any]:
    snapshot = quests.get_state_snapshot("help_the_smith")
    assert snapshot is not None
    return snapshot


def test_replace_state_empty_starts_auto_start_quest_and_flag_advances_it() -> None:
    controller, quests = _game()
    controller.set_flag("agreed_to_help", True)  # the last play-test got past the first stage
    controller.update(0.1)
    assert _progress(quests)["current_stage"] == "report"

    controller.replace_state({})

    assert _progress(quests)["status"] == "active"
    assert _progress(quests)["current_stage"] == "agree"
    controller.set_flag("agreed_to_help", True)
    controller.update(0.1)
    assert _progress(quests)["current_stage"] == "report"
    assert _progress(quests)["completed_stages"] == ["agree"]


def test_replace_state_with_saved_quests_keeps_saved_progress() -> None:
    controller, quests = _game()
    controller.set_flag("agreed_to_help", True)
    controller.update(0.1)
    saved = controller.export_state()

    controller.replace_state({})
    assert _progress(quests)["current_stage"] == "agree"

    controller.replace_state(saved)

    assert _progress(quests)["status"] == "active"
    assert _progress(quests)["current_stage"] == "report"
    assert _progress(quests)["completed_stages"] == ["agree"]
    assert controller.get_flag("agreed_to_help") is True
