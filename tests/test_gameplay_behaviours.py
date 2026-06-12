"""Tests for GameplayEventBus and canonical behaviours.

Tests cover:
- Config validation with actionable errors
- Deterministic behaviour
- Save/restore round-trip
- Event ordering
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_window():
    """Create a mock window with event bus."""
    from engine.gameplay_event_bus import GameplayEventBus

    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    window.event_bus = MagicMock()
    return window


@pytest.fixture
def mock_entity():
    """Create a mock entity."""
    entity = MagicMock()
    entity.mesh_id = "test_entity_001"
    entity.mesh_name = "TestEntity"
    entity.center_x = 100.0
    entity.center_y = 100.0
    entity.width = 32
    entity.height = 32
    return entity


# ============================================================================
# GameplayEventBus Tests
# ============================================================================

class TestGameplayEventBus:
    """Tests for GameplayEventBus."""

    def test_emit_creates_event(self):
        """Emit creates event with correct structure."""
        from engine.gameplay_event_bus import GameplayEventBus

        bus = GameplayEventBus()
        bus.emit("test_event", key="value", number=42)

        events = bus.peek()
        assert len(events) == 1

        evt = events[0]
        assert evt.event_type == "test_event"
        assert evt.payload["key"] == "value"
        assert evt.payload["number"] == 42
        assert evt.sequence == 0

    def test_ordering_is_stable(self):
        """Events maintain emission order via sequence numbers."""
        from engine.gameplay_event_bus import GameplayEventBus

        bus = GameplayEventBus()
        for i in range(10):
            bus.emit(f"event_{i}", index=i)

        events = bus.peek()
        assert len(events) == 10

        for i, evt in enumerate(events):
            assert evt.sequence == i
            assert evt.event_type == f"event_{i}"

    def test_drain_clears_queue(self):
        """Drain returns and clears all events."""
        from engine.gameplay_event_bus import GameplayEventBus

        bus = GameplayEventBus()
        bus.emit("event_a")
        bus.emit("event_b")

        drained = bus.drain()
        assert len(drained) == 2
        assert len(bus.peek()) == 0

    def test_save_restore_roundtrip(self):
        """Save/restore preserves events and sequence."""
        from engine.gameplay_event_bus import GameplayEventBus

        bus1 = GameplayEventBus()
        bus1.emit("event_1", data=1)
        bus1.emit("event_2", data=2)

        state = bus1.saveable_state()

        bus2 = GameplayEventBus()
        bus2.restore_state(state)

        events1 = bus1.peek()
        events2 = bus2.peek()

        assert len(events2) == len(events1)
        for e1, e2 in zip(events1, events2):
            assert e1.event_type == e2.event_type
            assert e1.sequence == e2.sequence
            assert e1.payload == e2.payload

    def test_clear_resets_queue(self):
        """Clear removes all events."""
        from engine.gameplay_event_bus import GameplayEventBus

        bus = GameplayEventBus()
        bus.emit("event_1")
        bus.emit("event_2")
        bus.clear()

        assert len(bus.peek()) == 0

    def test_validate_event_type(self):
        """Event type validation catches invalid types."""
        from engine.gameplay_event_bus import validate_event_type

        # Valid
        assert validate_event_type("on_enter") == []
        assert validate_event_type("quest_completed") == []

        # Invalid - empty
        errors = validate_event_type("")
        assert len(errors) == 1
        assert "empty" in errors[0].message.lower()

        # Invalid - spaces (message mentions alphanumeric/underscores)
        errors = validate_event_type("has space")
        assert len(errors) == 1
        assert "alphanumeric" in errors[0].message.lower() or "underscore" in errors[0].message.lower()


# ============================================================================
# TriggerVolume Tests
# ============================================================================

class TestTriggerVolume:
    """Tests for TriggerVolumeBehaviour."""

    def test_rect_detection(self, mock_window, mock_entity):
        """Rect trigger detects entity entering/exiting."""
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

        behaviour = TriggerVolumeBehaviour(
            mock_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
        )

        # Create a target entity inside the trigger
        target = MagicMock()
        target.mesh_id = "target_001"
        target.mesh_name = "Target"
        target.center_x = mock_entity.center_x + 20
        target.center_y = mock_entity.center_y + 20
        target.mesh_tags = []  # Will match because target_tags is empty

        mock_window.scene_controller = MagicMock()
        mock_window.scene_controller.all_sprites = [target]

        # Update should detect entry
        behaviour.update(0.016)

        events = mock_window.gameplay_event_bus.peek()
        enter_events = [e for e in events if e.event_type == "on_enter"]
        assert len(enter_events) >= 1

    def test_config_validation(self):
        """Config validation catches errors."""
        from engine.behaviours.trigger_volume import validate_trigger_volume_config

        # Invalid width
        errors = validate_trigger_volume_config(
            {"volume_type": "rect", "width": -10},
            entity_id="test",
        )
        assert any("width" in e.config_path for e in errors)

        # Invalid volume_type
        errors = validate_trigger_volume_config(
            {"volume_type": "invalid"},
            entity_id="test",
        )
        assert any("volume_type" in e.config_path for e in errors)

    def test_save_restore_roundtrip(self, mock_window, mock_entity):
        """Save/restore preserves trigger state."""
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

        behaviour = TriggerVolumeBehaviour(
            mock_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
            one_shot=True,
        )

        # Simulate some entities being inside
        behaviour._entities_inside = {"entity_1", "entity_2"}
        behaviour._fired_entities = {"entity_1"}

        state = behaviour.saveable_state()

        # Create new behaviour and restore
        behaviour2 = TriggerVolumeBehaviour(
            mock_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
            one_shot=True,
        )
        behaviour2.restore_state(state)

        assert behaviour2._entities_inside == {"entity_1", "entity_2"}
        assert behaviour2._fired_entities == {"entity_1"}

    def test_inspector_state(self, mock_window, mock_entity):
        """Inspector state returns expected summary."""
        from engine.behaviours.trigger_volume import TriggerVolumeBehaviour

        behaviour = TriggerVolumeBehaviour(
            mock_entity,
            mock_window,
            volume_type="rect",
            width=100,
            height=100,
        )

        state = behaviour.get_inspector_state()
        assert "enabled" in state
        assert "volume_type" in state
        assert state["volume_type"] == "rect"


# ============================================================================
# Interactable Tests
# ============================================================================

class TestInteractable:
    """Tests for InteractableBehaviour."""

    def test_interaction_emits_event(self, mock_window, mock_entity):
        """Successful interaction emits on_interact event."""
        from engine.behaviours.interactable import InteractableBehaviour

        behaviour = InteractableBehaviour(
            mock_entity,
            mock_window,
            interact_radius=50.0,
            interact_event="test_interact",
        )

        # Create interactor in range via scene_controller
        interactor = MagicMock()
        interactor.mesh_id = "player_001"
        interactor.mesh_name = "Player"
        interactor.center_x = mock_entity.center_x + 10
        interactor.center_y = mock_entity.center_y + 10
        interactor.mesh_tags = ["player"]

        mock_window.scene_controller = MagicMock()
        mock_window.scene_controller.all_sprites = [interactor]

        success = behaviour.try_interact()
        assert success

        events = mock_window.gameplay_event_bus.peek()
        interact_events = [e for e in events if e.event_type == "test_interact"]
        assert len(interact_events) == 1

    def test_cooldown_prevents_spam(self, mock_window, mock_entity):
        """Cooldown prevents rapid interactions."""
        from engine.behaviours.interactable import InteractableBehaviour

        behaviour = InteractableBehaviour(
            mock_entity,
            mock_window,
            interact_radius=50.0,
            cooldown=1.0,
        )

        interactor = MagicMock()
        interactor.mesh_id = "player_001"
        interactor.center_x = mock_entity.center_x
        interactor.center_y = mock_entity.center_y
        interactor.mesh_tags = ["player"]

        mock_window.scene_controller = MagicMock()
        mock_window.scene_controller.all_sprites = [interactor]

        # First interaction succeeds
        behaviour.try_interact()
        assert behaviour._cooldown_remaining > 0

        # Second interaction fails due to cooldown
        success = behaviour.try_interact()
        assert not success

    def test_one_shot_consumed(self, mock_window, mock_entity):
        """One-shot interactions are consumed after use."""
        from engine.behaviours.interactable import InteractableBehaviour

        behaviour = InteractableBehaviour(
            mock_entity,
            mock_window,
            interact_radius=50.0,
            one_shot=True,
            cooldown=0,
        )

        interactor = MagicMock()
        interactor.mesh_id = "player_001"
        interactor.center_x = mock_entity.center_x
        interactor.center_y = mock_entity.center_y
        interactor.mesh_tags = ["player"]

        mock_window.scene_controller = MagicMock()
        mock_window.scene_controller.all_sprites = [interactor]

        # First interaction succeeds
        success1 = behaviour.try_interact()
        assert success1
        assert behaviour._consumed

        # Second interaction fails
        success2 = behaviour.try_interact()
        assert not success2

    def test_save_restore_roundtrip(self, mock_window, mock_entity):
        """Save/restore preserves interaction state."""
        from engine.behaviours.interactable import InteractableBehaviour

        behaviour = InteractableBehaviour(
            mock_entity,
            mock_window,
            interact_radius=50.0,
            one_shot=True,
        )

        behaviour._interaction_count = 5
        behaviour._cooldown_remaining = 0.5
        behaviour._consumed = True

        state = behaviour.saveable_state()

        behaviour2 = InteractableBehaviour(
            mock_entity,
            mock_window,
            interact_radius=50.0,
            one_shot=True,
        )
        behaviour2.restore_state(state)

        assert behaviour2._interaction_count == 5
        assert behaviour2._cooldown_remaining == 0.5
        assert behaviour2._consumed


# ============================================================================
# Timer Tests
# ============================================================================

class TestTimer:
    """Tests for TimerBehaviour."""

    def test_fires_after_duration(self, mock_window, mock_entity):
        """Timer fires event after duration."""
        from engine.behaviours.timer import TimerBehaviour

        behaviour = TimerBehaviour(
            mock_entity,
            mock_window,
            duration=1.0,
            timer_event="timer_fired",
        )

        # Update for less than duration
        behaviour.update(0.5)
        events = mock_window.gameplay_event_bus.peek()
        timer_events = [e for e in events if e.event_type == "timer_fired"]
        assert len(timer_events) == 0

        # Update past duration
        behaviour.update(0.6)
        events = mock_window.gameplay_event_bus.peek()
        timer_events = [e for e in events if e.event_type == "timer_fired"]
        assert len(timer_events) == 1

    def test_repeat_fires_multiple(self, mock_window, mock_entity):
        """Repeat timer fires multiple times."""
        from engine.behaviours.timer import TimerBehaviour

        behaviour = TimerBehaviour(
            mock_entity,
            mock_window,
            duration=0.5,
            repeat=True,
            repeat_count=3,
            timer_event="timer_fired",
        )

        # Update for 2 seconds (should fire 3 times then stop)
        for _ in range(40):  # 40 * 0.05 = 2 seconds
            behaviour.update(0.05)

        events = mock_window.gameplay_event_bus.peek()
        timer_events = [e for e in events if e.event_type == "timer_fired"]
        assert len(timer_events) == 3

    def test_pause_resume(self, mock_window, mock_entity):
        """Pause/resume stops and continues timer."""
        from engine.behaviours.timer import TimerBehaviour

        behaviour = TimerBehaviour(
            mock_entity,
            mock_window,
            duration=1.0,
            timer_event="timer_fired",
        )

        behaviour.update(0.4)
        elapsed_before_pause = behaviour._elapsed

        behaviour.pause()
        behaviour.update(0.5)  # Should not accumulate

        assert behaviour._elapsed == elapsed_before_pause

        behaviour.resume()
        behaviour.update(0.7)  # Should now complete

        events = mock_window.gameplay_event_bus.peek()
        timer_events = [e for e in events if e.event_type == "timer_fired"]
        assert len(timer_events) == 1

    def test_deterministic_timing(self, mock_window, mock_entity):
        """Timer updates are deterministic with same dt sequence."""
        from engine.behaviours.timer import TimerBehaviour

        dt_sequence = [0.016, 0.017, 0.015, 0.016, 0.018, 0.016]

        # Run twice with same sequence
        results = []
        for _ in range(2):
            bus = type(mock_window.gameplay_event_bus)()
            mock_window.gameplay_event_bus = bus

            behaviour = TimerBehaviour(
                mock_entity,
                mock_window,
                duration=0.05,
                repeat=True,
                timer_event="timer_fired",
            )

            for dt in dt_sequence:
                behaviour.update(dt)

            events = bus.peek()
            results.append([e.sequence for e in events])

        # Both runs should have same results
        assert results[0] == results[1]

    def test_save_restore_roundtrip(self, mock_window, mock_entity):
        """Save/restore preserves timer state."""
        from engine.behaviours.timer import TimerBehaviour

        behaviour = TimerBehaviour(
            mock_entity,
            mock_window,
            duration=1.0,
        )

        behaviour.update(0.4)
        behaviour.pause()

        state = behaviour.saveable_state()

        behaviour2 = TimerBehaviour(
            mock_entity,
            mock_window,
            duration=1.0,
        )
        behaviour2.restore_state(state)

        assert abs(behaviour2._elapsed - 0.4) < 0.0001
        assert behaviour2._paused

    def test_config_validation(self):
        """Config validation catches errors."""
        from engine.behaviours.timer import validate_timer_config

        # Invalid duration
        errors = validate_timer_config(
            {"duration": -1},
            entity_id="test",
        )
        assert any("duration" in e.config_path for e in errors)

        # Invalid repeat_count
        errors = validate_timer_config(
            {"repeat_count": -5},
            entity_id="test",
        )
        assert any("repeat_count" in e.config_path for e in errors)


# ============================================================================
# DialogueRunner Tests
# ============================================================================

class TestDialogueRunner:
    """Tests for DialogueRunnerBehaviour."""

    @pytest.fixture
    def sample_script(self):
        """Sample dialogue script for testing."""
        return {
            "start": {
                "text": "Hello there!",
                "speaker": "NPC",
                "choices": [
                    {"text": "Hi!", "next": "greet_response"},
                    {"text": "Goodbye", "next": "farewell"},
                ],
            },
            "greet_response": {
                "text": "Nice to meet you!",
                "speaker": "NPC",
                "next": "end_node",
            },
            "farewell": {
                "text": "See you later!",
                "speaker": "NPC",
                "next": None,
            },
            "end_node": {
                "text": "That's all for now.",
                "speaker": "NPC",
            },
        }

    def test_start_dialogue(self, mock_window, mock_entity, sample_script):
        """Starting dialogue emits events."""
        from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour

        behaviour = DialogueRunnerBehaviour(
            mock_entity,
            mock_window,
            script=sample_script,
            start_node="start",
        )

        success = behaviour.start()
        assert success
        assert behaviour.is_running
        assert behaviour.current_node == "start"

        events = mock_window.gameplay_event_bus.peek()
        start_events = [e for e in events if e.event_type == "dialogue_started"]
        assert len(start_events) == 1

    def test_make_choice(self, mock_window, mock_entity, sample_script):
        """Making a choice advances dialogue."""
        from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour

        behaviour = DialogueRunnerBehaviour(
            mock_entity,
            mock_window,
            script=sample_script,
            start_node="start",
        )

        behaviour.start()
        mock_window.gameplay_event_bus.clear()

        success = behaviour.choose(0)  # "Hi!"
        assert success
        assert behaviour.current_node == "greet_response"

        events = mock_window.gameplay_event_bus.peek()
        choice_events = [e for e in events if e.event_type == "dialogue_choice"]
        assert len(choice_events) == 1

    def test_auto_advance(self, mock_window, mock_entity, sample_script):
        """Auto-advance mode progresses automatically."""
        from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour

        behaviour = DialogueRunnerBehaviour(
            mock_entity,
            mock_window,
            script={
                "start": {"text": "One", "next": "two"},
                "two": {"text": "Two", "next": "three"},
                "three": {"text": "Three"},
            },
            start_node="start",
            auto_advance=True,
        )

        behaviour.start()

        # Should auto-advance through all nodes
        assert behaviour._completed

    def test_save_restore_roundtrip(self, mock_window, mock_entity, sample_script):
        """Save/restore preserves dialogue state."""
        from engine.behaviours.dialogue_runner import DialogueRunnerBehaviour

        behaviour = DialogueRunnerBehaviour(
            mock_entity,
            mock_window,
            script=sample_script,
            start_node="start",
        )

        behaviour.start()
        behaviour.choose(0)  # Go to greet_response

        state = behaviour.saveable_state()

        behaviour2 = DialogueRunnerBehaviour(
            mock_entity,
            mock_window,
            script=sample_script,
            start_node="start",
        )
        behaviour2.restore_state(state)

        assert behaviour2.current_node == "greet_response"
        assert behaviour2.is_running
        assert "start" in behaviour2._visited_nodes

    def test_config_validation(self):
        """Config validation catches script errors."""
        from engine.behaviours.dialogue_runner import validate_dialogue_runner_config

        # Invalid node reference
        errors = validate_dialogue_runner_config(
            {
                "script": {
                    "start": {
                        "text": "Hi",
                        "choices": [{"text": "Bye", "next": "nonexistent"}],
                    },
                },
            },
            entity_id="test",
        )
        assert any("nonexistent" in e.message for e in errors)

        # Invalid start_node
        errors = validate_dialogue_runner_config(
            {
                "script": {"start": {"text": "Hi"}},
                "start_node": "missing",
            },
            entity_id="test",
        )
        assert any("missing" in e.message for e in errors)


# ============================================================================
# QuestHook Tests
# ============================================================================

class TestQuestHook:
    """Tests for QuestHookBehaviour."""

    def test_handle_event_increments_counter(self, mock_window, mock_entity):
        """Handling event increments counter."""
        from engine.behaviours.quest_hook import QuestHookBehaviour

        behaviour = QuestHookBehaviour(
            mock_entity,
            mock_window,
            quest_id="test_quest",
            listen_events=["enemy_killed"],
            target_count=5,
            increment=1,
        )

        # Handle events
        behaviour.handle_event({"enemy": "goblin"})
        assert behaviour.current_count == 1

        behaviour.handle_event({"enemy": "orc"})
        assert behaviour.current_count == 2

    def test_completion_emits_event(self, mock_window, mock_entity):
        """Reaching target count emits completion event."""
        from engine.behaviours.quest_hook import QuestHookBehaviour

        behaviour = QuestHookBehaviour(
            mock_entity,
            mock_window,
            quest_id="test_quest",
            listen_events=["item_collected"],
            target_count=2,
        )

        behaviour.handle_event({})
        behaviour.handle_event({})

        assert behaviour.is_completed

        events = mock_window.gameplay_event_bus.peek()
        complete_events = [e for e in events if e.event_type == "quest_step_completed"]
        assert len(complete_events) == 1

    def test_event_filter(self, mock_window, mock_entity):
        """Event filter restricts which events count."""
        from engine.behaviours.quest_hook import QuestHookBehaviour

        behaviour = QuestHookBehaviour(
            mock_entity,
            mock_window,
            quest_id="test_quest",
            listen_events=["item_collected"],
            event_filter={"item_type": "coin"},
            target_count=3,
        )

        # Non-matching event
        behaviour.handle_event({"item_type": "gem"})
        assert behaviour.current_count == 0

        # Matching event
        behaviour.handle_event({"item_type": "coin"})
        assert behaviour.current_count == 1

    def test_one_shot_only_triggers_once(self, mock_window, mock_entity):
        """One-shot hook only triggers once."""
        from engine.behaviours.quest_hook import QuestHookBehaviour

        behaviour = QuestHookBehaviour(
            mock_entity,
            mock_window,
            quest_id="test_quest",
            listen_events=["trigger_hit"],
            one_shot=True,
            target_count=-1,
        )

        behaviour.handle_event({})
        assert behaviour.current_count == 1

        behaviour.handle_event({})
        assert behaviour.current_count == 1  # Still 1

    def test_save_restore_roundtrip(self, mock_window, mock_entity):
        """Save/restore preserves quest state."""
        from engine.behaviours.quest_hook import QuestHookBehaviour

        behaviour = QuestHookBehaviour(
            mock_entity,
            mock_window,
            quest_id="test_quest",
            listen_events=["enemy_killed"],
            target_count=5,
        )

        behaviour.handle_event({})
        behaviour.handle_event({})

        state = behaviour.saveable_state()

        behaviour2 = QuestHookBehaviour(
            mock_entity,
            mock_window,
            quest_id="test_quest",
            listen_events=["enemy_killed"],
            target_count=5,
        )
        behaviour2.restore_state(state)

        assert behaviour2.current_count == 2
        assert behaviour2._event_count == 2

    def test_config_validation(self):
        """Config validation catches errors."""
        from engine.behaviours.quest_hook import validate_quest_hook_config

        # Missing quest_id
        errors = validate_quest_hook_config(
            {"listen_events": ["test"]},
            entity_id="test",
        )
        assert any("quest_id" in e.config_path for e in errors)

        # Empty listen_events
        errors = validate_quest_hook_config(
            {"quest_id": "test", "listen_events": []},
            entity_id="test",
        )
        assert any("listen_events" in e.config_path for e in errors)

        # Invalid target_count
        errors = validate_quest_hook_config(
            {"quest_id": "test", "listen_events": ["x"], "target_count": 0},
            entity_id="test",
        )
        assert any("target_count" in e.config_path for e in errors)


# ============================================================================
# Determinism Tests
# ============================================================================

class TestDeterminism:
    """Tests for deterministic behaviour across runs."""

    def test_event_ordering_is_deterministic(self, mock_window, mock_entity):
        """Events maintain deterministic ordering."""
        from engine.behaviours.timer import TimerBehaviour

        # Run multiple times with same inputs
        sequences = []
        for _ in range(3):
            from engine.gameplay_event_bus import GameplayEventBus
            bus = GameplayEventBus()
            mock_window.gameplay_event_bus = bus

            timer1 = TimerBehaviour(
                mock_entity,
                mock_window,
                duration=0.1,
                timer_event="timer_a",
                timer_id="a",
            )
            timer2 = TimerBehaviour(
                mock_entity,
                mock_window,
                duration=0.15,
                timer_event="timer_b",
                timer_id="b",
            )

            for _ in range(10):
                timer1.update(0.05)
                timer2.update(0.05)

            events = bus.peek()
            sequences.append([(e.event_type, e.sequence) for e in events])

        # All runs should produce same sequence
        assert sequences[0] == sequences[1] == sequences[2]
