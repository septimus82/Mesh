"""Integration test for Physics Facade v1."""
import pytest
from unittest.mock import MagicMock, patch
import engine.optional_arcade as optional_arcade

from engine.behaviours.player_controller import PlayerController

class MockSprite:
    def __init__(self, x, y, w, h):
        self.center_x = x
        self.center_y = y
        self.width = w
        self.height = h
        self.mesh_entity_data = {}
        self.mesh_behaviours_runtime = []
    
    @property
    def left(self): return self.center_x - self.width/2
    @property
    def right(self): return self.center_x + self.width/2
    @property
    def bottom(self): return self.center_y - self.height/2
    @property
    def top(self): return self.center_y + self.height/2

def test_player_controller_hits_wall():
    """Verify PlayerController uses physics facade to collide with walls."""
    
    # 1. Setup Environment
    window = MagicMock()
    window.input = MagicMock()
    # Ensure input is not blocked (MagicMock returns Truthy by default)
    window.player_input_blocked.return_value = False
    window.is_input_locked.return_value = False
    window.dialogue_blocks_input.return_value = False
    window.dialogue_box = None
    window.ui_controller = MagicMock() # Ensure ui_controller exists
    window.ui_controller.dialogue_box = None
    
    # Input: Move Right (x=1, y=0)
    # get_axis("move_left", "move_right") -> 1.0
    # get_axis("move_down", "move_up") -> 0.0
    window.input.get_axis.side_effect = [1.0, 0.0]
    
    # 2. Setup Scene & Physics
    scene = MagicMock()
    window.scene_controller = scene
    
    # Wall at x=100 (95-105)
    wall = MockSprite(100, 0, 10, 100)
    solid_sprites = [wall]
    scene.solid_sprites = solid_sprites
    
    # 3. Setup Player
    # At x=0. Speed=100.
    player = MockSprite(0, 0, 10, 10)
    controller = PlayerController(player, window, speed=100.0)
    
    # 4. Patch arcade.check_for_collision_with_list
    # PhysicsPureModel creates a proxy sprite at the FUTURE position.
    
    def mock_check_collision(sprite, sprite_list):
        hits = []
        # Sprite is the proxy from physics_runtime
        sl = sprite.center_x - sprite.width/2
        sr = sprite.center_x + sprite.width/2
        sb = sprite.center_y - sprite.height/2
        st = sprite.center_y + sprite.height/2
        
        for s in sprite_list:
            # AABB intersection check
            # s is MockSprite (has .left, .right props)
            if (sl < s.right and sr > s.left and
                sb < s.top and st > s.bottom):
                hits.append(s)
        return hits

    with patch('engine.optional_arcade.arcade.check_for_collision_with_list', side_effect=mock_check_collision):
        
        # 5. Move!
        # dt=1.0 -> Move 100 units right.
        # Player (right edge 5) + 100 = 105.
        # Wall (left edge 95).
        # Should stop at 95 (right edge) -> Center = 90.
        controller.update(1.0)
        
        # 6. Assert
        # The PlayerController updates the entity in place.
        # Note: PlayerController normalizes velocity, so (1,0) normalized is (1,0) * speed * dt = 100.
        assert player.center_x == 90.0, f"Expected 90.0 (95 - 5), got {player.center_x}"
