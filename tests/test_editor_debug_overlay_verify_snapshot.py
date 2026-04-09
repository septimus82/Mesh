"""Verify-health-snapshot IO tests for the editor debug overlay.

Covers:
- artifacts dir setter and snapshot block in copy text
- missing / corrupt JSON → "?" fallback behaviour
- schema-v2 step-budget parsing summary
- file-read throttling via mtime map + cache
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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

def test_copy_text_includes_verify_health_snapshot_and_throttles_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reset()
    record_swallowed("a.site", RuntimeError("a"))
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "exception_budget.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "baseline_count": 10,
                "current_count": 8,
                "ok": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (artifacts_dir / "verify_step_durations.json").write_text(
        json.dumps({"schema_version": 1, "total_ms": 123, "steps": []}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifacts_dir / "verify_step_budget_check.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "ok": False,
                "tolerance_ms": 50,
                "candidates_used": [],
                "checked_steps": [],
                "offenders": [
                    {"name": "mypy-gate", "delta_ms": 77, "effective_ms": 1000},
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    editor = _stub_editor(show_debug=True)
    editor._show_swallowed_exceptions_overlay = True
    editor.refresh_swallowed_exceptions_overlay_summary = (
        lambda force=False: overlays_modals.refresh_swallowed_exceptions_overlay_summary(
            editor,
            force=force,
        )
    )
    overlay = EditorDebugOverlayController(editor)
    overlay.set_verify_artifacts_dir(artifacts_dir)

    read_counter = {"count": 0}
    original_read_text = Path.read_text

    def _counting_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name in {"exception_budget.json", "verify_step_durations.json", "verify_step_budget_check.json"}:
            read_counter["count"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(
        "engine.editor.editor_debug_overlay_controller.time.time",
        lambda: 100.0,
    )
    monkeypatch.setattr(Path, "read_text", _counting_read_text, raising=True)

    text_a = overlay.build_swallowed_exceptions_copy_text()
    text_b = overlay.build_swallowed_exceptions_copy_text()
    assert read_counter["count"] == 3
    assert text_a == text_b
    assert "Verify Health Snapshot" in text_a
    assert "exception_budget: 8/10 ok=true" in text_a
    assert "verify_total_ms: 123" in text_a
    assert "step_budget_ok: false" in text_a
    assert "worst_step: mypy-gate delta_ms=77" in text_a
    reset()


def test_copy_text_verify_health_snapshot_missing_artifacts_uses_question_marks(
    tmp_path: Path,
) -> None:
    reset()
    record_swallowed("a.site", RuntimeError("a"))
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    editor = _stub_editor(show_debug=True)
    editor._show_swallowed_exceptions_overlay = True
    editor.refresh_swallowed_exceptions_overlay_summary = (
        lambda force=False: overlays_modals.refresh_swallowed_exceptions_overlay_summary(
            editor,
            force=force,
        )
    )
    overlay = EditorDebugOverlayController(editor)
    overlay.set_verify_artifacts_dir(artifacts_dir)
    text = overlay.build_swallowed_exceptions_copy_text()

    assert "Verify Health Snapshot" in text
    assert "exception_budget: ?/? ok=?" in text
    assert "verify_total_ms: ?" in text
    assert "step_budget_ok: ?" in text
    assert "worst_step: ? delta_ms=?" in text
    reset()
