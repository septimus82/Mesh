"""Per-clip battle sprite sheet overrides: parsing, validation, and view slicing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine import optional_arcade
from engine.assets import AssetManager
from engine.monster.battle_model import BattleSprite, BattleSpriteClip, BattleStats, Species
from engine.monster.battle_sprite_view import (
    BattleSpriteAnimator,
    BattleSpriteDisplay,
    _load_battle_sprite_texture_pools,
)
from engine.monster.data_load import ValidationResult, parse_species

pytestmark = pytest.mark.fast


def _write_horizontal_sheet(path: Path, *, frame_width: int, frame_count: int) -> None:
    from PIL import Image

    height = frame_width
    width = frame_width * frame_count
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for index in range(frame_count):
        left = index * frame_width
        tile = Image.new("RGBA", (frame_width, height), (30 + index * 20, 80, 120, 255))
        image.paste(tile, (left, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _species_row(*, clips: dict[str, object]) -> dict[str, object]:
    return {
        "id": "demo",
        "types": ["grass"],
        "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
        "battle_sprite": {
            "sheet": "assets/sprites/demo_main.png",
            "columns": 4,
            "rows": 1,
            "frame_width": 32,
            "frame_height": 32,
            "clips": {
                "idle": {"frames": [0, 1], "fps": 6, "loop": True},
                **clips,
            },
        },
    }


def _parse_demo_species(*, clips: dict[str, object]) -> tuple[Species | None, ValidationResult]:
    species_map, result = parse_species({"species": [_species_row(clips=clips)]})
    if not result.ok:
        return None, result
    return species_map.get("demo"), result


def test_parse_clip_without_override_matches_legacy_fields() -> None:
    species, result = _parse_demo_species(clips={})
    assert result.ok is True
    assert species is not None
    idle = species.battle_sprite.clips["idle"]  # type: ignore[union-attr]
    assert idle.frames == (0, 1)
    assert idle.fps == 6.0
    assert idle.loop is True
    assert idle.sheet is None
    assert idle.frame_width is None
    assert idle.frame_height is None
    assert idle.columns is None


def test_parse_clip_with_full_sheet_override() -> None:
    species, result = _parse_demo_species(
        clips={
            "victory": {
                "sheet": "assets/sprites/demo_victory.png",
                "frame_width": 64,
                "frame_height": 64,
                "columns": 3,
                "frames": [0, 1, 2],
                "fps": 8,
                "loop": False,
            },
        },
    )
    assert result.ok is True
    assert species is not None
    victory = species.battle_sprite.clips["victory"]  # type: ignore[union-attr]
    assert victory.sheet == "assets/sprites/demo_victory.png"
    assert victory.frame_width == 64
    assert victory.frame_height == 64
    assert victory.columns == 3
    assert victory.frames == (0, 1, 2)
    assert victory.loop is False


def test_parse_clip_with_partial_override_inherits_parent_dimensions() -> None:
    row = _species_row(
        clips={
            "victory": {
                "sheet": "assets/sprites/demo_victory.png",
                "frames": [0, 1, 2, 3, 4],
                "fps": 8,
                "loop": False,
            },
        },
    )
    row["battle_sprite"]["columns"] = 5  # type: ignore[index]
    species_map, result = parse_species({"species": [row]})
    assert result.ok is True
    species = species_map.get("demo")
    assert species is not None
    victory = species.battle_sprite.clips["victory"]  # type: ignore[union-attr]
    assert victory.sheet == "assets/sprites/demo_victory.png"
    assert victory.frame_width is None
    assert victory.frame_height is None
    assert victory.columns is None


def test_parse_rejects_empty_override_sheet() -> None:
    species, result = _parse_demo_species(
        clips={
            "victory": {
                "sheet": "   ",
                "frames": [0],
                "fps": 8,
                "loop": False,
            },
        },
    )
    assert species is None
    assert result.ok is False
    assert any("sheet must be a non-empty string" in err for err in result.errors)


def test_parse_rejects_non_positive_override_dimensions() -> None:
    species, result = _parse_demo_species(
        clips={
            "victory": {
                "sheet": "assets/sprites/demo_victory.png",
                "frame_width": 0,
                "frames": [0],
                "fps": 8,
                "loop": False,
            },
        },
    )
    assert species is None
    assert result.ok is False
    assert any("frame_width must be a positive number" in err for err in result.errors)


def test_parse_rejects_frames_outside_clip_grid() -> None:
    species, result = _parse_demo_species(
        clips={
            "victory": {
                "sheet": "assets/sprites/demo_victory.png",
                "frame_width": 64,
                "frame_height": 64,
                "columns": 3,
                "frames": [0, 1, 2, 3],
                "fps": 8,
                "loop": False,
            },
        },
    )
    assert species is None
    assert result.ok is False
    assert any("out of range for clip grid" in err for err in result.errors)


def test_non_loop_override_clip_returns_to_idle() -> None:
    main_textures = tuple(MagicMock(name=f"main_{index}") for index in range(4))
    victory_textures = tuple(MagicMock(name=f"victory_{index}") for index in range(3))
    battle_sprite = BattleSprite(
        sheet="assets/sprites/demo_main.png",
        columns=4,
        rows=1,
        frame_width=32,
        frame_height=32,
        clips={
            "idle": BattleSpriteClip(frames=(0,), fps=10.0, loop=True),
            "victory": BattleSpriteClip(
                frames=(0, 1, 2),
                fps=10.0,
                loop=False,
                sheet="assets/sprites/demo_victory.png",
                frame_width=64,
                frame_height=64,
                columns=3,
            ),
        },
    )
    pools = {
        (battle_sprite.sheet, 32, 32, 4): main_textures,
        ("assets/sprites/demo_victory.png", 64, 64, 3): victory_textures,
    }
    animator = BattleSpriteAnimator(
        textures=main_textures,
        clips=dict(battle_sprite.clips),
        battle_sprite=battle_sprite,
        texture_pools=pools,
    )
    animator.play_clip("victory")
    assert animator.current_texture() is victory_textures[0]
    animator.update(0.11)
    assert animator.active_clip_name == "victory"
    assert animator.current_texture() is victory_textures[1]
    animator.update(0.11)
    assert animator.active_clip_name == "victory"
    assert animator.current_texture() is victory_textures[2]
    animator.update(0.11)
    assert animator.active_clip_name == "idle"
    assert animator.frame_cursor == 0
    assert animator.current_texture() is main_textures[0]


@pytest.fixture
def require_arcade() -> None:
    if not optional_arcade.HAS_ARCADE:
        pytest.skip("Arcade not installed")


def test_view_slices_override_sheet_via_real_asset_manager(
    tmp_path: Path,
    require_arcade: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_path = tmp_path / "main.png"
    victory_path = tmp_path / "victory.png"
    _write_horizontal_sheet(main_path, frame_width=32, frame_count=4)
    _write_horizontal_sheet(victory_path, frame_width=64, frame_count=3)

    battle_sprite = BattleSprite(
        sheet=str(main_path),
        columns=4,
        rows=1,
        frame_width=32,
        frame_height=32,
        clips={
            "idle": BattleSpriteClip(frames=(0, 1), fps=6.0, loop=True),
            "victory": BattleSpriteClip(
                frames=(0, 1, 2),
                fps=8.0,
                loop=False,
                sheet=str(victory_path),
                frame_width=64,
                frame_height=64,
                columns=3,
            ),
        },
    )
    assets = AssetManager()
    cache = MagicMock()
    cache.get_or_build.side_effect = lambda spec: SimpleNamespace(
        frames=assets.load_sprite_sheet(spec.path, spec.frame_width, spec.frame_height, 4)
    )
    window = SimpleNamespace(assets=assets, animation_factory=SimpleNamespace(sheets=cache))

    pools = _load_battle_sprite_texture_pools(window, battle_sprite)  # type: ignore[arg-type]
    parent_key = (str(main_path), 32, 32, 4)
    victory_key = (str(victory_path), 64, 64, 3)
    assert len(pools[parent_key]) == 4
    assert len(pools[victory_key]) == 3
    assert all(tex.width == 32 and tex.height == 32 for tex in pools[parent_key])
    assert all(tex.width == 64 and tex.height == 64 for tex in pools[victory_key])

    display = BattleSpriteDisplay(window)  # type: ignore[arg-type]
    display.reload(
        Species(
            id="demo",
            base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
            types=("grass",),
            battle_sprite=battle_sprite,
        )
    )
    assert display.has_sprite
    display.play_clip("victory")
    victory_tex = display._animator.current_texture()  # type: ignore[union-attr]
    assert victory_tex is not None
    assert victory_tex.width == 64
    assert victory_tex.height == 64

    pools_again = _load_battle_sprite_texture_pools(window, battle_sprite)  # type: ignore[arg-type]
    assert pools_again[victory_key] is pools[victory_key]
