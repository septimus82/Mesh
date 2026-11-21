"""Sprite-sheet frames are sliced once per sheet and frame size, not on every room load; clearing the asset cache
(hot reload) slices again; callers get their own list."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import assets as assets_module
from engine.assets import AssetManager

pytestmark = pytest.mark.fast


def test_frames_are_sliced_once_and_cleared_with_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sheet = tmp_path / "hero.png"
    sheet.write_bytes(b"png")
    slices: list[str] = []

    def load_spritesheet(path: str) -> SimpleNamespace:
        slices.append(path)
        return SimpleNamespace(get_texture_grid=lambda size, columns, count, margin: [f"frame{i}" for i in range(count)])

    monkeypatch.setattr(assets_module.optional_arcade, "arcade", SimpleNamespace(load_spritesheet=load_spritesheet, Texture=object))
    manager = AssetManager()
    monkeypatch.setattr(manager, "_resolve_path", lambda path: str(tmp_path / path))
    monkeypatch.setattr(manager, "get_texture", lambda path: SimpleNamespace(width=128))

    walk = manager.load_sprite_sheet("hero.png", 32, 48, 4, start_frame=4)
    assert walk == ["frame4", "frame5", "frame6", "frame7"] and len(slices) == 1
    walk.clear()  # a caller's list is its own
    assert manager.load_sprite_sheet("hero.png", 32, 48, 4, start_frame=4) == ["frame4", "frame5", "frame6", "frame7"]
    assert len(slices) == 1, "the second load used the sliced frames"
    assert manager.load_sprite_sheet("hero.png", 32, 48, 1) == ["frame0"] and len(slices) == 2, "another clip slices"
    manager.clear()
    manager.load_sprite_sheet("hero.png", 32, 48, 4, start_frame=4)
    assert len(slices) == 3, "after clear (hot reload) the sheet is read again"
