from unittest.mock import MagicMock

from engine.behaviours.offer_perk_choice import OfferPerkChoice
from engine.perks import PerkManager


class MockGameState:
    def __init__(self):
        self.perk_manager = PerkManager()
        self.perks = []

    def has_perk(self, perk_id):
        return perk_id in self.perks

    def add_perk(self, perk_id):
        self.perks.append(perk_id)

class MockWindow:
    def __init__(self):
        self.game_state = MockGameState()
        self.game_state_controller = self.game_state
        self.ui = MagicMock()
        self.input = MagicMock()
        self.audio = MagicMock()

def test_offer_perk_choice_start():
    window = MockWindow()
    # Setup perks
    window.game_state.perk_manager.register_perk({
        "id": "p1",
        "name": "Perk 1",
        "description": "Desc 1",
        "effects": {}
    })

    entity = MagicMock()
    behaviour = OfferPerkChoice(entity, window, pool=["p1"])

    # Trigger start
    behaviour._start_offer()

    # Verify dialogue shown
    assert window.ui.show_dialogue.called
    args = window.ui.show_dialogue.call_args[0][0] # entries
    assert len(args) == 1
    assert len(args[0]["choices"]) == 2 # p1 + cancel
    assert args[0]["choices"][0]["id"] == "p1"

def test_offer_perk_choice_select():
    window = MockWindow()
    window.game_state.perk_manager.register_perk({
        "id": "p1",
        "name": "Perk 1",
        "description": "Desc 1",
        "effects": {}
    })

    entity = MagicMock()
    behaviour = OfferPerkChoice(entity, window, pool=["p1"])

    # Start
    behaviour._start_offer()
    behaviour._active = True # Simulate active
    behaviour._cooldown = 0 # Clear cooldown

    # Mock input
    window.input.was_action_pressed.side_effect = lambda action: action == "interact"

    # Mock dialogue box submission
    window.ui.dialogue_box.is_active_for.return_value = True
    window.ui.dialogue_box.submit_choice.return_value = {"id": "p1"}

    # Update
    behaviour.update(0.1)

    # Verify perk added
    assert "p1" in window.game_state.perks
    assert window.ui.close_dialogue.called

def test_offer_perk_choice_already_owned():
    window = MockWindow()
    window.game_state.perk_manager.register_perk({
        "id": "p1",
        "name": "Perk 1",
        "description": "Desc 1",
        "effects": {}
    })
    window.game_state.add_perk("p1")

    entity = MagicMock()
    behaviour = OfferPerkChoice(entity, window, pool=["p1"])

    # Trigger start
    behaviour._start_offer()

    # Verify message shown instead of choices
    assert window.ui.show_dialogue.called
    args = window.ui.show_dialogue.call_args[0][0]
    assert len(args) == 1
    assert "choices" not in args[0] or not args[0]["choices"]
    assert args[0]["text"] == "You have learned all I can teach."
