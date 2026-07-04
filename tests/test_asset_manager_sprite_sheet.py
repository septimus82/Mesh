"""AssetManager sprite sheet loading against the installed Arcade API."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import optional_arcade
from engine.assets import AssetManager

pytestmark = pytest.mark.fast


def _write_test_sheet(path: Path, *, frame_width: int = 64, frame_count: int = 6) -> None:
    from PIL import Image

    height = frame_width
    width = frame_width * frame_count
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for index in range(frame_count):
        left = index * frame_width
        tile = Image.new("RGBA", (frame_width, height), (40 + index * 30, 90, 140, 255))
        image.paste(tile, (left, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


@pytest.fixture
def require_arcade() -> None:
    if not optional_arcade.HAS_ARCADE:
        pytest.skip("Arcade not installed")


def test_load_sprite_sheet_slices_real_sheet_384x64(tmp_path: Path, require_arcade: None) -> None:
    sheet_path = tmp_path / "walk_sheet.png"
    _write_test_sheet(sheet_path, frame_width=64, frame_count=6)

    textures = AssetManager().load_sprite_sheet(str(sheet_path), 64, 64, 6, 0)

    assert len(textures) == 6
    assert all(tex.width == 64 and tex.height == 64 for tex in textures)


def test_load_sprite_sheet_honors_start_frame(tmp_path: Path, require_arcade: None) -> None:
    sheet_path = tmp_path / "walk_sheet.png"
    _write_test_sheet(sheet_path, frame_width=64, frame_count=6)

    textures = AssetManager().load_sprite_sheet(str(sheet_path), 64, 64, 2, 4)

    assert len(textures) == 2


def test_load_sprite_sheet_missing_file_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.png"
    assert AssetManager().load_sprite_sheet(str(missing), 64, 64, 6) == []


def test_placeholder_fallback_without_project_file(tmp_path: Path, require_arcade: None) -> None:
    manager = AssetManager()
    missing = tmp_path / "no_such_texture.png"

    texture = manager.get_texture(str(missing))

    assert texture is not None
    assert texture.width > 0
    assert texture.height > 0

    # Cached placeholder should be reused (single generated fallback).
    again = manager.get_texture(str(tmp_path / "another_missing.png"))
    assert again is texture
