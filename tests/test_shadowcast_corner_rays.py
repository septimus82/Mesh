import os
import pytest
import math
from unittest.mock import MagicMock, patch
from engine.lighting import LightManager

@pytest.mark.usefixtures("mock_arcade_lighting")
class TestShadowcastCornerRays:
    @pytest.fixture(autouse=True)
    def setup(self, mock_arcade_lighting):
        self.env_patcher = patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "1"})
        self.env_patcher.start()
        
        # Mock LightLayer
        self.mock_layer = MagicMock()
        self.mock_layer.add_light_polygon = MagicMock()
        
        self.lm = LightManager(MagicMock())
        self.lm.enabled = True
        self.lm._layer = self.mock_layer
        self.lm._create_layer = MagicMock(return_value=self.mock_layer)
        
        yield
        
        self.env_patcher.stop()

    def test_corner_rays_generation(self):
        # Setup a scene with one light and one occluder
        # Light at (0, 0), radius 100
        # Occluder: square at (50, -10) to (70, 10)
        # This occluder is within radius.
        # Vertices: (50, -10), (70, -10), (70, 10), (50, 10)
        
        light_config = {"x": 0, "y": 0, "radius": 100, "color": (255, 255, 255)}
        occluder_config = {"x": 50, "y": -10, "width": 20, "height": 20}
        
        self.lm.configure_scene_occluders([occluder_config])
        self.lm.configure_scene_lights([light_config])
        
        # Rebuild layer to trigger calculation
        self.lm._rebuild_layer()
        
        # Get the points passed to add_light_polygon
        assert self.mock_layer.add_light_polygon.called
        points = self.mock_layer.add_light_polygon.call_args[0][0]
        
        # With only uniform rays (16), we expect 17 points (center + 16)
        # With corner rays, we expect more.
        # 4 vertices * 3 rays = 12 extra rays (potentially merged with uniform ones)
        # Total should be significantly > 17.
        
        # Currently, it should fail if I assert > 17 because implementation is not there yet.
        # But I want to write the test for the DESIRED behavior.
        
        print(f"Generated points count: {len(points)}")
        assert len(points) > 17, "Should have more points than just uniform rays"
        
        # Check for specific angles/hits?
        # Vertex (50, 10) -> angle atan2(10, 50) ~= 0.197 rad
        # We expect rays at 0.197, 0.197+eps, 0.197-eps
        
        # Let's just check that we have a high enough count for now, 
        # and maybe check that the points are sorted by angle (implied by polygon structure usually, but let's trust the implementation to sort angles).
        
        # Verify determinism: run again and check exact match
        self.lm._rebuild_layer()
        points2 = self.mock_layer.add_light_polygon.call_args[0][0]
        assert points == points2
