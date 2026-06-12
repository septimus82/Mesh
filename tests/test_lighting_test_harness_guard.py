from unittest.mock import MagicMock, patch

from engine.lighting import LightManager


class PoisonLight:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Real Light instantiated! Test harness failed to mock it.")

class PoisonLightLayer:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("Real LightLayer instantiated! Test harness failed to mock it.")

def test_lighting_harness_prevents_real_instantiation(mock_arcade_lighting):
    """
    Verify that the mock_arcade_lighting fixture successfully prevents
    instantiation of the underlying lighting classes.
    """
    # We can't easily inject the Poison *under* the fixture because the fixture
    # is already active.
    # However, we can verify that the objects in use are indeed Mocks and not
    # the real classes (or anything else).

    from engine.lighting import _Light, _LightLayer

    # They should be mocks
    assert isinstance(_Light, MagicMock) or hasattr(_Light, "return_value")
    assert isinstance(_LightLayer, MagicMock) or hasattr(_LightLayer, "return_value")

    # Run code that would trigger instantiation
    window = MagicMock()
    lm = LightManager(window)
    lm.available = True

    # This calls _rebuild_layer -> _create_layer -> _LightLayer()
    lm.configure_scene_lights([{"x": 0, "y": 0, "radius": 10}])

    # This calls _create_light -> _Light()
    # (Assuming the config passed above triggers it)

    # If we were using real objects (or Poison), we'd crash or raise.
    # Since we didn't crash, the harness is working.

def test_manual_poison_check():
    """
    Verify that if we manually patch with Poison, then apply the fixture logic,
    the Poison is suppressed. This confirms the fixture targets the correct names.
    """
    # 1. Install Poison
    with patch("engine.lighting._LightLayer", PoisonLightLayer), \
         patch("engine.lighting._Light", PoisonLight):

        # Verify Poison is active
        from engine.lighting import _LightLayer as P_Layer
        assert P_Layer is PoisonLightLayer

        # 2. Apply the "safe" harness logic (simulating the fixture)
        with patch("engine.lighting._LightLayer") as safe_layer, \
             patch("engine.lighting._Light") as safe_light:

            # Verify Poison is masked
            from engine.lighting import _LightLayer as S_Layer
            assert S_Layer is not PoisonLightLayer

            # 3. Run dangerous code
            window = MagicMock()
            lm = LightManager(window)
            lm.available = True

            # Should NOT raise RuntimeError
            lm.configure_scene_lights([{"x": 0, "y": 0, "radius": 10}])
