import unittest
from unittest.mock import MagicMock

import pytest

from engine.behaviours.puzzle_behaviours import DoorLock, RewardChest, SwitchInteract
from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from tests._fake_window import fake_sprite, fake_window

pytestmark = pytest.mark.fast


class TestPuzzleBehaviours(unittest.TestCase):
    def setUp(self):
        # (spec'd: only what a real window and a real entity sprite have, S1 5.6 (c))
        self.window = fake_window(event_bus=MagicMock())
        self.entity = fake_sprite(mesh_entity_data={}, mesh_id="door_1", mesh_name="Door")

    def test_switch_interact(self):
        switch = SwitchInteract(self.entity, self.window, event_id="test_event")
        switch.on_interact(fake_sprite(mesh_name="Player"))

        # Check if emit was called with correct event
        # We can't easily check the exact object equality of MeshEvent without __eq__,
        # so we check the name and data manually or use ANY
        args = self.window.event_bus.emit.call_args[0][0]
        self.assertEqual(args.type, "test_event")
        self.assertEqual(args.payload["source"], self.entity)

    def test_switch_one_shot(self):
        switch = SwitchInteract(self.entity, self.window, event_id="test_event", one_shot=True)
        switch.on_interact(fake_sprite(mesh_name="Player"))
        self.assertEqual(self.window.event_bus.emit.call_count, 1)

        switch.on_interact(fake_sprite(mesh_name="Player"))
        self.assertEqual(self.window.event_bus.emit.call_count, 1)

    def _unlocked_door(self):
        door = DoorLock(self.entity, self.window, unlock_event="unlock_me")
        self.assertTrue(door.locked)

        # Simulate event
        door._on_unlock_event(MeshEvent("unlock_me", {}))
        self.assertFalse(door.locked)
        return self.window.event_bus.emit.call_args[0][0]

    def test_door_lock(self):
        self.assertEqual(self._unlocked_door().type, "door_unlocked")

    # A real entity sprite has mesh_id, not id: the door_unlocked payload's door_id is always "unknown" in a game.
    # (The MagicMock entity this test had answered .id; the spec'd one, like the game, doesn't.)
    @pytest.mark.xfail(strict=True, reason="#710: DoorLock's door_unlocked names door_id from entity.id")
    def test_door_unlocked_names_the_door(self):
        self.assertEqual(self._unlocked_door().payload["door_id"], "door_1")

    def test_reward_chest(self):
        chest = RewardChest(self.entity, self.window, unlock_event="reveal_me", gold=100)
        self.assertFalse(chest.enabled)

        # Unlock
        chest._on_unlock_event(MeshEvent("reveal_me", {}))
        self.assertTrue(chest.enabled)

        # Interact: the gold goes to the game's counter (#636), not to the player sprite
        self.window.game_state_controller = GameStateController(self.window)
        chest.on_interact(fake_sprite(mesh_name="Player"))

        self.assertEqual(self.window.game_state_controller.get_counter("gold"), 100)
        self.assertTrue(chest.looted)
