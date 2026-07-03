from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine import resize_diagnostics

pytestmark = pytest.mark.fast


def test_resize_diagnostics_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_RESIZE_DIAG", raising=False)
    assert resize_diagnostics.enabled() is False


def test_resize_diagnostics_enabled_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_RESIZE_DIAG", "1")
    assert resize_diagnostics.enabled() is True


def test_note_window_resize_starts_post_resize_frame_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESH_RESIZE_DIAG", "1")
    window = SimpleNamespace(width=1280, height=720)
    window.get_size = lambda: (1280, 720)

    resize_diagnostics.note_window_resize(window, 1600, 900)

    assert window._resize_diag_frames_left == resize_diagnostics._POST_RESIZE_FRAME_BUDGET
    assert window._resize_diag_last_event == (1600, 900)
    assert window._resize_diag_seq == 1


def test_maybe_log_draw_frame_sizes_consumes_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_RESIZE_DIAG", "1")
    window = SimpleNamespace(width=1600, height=900, _resize_diag_frames_left=2, _resize_diag_seq=1)
    window.get_size = lambda: (1600, 900)
    camera = SimpleNamespace(gui_camera=SimpleNamespace(viewport=SimpleNamespace(width=1600, height=900)))

    resize_diagnostics.maybe_log_draw_frame_sizes(window, camera, site="test")
    assert window._resize_diag_frames_left == 1

    resize_diagnostics.maybe_log_draw_frame_sizes(window, camera, site="test")
    assert window._resize_diag_frames_left == 0

    resize_diagnostics.maybe_log_draw_frame_sizes(window, camera, site="test")
    assert window._resize_diag_frames_left == 0


def test_log_gui_camera_sync_only_during_post_resize_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESH_RESIZE_DIAG", "1")
    window = SimpleNamespace(width=1280, height=720, _resize_diag_frames_left=0)
    window.get_size = lambda: (1280, 720)
    controller = SimpleNamespace(
        window=window,
        gui_camera=SimpleNamespace(viewport=SimpleNamespace(width=800, height=600)),
    )

    resize_diagnostics.log_gui_camera_sync(
        controller,
        synced=True,
        pre_viewport=(800, 600),
        post_viewport=(1280, 720),
    )

    window._resize_diag_frames_left = 3
    window._resize_diag_seq = 2
    window._resize_diag_last_event = (1280, 720)

    resize_diagnostics.log_gui_camera_sync(
        controller,
        synced=True,
        pre_viewport=(800, 600),
        post_viewport=(1280, 720),
    )


def test_visual_enabled_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_RESIZE_DPI_VIS", "1")
    assert resize_diagnostics.visual_enabled() is True


def test_log_viewport_pipeline_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_RESIZE_DIAG", raising=False)
    window = SimpleNamespace(width=1280, height=720, ctx=SimpleNamespace(viewport=(0, 0, 1280, 720)))
    resize_diagnostics.log_viewport_pipeline(window, site="test")


def test_log_viewport_pipeline_logs_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESH_RESIZE_DIAG", "1")
    window = SimpleNamespace(
        width=1610,
        height=808,
        ctx=SimpleNamespace(viewport=(0, 0, 1610, 808)),
        viewport=(0, 0, 1610, 808),
        _resize_diag_seq=29,
    )
    window.get_size = lambda: (1610, 808)
    window.get_framebuffer_size = lambda: (2013, 1011)
    window.scale = 1.25
    resize_diagnostics.log_viewport_pipeline(window, site="test_site")
    # Logging goes to configured logger; call should not raise.


def test_sync_gui_camera_to_window_unchanged_when_diag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MESH_RESIZE_DIAG", raising=False)
    from engine.camera_controller import CameraController

    window = SimpleNamespace(width=1280, height=720)
    gui_camera = MagicMock()
    gui_camera.viewport = SimpleNamespace(width=1280, height=720)
    controller = CameraController.__new__(CameraController)
    controller.window = window
    controller.gui_camera = gui_camera
    controller.camera = MagicMock()
    controller.resize = MagicMock()

    controller.sync_gui_camera_to_window()

    controller.resize.assert_not_called()
