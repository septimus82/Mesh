"""Tests for puzzle behaviour event subscription lifecycle.

Verifies DoorLock and RewardChest correctly unsubscribe on destroy().
"""

from __future__ import annotations

from unittest.mock import MagicMock

from engine.behaviours.puzzle_behaviours import DoorLock, RewardChest


def _make_window() -> MagicMock:
    window = MagicMock()
    unsub = MagicMock()
    window.event_bus.subscribe.return_value = unsub
    return window


def _make_entity() -> MagicMock:
    entity = MagicMock()
    entity.mesh_entity_data = {}
    return entity


class TestDoorLockLifecycle:
    def test_subscribe_stores_unsubscribe(self):
        window = _make_window()
        door = DoorLock(_make_entity(), window, unlock_event="lever_pulled")
        assert door._unsubscribe is not None
        window.event_bus.subscribe.assert_called_once_with(
            "lever_pulled", door._on_unlock_event
        )

    def test_destroy_calls_unsubscribe(self):
        window = _make_window()
        unsub = window.event_bus.subscribe.return_value
        door = DoorLock(_make_entity(), window, unlock_event="lever_pulled")
        door.destroy()
        unsub.assert_called_once()
        assert door._unsubscribe is None

    def test_destroy_idempotent(self):
        window = _make_window()
        door = DoorLock(_make_entity(), window, unlock_event="lever_pulled")
        door.destroy()
        door.destroy()  # no error

    def test_no_subscribe_when_no_event(self):
        window = _make_window()
        door = DoorLock(_make_entity(), window, unlock_event="")
        assert door._unsubscribe is None
        window.event_bus.subscribe.assert_not_called()


class TestRewardChestLifecycle:
    def test_subscribe_stores_unsubscribe(self):
        window = _make_window()
        chest = RewardChest(_make_entity(), window, unlock_event="door_unlocked")
        assert chest._unsubscribe is not None
        window.event_bus.subscribe.assert_called_once_with(
            "door_unlocked", chest._on_unlock_event
        )

    def test_destroy_calls_unsubscribe(self):
        window = _make_window()
        unsub = window.event_bus.subscribe.return_value
        chest = RewardChest(_make_entity(), window, unlock_event="door_unlocked")
        chest.destroy()
        unsub.assert_called_once()
        assert chest._unsubscribe is None

    def test_destroy_idempotent(self):
        window = _make_window()
        chest = RewardChest(_make_entity(), window, unlock_event="door_unlocked")
        chest.destroy()
        chest.destroy()  # no error

    def test_no_subscribe_when_no_event(self):
        window = _make_window()
        chest = RewardChest(_make_entity(), window, unlock_event="")
        assert chest._unsubscribe is None
        window.event_bus.subscribe.assert_not_called()
