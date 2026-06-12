import unittest
from unittest.mock import MagicMock

from engine.behaviours.puzzle_behaviours import DoorLock, RewardChest, SwitchInteract
from engine.events import MeshEvent


class TestPuzzleBehaviours(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.event_bus = MagicMock()
        self.entity = MagicMock()
        self.entity.mesh_entity_data = {}
        # Mock id for door
        self.entity.id = "door_1"

    def test_switch_interact(self):
        switch = SwitchInteract(self.entity, self.window, event_id="test_event")
        switch.on_interact(MagicMock())

        # Check if emit was called with correct event
        # We can't easily check the exact object equality of MeshEvent without __eq__,
        # so we check the name and data manually or use ANY
        args = self.window.event_bus.emit.call_args[0][0]
        self.assertEqual(args.type, "test_event")
        self.assertEqual(args.payload["source"], self.entity)

    def test_switch_one_shot(self):
        switch = SwitchInteract(self.entity, self.window, event_id="test_event", one_shot=True)
        switch.on_interact(MagicMock())
        self.assertEqual(self.window.event_bus.emit.call_count, 1)

        switch.on_interact(MagicMock())
        self.assertEqual(self.window.event_bus.emit.call_count, 1)

    def test_door_lock(self):
        door = DoorLock(self.entity, self.window, unlock_event="unlock_me")
        self.assertTrue(door.locked)

        # Simulate event
        door._on_unlock_event(MeshEvent("unlock_me", {}))
        self.assertFalse(door.locked)

        # Check emission of door_unlocked
        args = self.window.event_bus.emit.call_args[0][0]
        self.assertEqual(args.type, "door_unlocked")
        self.assertEqual(args.payload["door_id"], "door_1")

    def test_reward_chest(self):
        chest = RewardChest(self.entity, self.window, unlock_event="reveal_me", gold=100)
        self.assertFalse(chest.enabled)

        # Unlock
        chest._on_unlock_event(MeshEvent("reveal_me", {}))
        self.assertTrue(chest.enabled)

        # Interact
        player = MagicMock()
        player.inventory = MagicMock()
        chest.on_interact(player)

        player.inventory.add_gold.assert_called_with(100)
        self.assertTrue(chest.looted)
