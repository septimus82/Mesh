"""Copy-text contract tests for the editor debug overlay.

Covers:
- swallowed exceptions copy text formatting
- shadow backend block presence / absence
- debug gating behaviour (toggle, reset, clipboard)
- deterministic ordering of summary lines
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor import overlays_modals
from engine.editor.editor_debug_overlay_controller import EditorDebugOverlayController
from engine.editor_controller import EditorModeController
from engine.swallowed_exceptions import (
    format_swallowed_summary,
    record_swallowed,
    reset,
)

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

def test_swallowed_overlay_toggle_is_debug_gated() -> None:
    assert hasattr(EditorModeController, "toggle_swallowed_exceptions_overlay")
    editor = _stub_editor(show_debug=False)
    assert overlays_modals.toggle_swallowed_exceptions_overlay(editor) is False
    assert editor._show_swallowed_exceptions_overlay is False

    editor.window.show_debug = True
    assert overlays_modals.toggle_swallowed_exceptions_overlay(editor) is True
    assert editor._show_swallowed_exceptions_overlay is True
    assert editor._swallowed_exceptions_overlay_next_refresh_ts > 0.0


def test_swallowed_overlay_summary_refresh_uses_deterministic_formatter() -> None:
    reset()
    record_swallowed("b.site", RuntimeError("b"))
    record_swallowed("a.site", RuntimeError("a1"))
    record_swallowed("a.site", RuntimeError("a2"))

    editor = _stub_editor(show_debug=True)
    editor._show_swallowed_exceptions_overlay = True

    summary = overlays_modals.refresh_swallowed_exceptions_overlay_summary(editor, force=True)
    assert summary == format_swallowed_summary(limit=20)
    assert editor._swallowed_exceptions_overlay_summary == summary
    assert editor._swallowed_exceptions_overlay_distinct_sites == 2
    assert editor._swallowed_exceptions_overlay_total_count == 3
    reset()


def test_editor_debug_overlay_draw_headless_with_swallowed_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "engine.editor.editor_debug_overlay_controller.draw_panel_bg",
        lambda *args, **kwargs: None,
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
    editor._swallowed_exceptions_overlay_summary = "swallowed_exceptions summary:\na.site: count=1"
    editor._swallowed_exceptions_overlay_distinct_sites = 1
    editor._swallowed_exceptions_overlay_total_count = 1
    editor.refresh_swallowed_exceptions_overlay_summary = lambda force=False: editor._swallowed_exceptions_overlay_summary

    text_obj = SimpleNamespace(text="", y=0, draw=lambda: None)
    overlay = EditorDebugOverlayController(editor)
    overlay.draw_debug_overlay(text_obj)
    assert "Swallowed Exceptions" in text_obj.text
    assert "totals: total_swallowed_count=1 distinct_sites=1" in text_obj.text
    assert "a.site: count=1" in text_obj.text


def test_swallowed_overlay_reset_is_debug_only() -> None:
    reset()
    record_swallowed("a.site", RuntimeError("a"))
    editor = _stub_editor(show_debug=False)
    overlay = EditorDebugOverlayController(editor)
    assert overlay.reset_swallowed_exceptions() is False
    # Still present globally because reset is debug-gated/no-op.
    summary = format_swallowed_summary(limit=20)
    assert "a.site: count=1" in summary
    reset()


def test_build_copy_text_deterministic_order_and_totals() -> None:
    reset()
    record_swallowed("b.site", RuntimeError("b"))
    record_swallowed("a.site", RuntimeError("a1"))
    record_swallowed("a.site", RuntimeError("a2"))
    editor = _stub_editor(show_debug=True)
    editor._show_swallowed_exceptions_overlay = True
    editor.refresh_swallowed_exceptions_overlay_summary = (
        lambda force=False: overlays_modals.refresh_swallowed_exceptions_overlay_summary(
            editor,
            force=force,
        )
    )
    overlay = EditorDebugOverlayController(editor)
    text = overlay.build_swallowed_exceptions_copy_text()
    assert "Swallowed Exceptions" in text
    assert "total=3 distinct=2" in text
    a_index = text.find("a.site: count=2")
    b_index = text.find("b.site: count=1")
    assert a_index >= 0
    assert b_index >= 0
    assert a_index < b_index
    reset()


def test_copy_swallowed_exceptions_to_clipboard_debug_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _stub_editor(show_debug=False)
    editor._show_swallowed_exceptions_overlay = True
    overlay = EditorDebugOverlayController(editor)
    assert overlay.copy_swallowed_exceptions_to_clipboard() is False

    editor.window.show_debug = True
    editor.refresh_swallowed_exceptions_overlay_summary = lambda force=False: "no swallowed exceptions recorded"

    captured: dict[str, object] = {}

    def _fake_copy(text: str, *, is_web: bool = False, is_headless: bool = False) -> bool:
        captured["text"] = text
        captured["is_web"] = is_web
        captured["is_headless"] = is_headless
        return True

    monkeypatch.setattr(
        "engine.tooling_runtime.clipboard.try_copy_to_clipboard",
        _fake_copy,
    )
    assert overlay.copy_swallowed_exceptions_to_clipboard() is True
    assert "Swallowed Exceptions" in str(captured.get("text", ""))


def test_copy_text_no_shadow_backend_when_debug_disabled() -> None:
    reset()
    record_swallowed("a.site", RuntimeError("a"))
    editor = _stub_editor(show_debug=False)
    editor._show_swallowed_exceptions_overlay = True
    editor.refresh_swallowed_exceptions_overlay_summary = (
        lambda force=False: overlays_modals.refresh_swallowed_exceptions_overlay_summary(
            editor,
            force=force,
        )
    )
    overlay = EditorDebugOverlayController(editor)
    text = overlay.build_swallowed_exceptions_copy_text()
    assert "Swallowed Exceptions" in text
    assert "Shadow Backend" not in text
    assert "Shadow Backend: (unavailable)" not in text
    reset()
