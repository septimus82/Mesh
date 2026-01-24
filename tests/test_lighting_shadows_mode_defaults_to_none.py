from __future__ import annotations

from unittest.mock import MagicMock

from engine.lighting import LightManager


def test_lighting_shadows_mode_defaults_to_none() -> None:
    lm = LightManager(MagicMock(), enabled=False)
    assert lm.shadows_mode == "none"

