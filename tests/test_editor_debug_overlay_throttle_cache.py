"""Throttle / cache behaviour tests for the editor debug overlay.

Covers:
- shadow backend diagnostics called at most once within refresh window
- verify snapshot file reads throttled via mtime map + cache
- reset invalidates caches immediately
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor import overlays_modals
from engine.editor.editor_debug_overlay_controller import EditorDebugOverlayController
from engine.swallowed_exceptions import record_swallowed, reset

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_editor(*, show_debug: bool) -> SimpleNamespace:
    editor = SimpleNamespace()
    editor.window = SimpleNamespace(
        show_debug=show_debug,
        height=720,
        scene_controller=SimpleNamespace(current_scene_path="scenes/test_scene.json"),
    )
    editor._show_swallowed_exceptions_overlay = False
    editor._swallowed_exceptions_overlay_summary = "no swallowed exceptions recorded"
    editor._swallowed_exceptions_overlay_distinct_sites = 0
    editor._swallowed_exceptions_overlay_total_count = 0
    editor._swallowed_exceptions_overlay_next_refresh_ts = 0.0
    return editor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_swallowed_overlay_reset_clears_totals_and_cache_immediately() -> None:
    reset()
    record_swallowed("a.site", RuntimeError("a"))
    record_swallowed("b.site", RuntimeError("b"))

    editor = _stub_editor(show_debug=True)
    editor._show_swallowed_exceptions_overlay = True
    overlays_modals.refresh_swallowed_exceptions_overlay_summary(editor, force=True)
    assert editor._swallowed_exceptions_overlay_total_count == 2
    assert editor._swallowed_exceptions_overlay_distinct_sites == 2
    assert editor._swallowed_exceptions_overlay_next_refresh_ts > 0.0

    overlay = EditorDebugOverlayController(editor)
    pre_reset_copy = overlay.build_swallowed_exceptions_copy_text()
    assert "Swallowed Exceptions" in pre_reset_copy
    assert "total=2 distinct=2" in pre_reset_copy
    assert overlay.reset_swallowed_exceptions() is True
    assert editor._swallowed_exceptions_overlay_total_count == 0
    assert editor._swallowed_exceptions_overlay_distinct_sites == 0
    assert editor._swallowed_exceptions_overlay_summary == "no swallowed exceptions recorded"
    assert editor._swallowed_exceptions_overlay_next_refresh_ts == 0.0

    overlays_modals.refresh_swallowed_exceptions_overlay_summary(editor, force=False)
    assert editor._swallowed_exceptions_overlay_total_count == 0
    assert editor._swallowed_exceptions_overlay_distinct_sites == 0
    assert editor._swallowed_exceptions_overlay_summary == "no swallowed exceptions recorded"
    post_reset_copy = overlay.build_swallowed_exceptions_copy_text()
    assert "total=0 distinct=0" in post_reset_copy
    assert "no swallowed exceptions recorded" in post_reset_copy
    reset()


def test_debug_overlay_includes_shadow_backend_section_with_throttled_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "engine.editor.editor_debug_overlay_controller.draw_panel_bg",
        lambda *args, **kwargs: None,
    )

    calls = {"count": 0}

    def _fake_shadow_diag() -> dict[str, object]:
        calls["count"] += 1
        return {
            "schema_version": 1,
            "selected": "fbo.use",
            "reason": "fbo.use available",
            "fallbacks": ["fbo.activate", "none"],
        }

    monkeypatch.setattr(
        "engine.lighting.shadows.get_shadow_backend_diagnostics",
        _fake_shadow_diag,
    )

    # Freeze time so the second draw stays within refresh throttle window.
    monkeypatch.setattr(
        "engine.editor.editor_debug_overlay_controller.time.time",
        lambda: 100.0,
    )

    editor = _stub_editor(show_debug=True)
    editor.dirty_state = SimpleNamespace(is_dirty=False)
    editor.tool_mode = "MOVE"
    editor.shape_edit_mode = None
    editor.shape_snap_enabled = False
    editor.selected_entity = None
    editor._status_message = None
    editor._get_zone_behaviours = lambda *_args, **_kwargs: []
    editor._get_zone_behaviour = lambda *_args, **_kwargs: None
    editor.zone_behaviour_index = 0
    editor.inspector = SimpleNamespace(build_selection_overlay_lines=lambda: ["No selection"])
    editor._show_swallowed_exceptions_overlay = True
    editor._swallowed_exceptions_overlay_summary = "no swallowed exceptions recorded"
    editor._swallowed_exceptions_overlay_distinct_sites = 0
    editor._swallowed_exceptions_overlay_total_count = 0
    editor.refresh_swallowed_exceptions_overlay_summary = lambda force=False: editor._swallowed_exceptions_overlay_summary

    text_obj = SimpleNamespace(text="", y=0, draw=lambda: None)
    overlay = EditorDebugOverlayController(editor)
    overlay.draw_debug_overlay(text_obj)
    overlay.draw_debug_overlay(text_obj)

    assert calls["count"] == 1
    assert "Shadow Backend" in text_obj.text
    assert "selected: fbo.use" in text_obj.text
    assert "reason: fbo.use available" in text_obj.text
    assert "fallbacks: fbo.activate, none" in text_obj.text
    assert text_obj.text.find("Shadow Backend") < text_obj.text.find("No selection")


def test_copy_text_includes_shadow_backend_and_uses_throttle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset()
    record_swallowed("a.site", RuntimeError("a"))
    editor = _stub_editor(show_debug=True)
    editor._show_swallowed_exceptions_overlay = True
    editor.refresh_swallowed_exceptions_overlay_summary = (
        lambda force=False: overlays_modals.refresh_swallowed_exceptions_overlay_summary(
            editor,
            force=force,
        )
    )

    calls = {"count": 0}

    def _fake_shadow_diag() -> dict[str, object]:
        calls["count"] += 1
        return {
            "schema_version": 1,
            "selected": "fbo.use",
            "reason": "fbo.use available",
            "fallbacks": ["fbo.activate", "none"],
        }

    monkeypatch.setattr(
        "engine.lighting.shadows.get_shadow_backend_diagnostics",
        _fake_shadow_diag,
    )
    monkeypatch.setattr(
        "engine.editor.editor_debug_overlay_controller.time.time",
        lambda: 100.0,
    )

    overlay = EditorDebugOverlayController(editor)
    text_a = overlay.build_swallowed_exceptions_copy_text()
    text_b = overlay.build_swallowed_exceptions_copy_text()
    assert calls["count"] == 1
    assert "Shadow Backend" in text_a
    assert "selected: fbo.use" in text_a
    assert "reason: fbo.use available" in text_a
    assert "fallbacks:" in text_a
    assert "  - fbo.activate" in text_a
    assert "  - none" in text_a
    assert text_a == text_b
    reset()
