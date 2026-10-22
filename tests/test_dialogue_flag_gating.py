"""Dialogue require_flags/forbid_flags, and auto_start waiting its turn (the Ezekiel cemetery test)."""

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.dialogue import Dialogue
from tests.test_dialogue_interaction import DummyEntity, DummyWindow

pytestmark = pytest.mark.fast


class FlagWindow(DummyWindow):
    def __init__(self) -> None:
        super().__init__()
        self.flags: dict[str, bool] = {}

    def get_flag(self, name: str) -> bool:
        return self.flags.get(name, False)


def _frame(window: FlagWindow, *behaviours: Dialogue) -> None:
    window.input.update(0.016)
    for behaviour in behaviours:
        behaviour.update(0.016)


def test_require_and_forbid_flags_gate_talking() -> None:
    window = FlagWindow()
    grave = Dialogue(DummyEntity("Grave", ["The grave lies open."]), window, require_flags=["dug"], forbid_flags=["filled"])
    player = DummyEntity("Player", [])

    assert not grave.can_interact_with(player)
    window.flags["dug"] = True
    assert grave.can_interact_with(player)
    window.flags["filled"] = True
    assert not grave.can_interact_with(player)


def test_auto_start_waits_for_its_flags() -> None:
    window = FlagWindow()
    keeper = Dialogue(DummyEntity("Keeper", ["Who's there?"]), window, auto_start=True, require_flags=["third_grave"])

    _frame(window, keeper)
    assert not window.dialogue_box.is_active()

    window.flags["third_grave"] = True
    _frame(window, keeper)
    assert window.dialogue_box.get_current_entry()["text"] == "Who's there?"


def test_auto_start_does_not_cut_off_another_speaker_or_eat_their_closing_press() -> None:
    window = FlagWindow()
    grave = Dialogue(DummyEntity("Grave", ["The coffin is empty."]), window)
    keeper = Dialogue(DummyEntity("Keeper", ["Who's there?", "Grave robber!"]), window, auto_start=True, require_flags=["third_grave"])

    grave.on_interact(window, DummyEntity("Player", []))
    window.flags["third_grave"] = True  # set by the line the player is reading
    _frame(window, grave, keeper)
    assert window.dialogue_box.get_current_entry()["text"] == "The coffin is empty."

    window.input.press(optional_arcade.arcade.key.E)  # closes the grave's box; the keeper opens in the same frame
    _frame(window, grave, keeper)
    window.input.release(optional_arcade.arcade.key.E)
    _frame(window, grave, keeper)
    assert window.dialogue_box.get_current_entry()["text"] == "Who's there?"


def test_start_rules_pick_the_opening_line_from_flags() -> None:
    window = FlagWindow()
    grave = DummyEntity("Grave", [])
    grave.mesh_entity_data = {}
    dialogue = {"start": "bare", "nodes": {
        "bare": {"text": "I cannot dig with my bare hands."},
        "dig": {"text": "Start digging?"},
        "open": {"text": "The grave is already open."}},
        "starts": [{"node": "open", "require_flags": ["dug"]}, {"node": "dig", "require_flags": ["has_shovel"]}]}
    behaviour = Dialogue(grave, window, dialogue=dialogue, once=False)
    player = DummyEntity("Player", [])

    def opening() -> str:
        behaviour.on_interact(window, player)
        text = window.dialogue_box.get_current_entry()["text"]
        window.dialogue_box.clear()
        _frame(window, behaviour)
        return text

    assert opening() == "I cannot dig with my bare hands."
    window.flags["has_shovel"] = True
    assert opening() == "Start digging?"
    window.flags["dug"] = True
    assert opening() == "The grave is already open."  # first matching rule wins
