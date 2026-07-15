"""Lock tests: subscribed_event_types() declarations for migrated behaviours.

Per-class invariants (17 tests) + end-to-end belt tests (2 tests) = 19 total.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    sc.layers = {}
    sc.window = SimpleNamespace(strict_mode=False)
    return sc


def _sprite(behaviours: list[Any]) -> Any:
    return SimpleNamespace(
        mesh_name="test_sprite",
        mesh_behaviours_runtime=behaviours,
    )


def _evt(t: str) -> Any:
    from engine.events import MeshEvent

    return MeshEvent(type=t, payload={})


# ---------------------------------------------------------------------------
# Per-class invariants
# ---------------------------------------------------------------------------


def test_main_menu_subscribed_event_types_returns_empty_frozenset() -> None:
    """Lock: MainMenuBehaviour.subscribed_event_types() is always frozenset()."""
    from engine.behaviours.main_menu import MainMenuBehaviour

    b = object.__new__(MainMenuBehaviour)
    assert b.subscribed_event_types() == frozenset()


def test_interactable_subscribed_event_types_returns_empty_frozenset() -> None:
    """Lock: InteractableBehaviour no longer listens for input events directly."""
    from engine.behaviours.interactable import InteractableBehaviour

    b = object.__new__(InteractableBehaviour)
    assert b.subscribed_event_types() == frozenset()


def test_dialogue_subscribed_event_types_configured() -> None:
    """Lock: Dialogue with start_event set returns frozenset({start_event})."""
    from engine.behaviours.dialogue import Dialogue

    b = object.__new__(Dialogue)
    b.start_event = "start_scene"
    assert b.subscribed_event_types() == frozenset({"start_scene"})


def test_dialogue_subscribed_event_types_unconfigured() -> None:
    """Lock: Dialogue with empty start_event returns frozenset()."""
    from engine.behaviours.dialogue import Dialogue

    b = object.__new__(Dialogue)
    b.start_event = ""
    assert b.subscribed_event_types() == frozenset()


def test_emit_event_on_event_subscribed_event_types_configured() -> None:
    """Lock: EmitEventOnEvent with listen_event set returns frozenset({listen_event})."""
    from engine.behaviours.emit_event_on_event import EmitEventOnEvent

    b = object.__new__(EmitEventOnEvent)
    b.listen_event = "some_event"
    assert b.subscribed_event_types() == frozenset({"some_event"})


def test_emit_event_on_event_subscribed_event_types_unconfigured() -> None:
    """Lock: EmitEventOnEvent with empty listen_event returns frozenset()."""
    from engine.behaviours.emit_event_on_event import EmitEventOnEvent

    b = object.__new__(EmitEventOnEvent)
    b.listen_event = ""
    assert b.subscribed_event_types() == frozenset()


def test_listen_for_event_subscribed_event_types_configured() -> None:
    """Lock: ListenForEvent with event_type set returns frozenset({event_type})."""
    from engine.behaviours.listen_for_event import ListenForEvent

    b = object.__new__(ListenForEvent)
    b.event_type = "player_died"
    assert b.subscribed_event_types() == frozenset({"player_died"})


def test_listen_for_event_subscribed_event_types_unconfigured() -> None:
    """Lock: ListenForEvent with empty event_type returns frozenset()."""
    from engine.behaviours.listen_for_event import ListenForEvent

    b = object.__new__(ListenForEvent)
    b.event_type = ""
    assert b.subscribed_event_types() == frozenset()


def test_offer_perk_choice_subscribed_event_types_configured() -> None:
    """Lock: OfferPerkChoice with start_event set returns frozenset({start_event})."""
    from engine.behaviours.offer_perk_choice import OfferPerkChoice

    b = object.__new__(OfferPerkChoice)
    b.start_event = "level_up"
    assert b.subscribed_event_types() == frozenset({"level_up"})


def test_offer_perk_choice_subscribed_event_types_unconfigured() -> None:
    """Lock: OfferPerkChoice with empty start_event returns frozenset()."""
    from engine.behaviours.offer_perk_choice import OfferPerkChoice

    b = object.__new__(OfferPerkChoice)
    b.start_event = ""
    assert b.subscribed_event_types() == frozenset()


def test_quest_progress_subscribed_event_types_configured() -> None:
    """Lock: QuestProgressOnEvent with event_type set returns frozenset({event_type})."""
    from engine.behaviours.quest_progress import QuestProgressOnEvent

    b = object.__new__(QuestProgressOnEvent)
    b.event_type = "enemy_killed"
    assert b.subscribed_event_types() == frozenset({"enemy_killed"})


def test_quest_progress_subscribed_event_types_unconfigured() -> None:
    """Lock: QuestProgressOnEvent with empty event_type returns frozenset()."""
    from engine.behaviours.quest_progress import QuestProgressOnEvent

    b = object.__new__(QuestProgressOnEvent)
    b.event_type = ""
    assert b.subscribed_event_types() == frozenset()


def test_scene_transition_subscribed_event_types_configured() -> None:
    """Lock: SceneTransition with event_type set returns frozenset({event_type})."""
    from engine.behaviours.scene_transition import SceneTransition

    b = object.__new__(SceneTransition)
    b.event_type = "portal_entered"
    assert b.subscribed_event_types() == frozenset({"portal_entered"})


def test_scene_transition_subscribed_event_types_unconfigured() -> None:
    """Lock: SceneTransition with empty event_type returns frozenset()."""
    from engine.behaviours.scene_transition import SceneTransition

    b = object.__new__(SceneTransition)
    b.event_type = ""
    assert b.subscribed_event_types() == frozenset()


def test_set_game_state_on_event_subscribed_event_types_configured() -> None:
    """Lock: SetGameStateOnEvent with event_type set returns frozenset({event_type})."""
    from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent

    b = object.__new__(SetGameStateOnEvent)
    b.event_type = "boss_defeated"
    assert b.subscribed_event_types() == frozenset({"boss_defeated"})


def test_set_game_state_on_event_subscribed_event_types_unconfigured() -> None:
    """Lock: SetGameStateOnEvent with empty event_type returns frozenset()."""
    from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent

    b = object.__new__(SetGameStateOnEvent)
    b.event_type = ""
    assert b.subscribed_event_types() == frozenset()


def test_sequence_player_subscribed_event_types_returns_none() -> None:
    """Lock: SequencePlayer does NOT override subscribed_event_types(); inherits None wildcard."""
    from engine.behaviours.sequence_player import SequencePlayer

    b = object.__new__(SequencePlayer)
    assert b.subscribed_event_types() is None


# ---------------------------------------------------------------------------
# End-to-end belt tests: filter + real class integration
# ---------------------------------------------------------------------------


def test_belt_listen_for_event_configured_delivers_matching_only() -> None:
    """E2E: configured ListenForEvent fires only for its subscribed type.

    Delivers ["target_event", "other_event"] to a once=True instance.
    Only "target_event" matches → _consumed flips to True exactly once.
    "other_event" must be filtered before on_event is called (not just early-returned).
    """
    from engine.behaviours.listen_for_event import ListenForEvent

    entity = SimpleNamespace(mesh_entity_data={}, mesh_name="belt_entity")
    window = SimpleNamespace()
    b = ListenForEvent(entity, window, event_type="target_event", once=True)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite([b])]}
    sc._deliver_events_to_behaviours([_evt("target_event"), _evt("other_event")])

    assert b._consumed is True, (
        "on_event must fire for 'target_event' → _consumed=True (once=True)"
    )


def test_belt_listen_for_event_unconfigured_never_fires() -> None:
    """E2E: unconfigured ListenForEvent (event_type='') never fires for any event.

    subscribed_event_types() returns frozenset(), so the filter skips delivery
    entirely — on_event is never called and _consumed stays False.
    """
    from engine.behaviours.listen_for_event import ListenForEvent

    entity = SimpleNamespace(mesh_entity_data={}, mesh_name="belt_entity")
    window = SimpleNamespace()
    b = ListenForEvent(entity, window, event_type="", once=True)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite([b])]}
    sc._deliver_events_to_behaviours([_evt("target_event"), _evt("other_event")])

    assert b._consumed is False, (
        "Unconfigured ListenForEvent must never fire: subscribed_event_types()=frozenset()"
    )
