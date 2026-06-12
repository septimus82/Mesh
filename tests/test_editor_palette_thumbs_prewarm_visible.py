from __future__ import annotations

from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine import editor_palette_thumbs
from engine.editor_controller import EditorModeController


def _write_tiny_png(path: Path, *, rgba: tuple[int, int, int, int]) -> None:
    try:
        image_module = import_module("PIL.Image")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for thumbnail tests") from exc

    Image = image_module
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (2, 2), rgba)
    img.save(path, format="PNG")


class MockWindow:
    def __init__(self, *, width: int = 800, height: int = 300):
        self.width = width
        self.height = height
        self.paused = False
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(0, 0))


def test_prewarm_visible_thumbs_only_and_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    editor_palette_thumbs._reset_thumb_generation_state_for_tests()

    # Ensure thumb cache writes go into tmp_path, not the repo.
    monkeypatch.setattr(editor_palette_thumbs, "get_repo_root", lambda *args, **kwargs: tmp_path)

    # Build 10 prefabs with real sprite paths.
    prefabs = []
    sprite_paths: list[Path] = []
    for i in range(10):
        sprite = tmp_path / "sprites" / f"p{i}.png"
        _write_tiny_png(sprite, rgba=(i * 20, 0, 0, 255))
        sprite_paths.append(sprite)
        name = f"Thing {i}"
        # Only 3 will match the filter term "match": indices 2, 5, 7
        if i in (2, 5, 7):
            name = f"Match {i}"
        prefabs.append({"id": f"prefab_{i}", "display_name": name, "entity": {"sprite": str(sprite)}})

    window = MockWindow(width=800, height=400)

    # Patch palette loading to avoid touching real content.
    monkeypatch.setattr("engine.editor_controller.load_prefab_palette", lambda *args, **kwargs: list(prefabs))
    monkeypatch.setattr("engine.editor_controller.get_prefab_palette", lambda: list(prefabs))

    controller = EditorModeController(window)
    controller.active = True
    controller.palette_active = True

    controller.palette_filter = "match"
    controller._refresh_palette_list()

    # Prewarm should enqueue only the filtered (visible) items in order.
    controller._prewarm_visible_palette_thumbs()

    queued = editor_palette_thumbs._peek_thumb_queue_for_tests()
    expected = [str(sprite_paths[i]) for i in (2, 5, 7)]
    assert queued == expected
