"""B-05: the four event-driven behaviours release their bus subscription when they end (the old teardown called a
``bus.unsubscribe`` method that does not exist, so the callback kept running for a removed entity)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.behaviours.cutscene_trigger import CutsceneTrigger
from engine.behaviours.grant_experience import GrantExperience
from engine.behaviours.quest_giver import QuestGiver
from engine.behaviours.scene_exit import SceneExit
from engine.events import MeshEventBus

pytestmark = pytest.mark.integration


class _Window:
    def __init__(self) -> None:
        self.event_bus = MeshEventBus()
        self.game_state_controller = MagicMock()
        self.cutscene_controller = MagicMock()
        self.scene_controller = MagicMock()


def _make(kind: str, window: _Window, entity: Any):
    if kind == "xp":
        return GrantExperience(entity, window, event="foe_died", xp=5)
    if kind == "quest":
        return QuestGiver(entity, window, quest_id="q", listen_event="offer")
    if kind == "cutscene":
        return CutsceneTrigger(entity, window, listen_event="go", cutscene_id="c")
    return SceneExit(entity, window, listen_event="exit", target_scene="b", target_spawn="s")


def _fire(kind: str, window: _Window, entity: Any) -> int:
    """Publish the behaviour's event; return how many times its effect ran."""
    bus = window.event_bus
    if kind == "xp":
        bus.emit("foe_died", actor=entity)
        return window.game_state_controller.add_xp.call_count
    if kind == "quest":
        bus.emit("offer")
        return window.game_state_controller.quests.start_quest.call_count
    if kind == "cutscene":
        bus.emit("go")
        return window.cutscene_controller.play_cutscene.call_count
    bus.emit("exit")
    return window.scene_controller.queue_scene_change.call_count


KINDS = ["xp", "quest", "cutscene", "exit"]



def _count(bus: MeshEventBus) -> int:
    return sum(len(v) for v in bus._subscribers.values())


@pytest.mark.parametrize("kind", KINDS)
def test_removed_entity_callback_stops_and_count_returns_to_baseline(kind: str) -> None:
    window = _Window()
    entity = MagicMock()
    baseline = _count(window.event_bus)
    behaviour = _make(kind, window, entity)
    assert _count(window.event_bus) == baseline + 1
    assert _fire(kind, window, entity) == 1

    behaviour.on_destroy()

    assert _count(window.event_bus) == baseline
    assert _fire(kind, window, entity) == 1  # no second run for the removed entity
    behaviour.on_destroy()  # ending twice is harmless
    assert _count(window.event_bus) == baseline


@pytest.mark.parametrize("kind", KINDS)
def test_scene_change_ends_the_subscription(kind: str) -> None:
    window = _Window()
    entity = MagicMock()
    baseline = _count(window.event_bus)
    with window.event_bus.record_subscriptions() as made:
        _make(kind, window, entity)
    assert _fire(kind, window, entity) == 1
    for unsubscribe in made:  # what SceneController._clear_scene_event_subscriptions does on a scene change
        unsubscribe()
    assert _count(window.event_bus) == baseline
    assert _fire(kind, window, entity) == 1


@pytest.mark.parametrize("kind", KINDS)
def test_readding_after_removal_works(kind: str) -> None:
    window = _Window()
    entity = MagicMock()
    first = _make(kind, window, entity)
    first.on_destroy()
    baseline = _count(window.event_bus)
    second = _make(kind, window, entity)
    assert _count(window.event_bus) == baseline + 1
    assert _fire(kind, window, entity) == 1
    second.on_destroy()
    assert _count(window.event_bus) == baseline


@pytest.mark.parametrize("kind", KINDS)
def test_non_mesh_bus_never_subscribes_and_teardown_is_quiet(kind: str, capsys: pytest.CaptureFixture[str]) -> None:
    window = _Window()
    window.event_bus = MagicMock()  # not a MeshEventBus: the behaviour does not subscribe
    behaviour = _make(kind, window, MagicMock())
    window.event_bus.subscribe.assert_not_called()
    behaviour.on_destroy()
    assert "ERROR" not in capsys.readouterr().out
