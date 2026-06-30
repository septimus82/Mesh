from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.scene_loader import SceneLoader

pytestmark = [pytest.mark.fast]


def _hub_sproutling() -> dict:
    scene = json.loads(Path("scenes/showcase_hub.json").read_text(encoding="utf-8"))
    sproutling = next(entity for entity in scene["entities"] if entity.get("id") == "hub_sproutling")
    assert isinstance(sproutling, dict)
    return sproutling


def test_showcase_hub_sproutling_sprite_asset_exists() -> None:
    sproutling = _hub_sproutling()
    sprite_path = Path(str(sproutling["sprite"]))
    assert sprite_path.is_file()
    assert sprite_path.name == "sproutling.png"


def test_showcase_hub_sproutling_has_sprite_sheet_and_idle_animation() -> None:
    sproutling = _hub_sproutling()
    sprite_sheet = sproutling.get("sprite_sheet")
    animations = sproutling.get("animations")

    assert isinstance(sprite_sheet, dict)
    assert sprite_sheet == {
        "columns": 7,
        "rows": 1,
        "frame_width": 107,
        "frame_height": 109,
    }
    assert sproutling.get("animation_state") == "idle"
    assert isinstance(animations, dict)
    idle = animations["idle"]
    assert idle["fps"] == 6
    assert idle["frames"] == [0, 1, 2, 3, 4, 5, 6]
    assert idle["loop"] is True


def test_showcase_hub_sproutling_does_not_require_animator_behaviour() -> None:
    sproutling = _hub_sproutling()
    behaviours = sproutling.get("behaviours", [])
    assert "Animator" not in behaviours


def test_showcase_hub_sproutling_animations_fit_sprite_sheet() -> None:
    sproutling = _hub_sproutling()
    sprite_sheet = sproutling["sprite_sheet"]
    animations = sproutling["animations"]
    frame_count = int(sprite_sheet["columns"]) * int(sprite_sheet["rows"])
    frame_indexes = [int(frame) for clip in animations.values() for frame in clip["frames"]]

    assert frame_indexes
    assert max(frame_indexes) < frame_count


def test_showcase_hub_scene_validates_with_sproutling() -> None:
    report = SceneLoader().validate_scene_file("scenes/showcase_hub.json")
    assert report.ok, report.errors


def test_sproutling_idle_animation_factory_cycles_frames() -> None:
    from PIL import Image

    import engine.optional_arcade as optional_arcade
    from engine.animation import AnimationFactory
    from tests._typing import as_any

    sheet = Image.open("assets/sprites/sproutling.png")
    base_texture = optional_arcade.arcade.Texture(name="sproutling", image=sheet)

    class _Assets:
        def get_texture(self, path: str) -> object | None:
            if path == "assets/sprites/sproutling.png":
                return base_texture
            return None

    factory = AnimationFactory(as_any(_Assets()))
    sprite = optional_arcade.arcade.Sprite()
    player = factory.build_for_entity(sprite, _hub_sproutling(), debug=False)
    assert player is not None

    seen: set[int] = set()
    clip = player.clips[player.current_state]
    for _ in range(14):
        seen.add(clip.frames[player.frame_cursor])
        player.update(1.0 / 6.0)

    assert seen == {0, 1, 2, 3, 4, 5, 6}
