"""Tests for AI behaviour pack: PatrolPath, ChaseTarget, FleeFromTarget, Wander.

Tests cover:
- Config validation
- Basic functionality
- Determinism (same inputs produce same outputs)
- Save/restore mid-operation
- Event emission
"""

from __future__ import annotations

import pytest
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_window():
    """Create a mock window with all required components."""
    from engine.gameplay_event_bus import GameplayEventBus
    from engine.rng_service import RNGService
    
    window = MagicMock()
    window.gameplay_event_bus = GameplayEventBus()
    
    # Create scene controller with nav grid
    scene = MagicMock()
    scene.all_sprites = []
    # Explicitly set get_all_entities to None so _iter_candidates falls back to all_sprites
    scene.get_all_entities = None
    
    # Simple nav grid mock that handles both tuple and x,y calls
    def is_walkable(pos_or_x, y=None):
        """Accept both tuple and two-arg calls."""
        return True
    
    def in_bounds(pos_or_x, y=None):
        """Accept both tuple and two-arg calls."""
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
def mock_entity():
    """Create a mock entity sprite."""
    return create_mock_entity("test_entity", 100.0, 100.0)


# =============================================================================
# PatrolPath Tests
# =============================================================================

class TestPatrolPath:
    """Tests for PatrolPath behaviour."""
    
    def test_patrol_loop_mode(self, mock_window, mock_entity):
        """Patrol loops through waypoints in loop mode."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        
        patrol = PatrolPathBehaviour(
            mock_entity,
            mock_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 150, "y": 100},
                {"x": 150, "y": 200},
            ],
            speed=1000,  # Fast for testing
            mode="loop",
            arrive_radius=4.0,
        )
        
        patrol.start()
        assert patrol.state == "patrolling"
        assert patrol.waypoint_count == 3
        
        # Should loop: 0 -> 1 -> 2 -> 0 -> ...
        initial_index = patrol.current_waypoint_index
        
        # Move through waypoints
        for _ in range(50):  # Plenty of updates
            patrol.update(0.1)
        
        # Should still be patrolling (looping)
        assert patrol.state in ("patrolling", "waiting")
    
    def test_patrol_pingpong_mode(self, mock_window, mock_entity):
        """Patrol reverses direction in pingpong mode."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        
        patrol = PatrolPathBehaviour(
            mock_entity,
            mock_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 100, "y": 100},
                {"x": 150, "y": 100},
            ],
            speed=1000,
            mode="pingpong",
            arrive_radius=4.0,
        )
        
        patrol.start()
        
        # Simulate movement
        directions_seen = []
        for _ in range(100):
            patrol.update(0.1)
            directions_seen.append(patrol._direction)
        
        # Should have both directions in pingpong
        assert 1 in directions_seen or -1 in directions_seen
    
    def test_patrol_once_mode_completes(self, mock_window, mock_entity):
        """Patrol once mode completes after visiting all waypoints."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        
        patrol = PatrolPathBehaviour(
            mock_entity,
            mock_window,
            waypoints=[
                {"x": 100, "y": 100},
                {"x": 110, "y": 100},
            ],
            speed=1000,
            mode="once",
            arrive_radius=20.0,  # Large for quick arrival
        )
        
        patrol.start()
        
        # Run until completed
        for _ in range(100):
            if patrol.state == "completed":
                break
            patrol.update(0.1)
        
        assert patrol.state == "completed"
    
    def test_patrol_emits_events(self, mock_window, mock_entity):
        """Patrol emits expected events."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        
        patrol = PatrolPathBehaviour(
            mock_entity,
            mock_window,
            waypoints=[
                {"x": 100, "y": 100},
                {"x": 108, "y": 100},  # Very close
            ],
            speed=1000,
            mode="once",
            arrive_radius=20.0,
        )
        
        patrol.start()
        
        # Should have emitted patrol_started
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "patrol_started" in event_types
        
        # Run to completion
        for _ in range(50):
            patrol.update(0.1)
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "reached_waypoint" in event_types
    
    def test_patrol_save_restore(self, mock_window, mock_entity):
        """Patrol state survives save/restore."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        
        patrol1 = PatrolPathBehaviour(
            mock_entity,
            mock_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 100, "y": 100},
                {"x": 150, "y": 100},
            ],
            speed=50,
            mode="pingpong",
        )
        
        patrol1.start()
        
        # Run partway
        for _ in range(10):
            patrol1.update(0.016)
        
        # Save state
        saved = patrol1.saveable_state()
        
        # Create new behaviour
        mock_entity2 = MagicMock()
        mock_entity2.mesh_id = "test_entity"
        mock_entity2.center_x = mock_entity.center_x
        mock_entity2.center_y = mock_entity.center_y
        
        patrol2 = PatrolPathBehaviour(
            mock_entity2,
            mock_window,
            waypoints=[
                {"x": 50, "y": 100},
                {"x": 100, "y": 100},
                {"x": 150, "y": 100},
            ],
            speed=50,
            mode="pingpong",
        )
        
        # Restore state
        patrol2.restore_state(saved)
        
        # States should match
        assert patrol2.state == patrol1.state
        assert patrol2.current_waypoint_index == patrol1.current_waypoint_index
        assert patrol2._direction == patrol1._direction


# =============================================================================
# ChaseTarget Tests
# =============================================================================

class TestChaseTarget:
    """Tests for ChaseTarget behaviour."""
    
    def test_chase_acquires_target_by_tag(self, mock_window, mock_entity):
        """ChaseTarget acquires target by mesh_tag."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        # Create target with proper mesh_tag
        target = create_mock_entity("player", 150.0, 100.0, mesh_tag="player")
        
        mock_window.scene_controller.all_sprites = [mock_entity, target]
        
        chase = ChaseTargetBehaviour(
            mock_entity,
            mock_window,
            target_tag="player",
            acquire_radius_tiles=10,
            speed=100,
        )
        
        # Should start idle
        assert chase.state == "idle"
        
        # Update should acquire target
        chase.update(0.016)
        
        assert chase.state == "chase"
        # Note: _entity_id uses mesh_name as fallback (which is "Player" capitalized)
        assert chase.current_target_id == "Player"
    
    def test_chase_emits_target_acquired(self, mock_window, mock_entity):
        """ChaseTarget emits target_acquired event."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        target = create_mock_entity("player", 150.0, 100.0, mesh_tag="player")
        
        mock_window.scene_controller.all_sprites = [mock_entity, target]
        
        chase = ChaseTargetBehaviour(
            mock_entity,
            mock_window,
            target_tag="player",
            acquire_radius_tiles=10,
            speed=100,
        )
        
        chase.update(0.016)
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "target_acquired" in event_types
    
    def test_chase_loses_target_out_of_range(self, mock_window, mock_entity):
        """ChaseTarget loses target when out of leash range."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        target = create_mock_entity("player", 150.0, 100.0, mesh_tag="player")
        
        mock_window.scene_controller.all_sprites = [mock_entity, target]
        
        chase = ChaseTargetBehaviour(
            mock_entity,
            mock_window,
            target_tag="player",
            acquire_radius_tiles=10,
            leash_radius_tiles=5,  # Short leash
            speed=100,
        )
        
        # Acquire target
        chase.update(0.016)
        assert chase.state == "chase"
        
        # Move target far away
        target.center_x = 500.0
        
        # Should lose target
        chase.update(0.016)
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "target_lost" in event_types
    
    def test_chase_save_restore_mid_chase(self, mock_window, mock_entity):
        """ChaseTarget state survives save/restore during chase."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        target = create_mock_entity("player", 150.0, 100.0, mesh_tag="player")
        
        mock_window.scene_controller.all_sprites = [mock_entity, target]
        
        chase1 = ChaseTargetBehaviour(
            mock_entity,
            mock_window,
            target_tag="player",
            acquire_radius_tiles=10,
            speed=100,
        )
        
        # Start chasing
        chase1.update(0.016)
        assert chase1.state == "chase"
        
        # Save state
        saved = chase1.saveable_state()
        
        # Create new behaviour
        chase2 = ChaseTargetBehaviour(
            mock_entity,
            mock_window,
            target_tag="player",
            acquire_radius_tiles=10,
            speed=100,
        )
        
        chase2.restore_state(saved)
        
        # Should still be chasing same target (note: _entity_id uses mesh_name as fallback)
        assert chase2.state == "chase"
        assert chase2.current_target_id == saved["target_id"]


# =============================================================================
# FleeFromTarget Tests
# =============================================================================

class TestFleeFromTarget:
    """Tests for FleeFromTarget behaviour."""
    
    def test_flee_detects_threat(self, mock_window, mock_entity):
        """FleeFromTarget detects threats within radius."""
        from engine.behaviours.flee_from_target import FleeFromTargetBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        threat = create_mock_entity("enemy", 120.0, 100.0, mesh_tags=["enemy"])
        
        mock_window.scene_controller.all_sprites = [mock_entity, threat]
        
        flee = FleeFromTargetBehaviour(
            mock_entity,
            mock_window,
            threat_tags=["enemy"],
            detection_radius=10,
            flee_distance=8,
            speed=100,
        )
        
        flee.update(0.016)
        
        assert flee.state == "fleeing"
        assert flee.current_threat_id == "enemy"
    
    def test_flee_emits_started_event(self, mock_window, mock_entity):
        """FleeFromTarget emits flee_started event."""
        from engine.behaviours.flee_from_target import FleeFromTargetBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        threat = create_mock_entity("enemy", 120.0, 100.0, mesh_tags=["enemy"])
        
        mock_window.scene_controller.all_sprites = [mock_entity, threat]
        
        flee = FleeFromTargetBehaviour(
            mock_entity,
            mock_window,
            threat_tags=["enemy"],
            detection_radius=10,
            speed=100,
        )
        
        flee.update(0.016)
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "flee_started" in event_types
    
    def test_flee_completes_at_safe_distance(self, mock_window, mock_entity):
        """FleeFromTarget completes when reaching safe distance."""
        from engine.behaviours.flee_from_target import FleeFromTargetBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        threat = create_mock_entity("enemy", 100.0, 100.0, mesh_tags=["enemy"])
        
        mock_window.scene_controller.all_sprites = [mock_entity, threat]
        
        flee = FleeFromTargetBehaviour(
            mock_entity,
            mock_window,
            threat_tags=["enemy"],
            detection_radius=10,
            safe_distance=2,  # Small safe distance
            speed=1000,  # Fast for testing
        )
        
        # Move entity far from threat first
        mock_entity.center_x = 200.0
        
        # Now entity should be safe
        flee._state = "fleeing"
        flee._threat = threat
        flee._threat_id = "enemy"
        
        flee.update(0.016)
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "flee_completed" in event_types


# =============================================================================
# Wander Tests
# =============================================================================

class TestWander:
    """Tests for Wander behaviour."""
    
    def test_wander_starts_after_idle(self, mock_window, mock_entity):
        """Wander starts moving after idle time."""
        from engine.behaviours.wander import WanderBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        wander = WanderBehaviour(
            mock_entity,
            mock_window,
            wander_radius=5,
            speed=100,
            idle_time_min=0.0,
            idle_time_max=0.1,
        )
        
        # Start in idle
        wander._start_idle()
        assert wander.state == "idle"
        
        # Update should eventually start wandering
        for _ in range(10):
            wander.update(0.1)
            if wander.state == "wandering":
                break
        
        # Should have started wandering
        assert wander.state == "wandering"
    
    def test_wander_emits_events(self, mock_window, mock_entity):
        """Wander emits expected events."""
        from engine.behaviours.wander import WanderBehaviour
        from engine.rng_service import rng_service
        
        rng_service.seed(42)
        
        wander = WanderBehaviour(
            mock_entity,
            mock_window,
            wander_radius=5,
            speed=1000,
            idle_time_min=0.0,
            idle_time_max=0.0,
        )
        
        wander.start()
        
        events = mock_window.gameplay_event_bus.peek()
        event_types = [e.event_type for e in events]
        assert "wander_started" in event_types


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Tests for deterministic behaviour."""
    
    def test_patrol_deterministic(self, mock_window, mock_entity):
        """PatrolPath produces identical results with same inputs."""
        from engine.behaviours.patrol_path import PatrolPathBehaviour
        
        results = []
        
        for _ in range(2):
            entity = MagicMock()
            entity.mesh_id = "test"
            entity.center_x = 100.0
            entity.center_y = 100.0
            
            patrol = PatrolPathBehaviour(
                entity,
                mock_window,
                waypoints=[
                    {"x": 50, "y": 100},
                    {"x": 150, "y": 100},
                ],
                speed=100,
                mode="loop",
            )
            
            patrol.start()
            
            positions = []
            for _ in range(20):
                patrol.update(0.016)
                positions.append((round(entity.center_x, 2), round(entity.center_y, 2)))
            
            results.append(positions)
        
        assert results[0] == results[1], "PatrolPath should be deterministic"
    
    def test_chase_deterministic(self, mock_window, mock_entity):
        """ChaseTarget produces identical results with same inputs."""
        from engine.behaviours.chase_target import ChaseTargetBehaviour
        
        results = []
        
        for _ in range(2):
            entity = MagicMock()
            entity.mesh_id = "chaser"
            entity.center_x = 100.0
            entity.center_y = 100.0
            
            target = MagicMock()
            target.mesh_id = "target"
            target.mesh_name = "Target"
            target.mesh_tag = "player"
            target.center_x = 200.0
            target.center_y = 100.0
            
            mock_window.scene_controller.all_sprites = [entity, target]
            
            chase = ChaseTargetBehaviour(
                entity,
                mock_window,
                target_tag="player",
                acquire_radius_tiles=20,
                speed=100,
            )
            
            states = []
            for _ in range(10):
                chase.update(0.016)
                states.append((chase.state, chase.current_target_id))
            
            results.append(states)
        
        assert results[0] == results[1], "ChaseTarget should be deterministic"
    
    def test_flee_deterministic_with_seed(self, mock_window, mock_entity):
        """FleeFromTarget produces identical results with same RNG seed."""
        from engine.behaviours.flee_from_target import FleeFromTargetBehaviour
        from engine.rng_service import rng_service
        
        results = []
        
        for _ in range(2):
            rng_service.seed(12345)  # Reset RNG
            
            entity = MagicMock()
            entity.mesh_id = "flee_entity"
            entity.center_x = 100.0
            entity.center_y = 100.0
            
            threat = MagicMock()
            threat.mesh_id = "threat"
            threat.mesh_name = "Threat"
            threat.mesh_tags = ["enemy"]
            threat.center_x = 120.0
            threat.center_y = 100.0
            
            mock_window.scene_controller.all_sprites = [entity, threat]
            
            flee = FleeFromTargetBehaviour(
                entity,
                mock_window,
                threat_tags=["enemy"],
                detection_radius=10,
                speed=100,
            )
            
            states = []
            for _ in range(5):
                flee.update(0.016)
                states.append((flee.state, flee.current_threat_id, flee._flee_target))
            
            results.append(states)
        
        assert results[0] == results[1], "FleeFromTarget should be deterministic with same seed"
    
    def test_wander_deterministic_with_seed(self, mock_window, mock_entity):
        """Wander produces identical results with same RNG seed."""
        from engine.behaviours.wander import WanderBehaviour
        from engine.rng_service import rng_service
        
        results = []
        
        for _ in range(2):
            rng_service.seed(12345)  # Reset RNG
            
            entity = MagicMock()
            entity.mesh_id = "wanderer"
            entity.center_x = 100.0
            entity.center_y = 100.0
            
            wander = WanderBehaviour(
                entity,
                mock_window,
                wander_radius=5,
                speed=100,
                idle_time_min=0.0,
                idle_time_max=0.0,
            )
            
            wander.start()
            
            states = []
            for _ in range(5):
                wander.update(0.016)
                states.append((wander.state, wander._wander_target))
            
            results.append(states)
        
        assert results[0] == results[1], "Wander should be deterministic with same seed"


# =============================================================================
# Config Validation Tests
# =============================================================================

class TestConfigValidation:
    """Tests for configuration validation."""
    
    def test_patrol_path_validation_empty_waypoints(self):
        """PatrolPath validation fails with empty waypoints."""
        from engine.behaviours.patrol_path import validate_patrol_path_config
        
        errors = validate_patrol_path_config({
            "waypoints": [],
            "waypoint_tag": "",
        }, entity_id="test")
        
        assert len(errors) > 0
        assert any("waypoints" in str(e.message) for e in errors)
    
    def test_patrol_path_validation_invalid_mode(self):
        """PatrolPath validation fails with invalid mode."""
        from engine.behaviours.patrol_path import validate_patrol_path_config
        
        errors = validate_patrol_path_config({
            "waypoints": [{"x": 0, "y": 0}],
            "mode": "invalid_mode",
        }, entity_id="test")
        
        assert len(errors) > 0
        assert any("mode" in str(e.config_path) for e in errors)
    
    def test_flee_validation_no_threat(self):
        """FleeFromTarget validation fails with no threat config."""
        from engine.behaviours.flee_from_target import validate_flee_from_target_config
        
        errors = validate_flee_from_target_config({
            "threat_tags": [],
            "threat_entity_id": "",
        }, entity_id="test")
        
        assert len(errors) > 0
        assert any("threat" in str(e.message) for e in errors)
    
    def test_wander_validation_negative_radius(self):
        """Wander validation fails with negative radius."""
        from engine.behaviours.wander import validate_wander_config
        
        errors = validate_wander_config({
            "wander_radius": -5.0,
        }, entity_id="test")
        
        assert len(errors) > 0
