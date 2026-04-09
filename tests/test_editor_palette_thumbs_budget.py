from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from engine import editor_palette_thumbs


def _write_tiny_png(path: Path, *, rgba: tuple[int, int, int, int]) -> None:
    """Write a valid tiny PNG using Pillow (Mesh already uses PIL for thumbs)."""
    try:
        image_module = import_module("PIL.Image")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for thumbnail tests") from exc

    Image = image_module
    img = Image.new("RGBA", (2, 2), rgba)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def test_budgeted_thumb_generation(tmp_path: Path) -> None:
    editor_palette_thumbs._reset_thumb_generation_state_for_tests()

    sprites_dir = tmp_path / "sprites"
    pngs = []
    for i in range(5):
        p = sprites_dir / f"s{i}.png"
        _write_tiny_png(p, rgba=(i * 20, 0, 0, 255))
        pngs.append(p)

    # Request thumbs for all 5 (should enqueue, none ready yet).
    for p in pngs:
        assert editor_palette_thumbs.request_thumb(str(p), repo_root=tmp_path, thumb_size=16) is None

    # Queue dedup: requesting again should not increase work.
    assert editor_palette_thumbs.request_thumb(str(pngs[0]), repo_root=tmp_path, thumb_size=16) is None
    assert editor_palette_thumbs.request_thumb(str(pngs[1]), repo_root=tmp_path, thumb_size=16) is None

    # Tick with max_per_frame=2 should only generate 2.
    processed = editor_palette_thumbs.tick_thumb_generation(max_per_frame=2)
    assert processed == 2

    ready = [editor_palette_thumbs.request_thumb(str(p), repo_root=tmp_path, thumb_size=16) for p in pngs]
    assert sum(1 for r in ready if r is not None) == 2

    processed = editor_palette_thumbs.tick_thumb_generation(max_per_frame=2)
    assert processed == 2
    ready = [editor_palette_thumbs.request_thumb(str(p), repo_root=tmp_path, thumb_size=16) for p in pngs]
    assert sum(1 for r in ready if r is not None) == 4

    processed = editor_palette_thumbs.tick_thumb_generation(max_per_frame=2)
    assert processed == 1
    ready = [editor_palette_thumbs.request_thumb(str(p), repo_root=tmp_path, thumb_size=16) for p in pngs]
    assert sum(1 for r in ready if r is not None) == 5

    # Queue should be empty (dedup prevents endless re-adding).
    assert editor_palette_thumbs.tick_thumb_generation(max_per_frame=10) == 0
