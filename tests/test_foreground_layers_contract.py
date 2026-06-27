from __future__ import annotations

import pytest

from engine.background_layers import (
    BackgroundLayer,
    parse_background_layers,
    parse_foreground_layers,
)
from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours


def _layer(idx: int) -> dict:
    return {
        "id": f"fg{idx}",
        "path": f"assets/fg{idx}.png",
        "z": idx,
        "parallax": 1.0,
        "repeat_x": True,
        "repeat_y": True,
    }


def test_parse_foreground_layers_absent_returns_empty() -> None:
    assert parse_foreground_layers({}) == []
    assert parse_foreground_layers({"foreground_layers": None}) == []


def test_parse_foreground_layers_reads_foreground_key_only() -> None:
    payload = {
        "background_layers": [_layer(0)],
        "foreground_layers": [_layer(1), _layer(2)],
    }
    fg = parse_foreground_layers(payload)
    assert [layer.id for layer in fg] == ["fg1", "fg2"]
    # It must not pick up background_layers entries.
    assert all(layer.id != "fg0" for layer in fg)


def test_parse_foreground_layers_matches_background_parsing_shape() -> None:
    entries = [_layer(3), _layer(1), _layer(2)]
    fg = parse_foreground_layers({"foreground_layers": entries})
    bg = parse_background_layers({"background_layers": entries})
    assert fg == bg
    assert all(isinstance(layer, BackgroundLayer) for layer in fg)
    # Same z/id sort contract as background layers.
    assert [layer.id for layer in fg] == ["fg1", "fg2", "fg3"]


def test_scene_loader_allows_foreground_layers_without_unknown_key_warning() -> None:
    loader = SceneLoader()
    scene = {
        "name": "Foreground Scene",
        "entities": [],
        "background_layers": [_layer(0)],
        "foreground_layers": [_layer(1)],
    }
    report = loader.validate_scene(scene, validate_entities=False)
    assert report.ok is True
    assert not any("Unknown top-level key" in warning for warning in report.warnings)
