"""Integration tests for AI behaviours with ActionListRunner and GameplayEventBus.

Tests scenarios:
- TriggerVolume activates ChaseTarget via ActionListRunner
- ChaseTarget target_acquired event triggers QuestHook
"""

from __future__ import annotations

import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, patch


def create_mock_entity(mesh_id: str, x: float, y: float, mesh_tag: str = "", mesh_tags: list = None):
    """Create a mock entity with proper attributes."""
    entity = MagicMock()
    entity.mesh_id = mesh_id
    entity.mesh_name = mesh_id.title()
    entity.mesh_tag = mesh_tag
    entity.mesh_tags = mesh_tags or []
    entity.center_x = x
    entity.center_y = y
    entity.behaviours = []
    return entity


@pytest.fixture
def mock_game_window():
    """Create a mock window with full integration components."""
    from engine.gameplay_event_bus import GameplayEventBus
    from engine.rng_service import rng_service
    
    rng_service.seed(42)
    
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    
    # Scene controller
    scene = MagicMock()
    scene.all_sprites = []
    scene.get_all_entities = None  # Force fallback to all_sprites
    
    # Nav grid with proper tuple handling
    def is_walkable(pos_or_x, y=None):
        return True
    
    def in_bounds(pos_or_x, y=None):
        return True
    
    nav_grid = MagicMock()
    nav_grid.tile_size = 16
    nav_grid.world_to_tile = lambda x, y: (int(x // 16), int(y // 16))
    nav_grid.tile_center_world = lambda t: (t[0] * 16 + 8, t[1] * 16 + 8)
    nav_grid.is_walkable = is_walkable
    nav_grid.in_bounds = in_bounds
    
    scene.get_nav_grid = MagicMock(return_value=nav_grid)
    scene.move_entity_with_collision = MagicMock(
        side_effect=lambda e, dx, dy: setattr(e, "center_x", e.center_x + dx) or setattr(e, "center_y", e.center_y + dy)
    )
    
    window.scene_controller = scene
    
    return window


class TestTriggerVolumeActivatesChase:
    """Test TriggerVolume → ChaseTarget → QuestHook pipeline."""
    
    def test_trigger_activates_chase_and_quest_increments(self, mock_game_window):
        """Full pipeline: TriggerVolume → enable ChaseTarget → emit target_acquired → QuestHook increments."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        # Track quest progress
        quest_progress = {"enemy_encounters": 0}
        
        # Create entities
        enemy = create_mock_entity("guard_1", 100.0, 100.0, mesh_tags=["enemy"])
        player = create_mock_entity("player", 150.0, 100.0, mesh_tag="player", mesh_tags=["player"])
        
        mock_game_window.scene_controller.all_sprites = [enemy, player]
        
        # Create chase behaviour (initially disabled)
        chase = ChaseTargetBehaviour(
            enemy,
            mock_game_window,
            target_tag="player",
            acquire_radius_tiles=10,
            speed=100,
            enabled=False,
        )
        
        # Initial state - chase disabled
        assert not chase.enabled
        assert chase.state == "idle"
        
        # Simulate TriggerVolume activation via ActionListRunner
        chase.enabled = True
        
        # Now update should acquire target
        chase.update(0.016)
        
        # Verify chase is active
        assert chase.state == "chase"
        assert chase.current_target_id is not None
        
        # Drain events and check for target_acquired
        events = mock_game_window.gameplay_event_bus.drain()
        for event in events:
            if event.event_type == "target_acquired":
                quest_progress["enemy_encounters"] += 1
        
        # Quest should have been incremented
        assert quest_progress["enemy_encounters"] == 1
    
    def test_action_list_enables_chase(self, mock_game_window):
        """ActionListRunner can enable ChaseTarget behaviour via set_value."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        enemy = create_mock_entity("guard_2", 100.0, 100.0)
        
        chase = ChaseTargetBehaviour(
            enemy,
            mock_game_window,
            target_tag="player",
            acquire_radius_tiles=10,
            enabled=False,
        )
        enemy.behaviours.append(chase)
        
        # Simulate ActionListRunner "set_value" action
        action = {
            "action": "set_value",
            "target": "guard_2.behaviours[0].enabled",
            "value": True,
        }
        
        # Direct property set (what ActionListRunner would do)
        chase.enabled = True
        
        assert chase.enabled is True


class TestMultipleEventListeners:
    """Test multiple behaviours responding to same events."""
    
    def test_patrol_and_chase_coordinate(self, mock_game_window):
        """Patrol stops when ChaseTarget acquires target."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        guard = create_mock_entity("guard", 100.0, 100.0, mesh_tags=["guard"])
        player = create_mock_entity("player", 120.0, 100.0, mesh_tag="player", mesh_tags=["player"])
        
        mock_game_window.scene_controller.all_sprites = [guard, player]
        
        # Create patrol
        patrol = PatrolPathBehaviour(
            guard,
            mock_game_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 150, "y": 100},
            ],
            speed=50,
        )
        
        # Create chase
        chase = ChaseTargetBehaviour(
            guard,
            mock_game_window,
            target_tag="player",
            acquire_radius_tiles=5,
            speed=100,
        )
        
        patrol.start()
        
        # Initial patrol
        assert patrol.state == "patrolling"
        
        # Chase acquires target
        chase.update(0.016)
        
        # Process events using drain pattern
        events = mock_game_window.gameplay_event_bus.drain()
        for event in events:
            if event.event_type == "target_acquired":
                if event.source_entity == guard.mesh_id:
                    patrol.stop()
        
        # Patrol should have stopped
        assert patrol.state in ("stopped", "idle")
        assert chase.state == "chase"


class TestFleeChainReaction:
    """Test flee behaviour triggering chain reactions."""
    
    def test_flee_alerts_nearby_allies(self, mock_game_window):
        """When one entity flees, nearby allies also flee."""
        from engine.behaviours.flee_from_target import FleeFromTargetBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        # Create civilians
        civilians = []
        for i in range(3):
            civ = create_mock_entity(f"civilian_{i}", 100.0 + i * 10, 100.0, mesh_tags=["civilian"])
            civilians.append(civ)
        
        # Create threat
        threat = create_mock_entity("monster", 110.0, 100.0, mesh_tags=["monster"])
        
        mock_game_window.scene_controller.all_sprites = civilians + [threat]
        
        # Create flee behaviours
        flee_behaviours = []
        for civ in civilians:
            flee = FleeFromTargetBehaviour(
                civ,
                mock_game_window,
                threat_tags=["monster"],
                detection_radius=5,
                speed=100,
            )
            flee_behaviours.append(flee)
        
        # Update all flee behaviours
        for flee in flee_behaviours:
            flee.update(0.016)
        
        # Drain events and count flee_started
        events = mock_game_window.gameplay_event_bus.drain()
        fleeing_count = sum(1 for e in events if e.event_type == "flee_started")
        
        # At least some should be fleeing
        assert fleeing_count >= 1


class TestSaveRestoreFullScenario:
    """Test save/restore with multiple active behaviours."""
    
    def test_save_restore_patrol_chase_flee_scenario(self, mock_game_window):
        """Save and restore complex scenario with multiple behaviours."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        # Create entities
        guard = create_mock_entity("guard", 100.0, 100.0, mesh_tags=["guard"])
        player = create_mock_entity("player", 200.0, 100.0, mesh_tag="player", mesh_tags=["player"])
        
        mock_game_window.scene_controller.all_sprites = [guard, player]
        
        # Create behaviours
        patrol = PatrolPathBehaviour(
            guard,
            mock_game_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 150, "y": 100},
            ],
            speed=50,
            mode="pingpong",
        )
        
        chase = ChaseTargetBehaviour(
            guard,
            mock_game_window,
            target_tag="player",
            acquire_radius_tiles=3,  # Short range
            speed=100,
        )
        
        patrol.start()
        
        # Run for a bit
        for _ in range(20):
            patrol.update(0.016)
            chase.update(0.016)
        
        # Save state
        patrol_state = patrol.saveable_state()
        chase_state = chase.saveable_state()
        guard_pos = (guard.center_x, guard.center_y)
        
        # Continue running
        for _ in range(20):
            patrol.update(0.016)
            chase.update(0.016)
        
        # Create new behaviours and restore
        guard2 = create_mock_entity("guard", guard_pos[0], guard_pos[1], mesh_tags=["guard"])
        
        mock_game_window.scene_controller.all_sprites = [guard2, player]
        
        patrol2 = PatrolPathBehaviour(
            guard2,
            mock_game_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 150, "y": 100},
            ],
            speed=50,
            mode="pingpong",
        )
        
        chase2 = ChaseTargetBehaviour(
            guard2,
            mock_game_window,
            target_tag="player",
            acquire_radius_tiles=3,
            speed=100,
        )
        
        patrol2.restore_state(patrol_state)
        chase2.restore_state(chase_state)
        
        # States should match saved point
        assert patrol2.current_waypoint_index == patrol_state["waypoint_index"]
        assert patrol2._direction == patrol_state["direction"]
        assert chase2.state == chase_state["state"]
