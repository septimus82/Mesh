"""The editor keeps scene content on the visible canvas (CREATOR-FIRST-STEPS PR A).

CameraFollow is paused in the editor, so without framing a small scene near the
world origin opened via `mesh edit` drew under the left dock / Creator panels.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode.creator_overlay_renderer import creator_canvas_rect
from engine.editor.editor_camera_framing import editor_viewport_rect, frame_content_if_offscreen
from engine.editor.editor_shell_layout import Rect
from tests._headless_editor import headless_editor

pytestmark = [pytest.mark.fast]


def _screen(window, x: float, y: float) -> tuple[float, float]:
    cam_x, cam_y = window.camera.position
    zoom = window.camera.zoom
    return ((x - cam_x) * zoom + window.width / 2.0, (y - cam_y) * zoom + window.height / 2.0)


@pytest.fixture
def edited_starter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with headless_editor(tmp_path, monkeypatch) as window:
        yield window


def test_mesh_edit_starter_scene_entities_are_on_the_editor_canvas(edited_starter) -> None:
    window = edited_starter
    viewport = editor_viewport_rect(window.editor_controller)
    sprites = list(window.scene_controller.all_sprites)
    assert len(sprites) == 2
    for sprite in sprites:
        assert viewport.contains_point(*_screen(window, sprite.center_x, sprite.center_y)), sprite


def test_creator_mode_frames_onto_its_own_canvas(edited_starter) -> None:
    window = edited_starter
    window.camera.position = (5000.0, 5000.0)  # nothing visible anywhere
    window.editor_controller.creator_mode.toggle()
    canvas = creator_canvas_rect(window.width, window.height)
    for sprite in window.scene_controller.all_sprites:
        assert canvas.contains_point(*_screen(window, sprite.center_x, sprite.center_y)), sprite


def test_visible_content_is_never_reframed() -> None:
    # A restored workspace view or play-mode follow position already shows something.
    camera = SimpleNamespace(position=(1000.0, 1000.0), zoom=1.0)
    sprites = [SimpleNamespace(center_x=1000.0, center_y=1000.0), SimpleNamespace(center_x=9000.0, center_y=9000.0)]
    window = SimpleNamespace(width=1280, height=720, camera=camera, scene_controller=SimpleNamespace(all_sprites=sprites))
    assert frame_content_if_offscreen(window, Rect(left=320, right=960, bottom=28, top=672)) is False
    assert camera.position == (1000.0, 1000.0)
