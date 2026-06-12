import unittest
from unittest.mock import MagicMock

from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quest_manager import QuestManager


class TestEventDispatchContract(unittest.TestCase):
    def test_dispatch_chain(self):
        # Setup
        window = MagicMock()
        controller = GameStateController(window)

        # Mock QuestManager to verify it receives events
        controller.quests = MagicMock(spec=QuestManager)

        # 1. Emit event via controller
        event = MeshEvent("test_event", {"foo": "bar"})
        controller.handle_event(event)

        # Verify QuestManager received it with controller context
        controller.quests.handle_event.assert_called_once_with(event, controller)

    def test_dict_event_dispatch(self):
        # Setup
        window = MagicMock()
        controller = GameStateController(window)
        controller.quests = MagicMock(spec=QuestManager)

        # 1. Emit dict event (trace style)
        event_dict = {"name": "trace_event", "payload": {}}
        controller.handle_event(event_dict)

        # Verify QuestManager received it
        controller.quests.handle_event.assert_called_once_with(event_dict, controller)

if __name__ == "__main__":
    unittest.main()
