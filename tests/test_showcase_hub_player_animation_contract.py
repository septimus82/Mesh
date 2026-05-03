from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _hub_player() -> dict:
    scene = json.loads(Path("scenes/showcase_hub.json").read_text(encoding="utf-8"))
    player = next(entity for entity in scene["entities"] if entity.get("id") == "hub_player")
    assert isinstance(player, dict)
    return player


def test_showcase_hub_player_has_sprite_sheet() -> None:
    sprite_sheet = _hub_player().get("sprite_sheet")
    assert isinstance(sprite_sheet, dict)
    assert sprite_sheet
    for key in ("columns", "frame_width", "frame_height", "rows"):
        value = sprite_sheet.get(key)
        assert isinstance(value, int)
        assert value > 0


def test_showcase_hub_player_has_animations() -> None:
    animations = _hub_player().get("animations")
    assert isinstance(animations, dict)
    assert {"idle", "walk"}.issubset(animations)
    for clip_name in ("idle", "walk"):
        clip = animations[clip_name]
        assert clip["fps"] > 0
        assert isinstance(clip["frames"], list) and clip["frames"]
        assert isinstance(clip["loop"], bool)


def test_showcase_hub_player_animations_match_sprite_sheet() -> None:
    player = _hub_player()
    sprite_sheet = player.get("sprite_sheet")
    animations = player.get("animations")
    assert isinstance(sprite_sheet, dict)
    assert isinstance(animations, dict)

    frame_count = int(sprite_sheet["columns"]) * int(sprite_sheet["rows"])
    frame_indexes = [int(frame) for clip in animations.values() for frame in clip["frames"]]

    assert frame_indexes
    assert max(frame_indexes) < frame_count
