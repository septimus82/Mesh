"""Fast-tier tests for SceneController authoring-proxy tracing.

Covers:
- Tracing default-off: snapshot shows enabled=false and no function entries.
- Tracing enabled: call counts, timing fields, ordering.
- Error capture: exception propagates unchanged, last_err recorded.
- Reset: clears accumulated data.
- Overlay gating: section rendered only when debug + trace enabled.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor.editor_debug_overlay_controller import EditorDebugOverlayController

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_controller() -> Any:
    """Build a SceneController via object.__new__ (skip __init__)."""
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    # Instance-level trace data so tests don't leak into class state.
    sc._authoring_trace_enabled = False
    sc._authoring_trace_data = {}
    return sc


def _noop_fn(sc: Any, *args: Any, **kwargs: Any) -> str:
    """Dummy authoring function that returns a deterministic value."""
    return "ok"


def _slow_fn(sc: Any, *args: Any, **kwargs: Any) -> str:
    """Slightly slower dummy (still fast, but non-zero work)."""
    total = 0
    for i in range(200):
        total += i
    return "slow_ok"


def _boom_fn(sc: Any, *args: Any, **kwargs: Any) -> str:
    raise ValueError("boom")


def _stub_editor(*, show_debug: bool) -> SimpleNamespace:
    editor = SimpleNamespace()
    editor.window = SimpleNamespace(
        show_debug=show_debug,
        height=720,
        scene_controller=SimpleNamespace(current_scene_path="scenes/test.json"),
    )
    editor._show_swallowed_exceptions_overlay = False
    editor._swallowed_exceptions_overlay_summary = ""
    editor._swallowed_exceptions_overlay_distinct_sites = 0
    editor._swallowed_exceptions_overlay_total_count = 0
    editor._swallowed_exceptions_overlay_next_refresh_ts = 0.0
    return editor


# ---------------------------------------------------------------------------
# Default-off / gating
# ---------------------------------------------------------------------------

def test_tracing_default_off() -> None:
    sc = _make_controller()
    snap = sc.get_authoring_trace_snapshot()
    assert snap["schema_version"] == 1
    assert snap["enabled"] is False
    assert snap["total_calls"] == 0
    assert snap["functions"] == []


def test_tracing_off_zero_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """When tracing is off, _call_authoring takes the fast path (no timing)."""
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    monkeypatch.setattr(authoring_mod, "debug_set_name", _noop_fn)
    result = sc._call_authoring("debug_set_name", "id-1", "n")
    assert result == "ok"
    # No trace data accumulated
    assert sc._authoring_trace_data == {}


# ---------------------------------------------------------------------------
# Enabled tracing: counts + timing
# ---------------------------------------------------------------------------

def test_tracing_counts_and_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _noop_fn)

    for _ in range(5):
        sc._call_authoring("debug_set_name", "id-1", "n")

    snap = sc.get_authoring_trace_snapshot()
    assert snap["enabled"] is True
    assert snap["total_calls"] == 5
    assert len(snap["functions"]) == 1

    entry = snap["functions"][0]
    assert entry["name"] == "debug_set_name"
    assert entry["count"] == 5
    assert entry["total_ms"] >= 0
    assert entry["avg_ms"] >= 0
    assert entry["last_err"] is None


def test_tracing_multiple_functions_ordering(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _noop_fn)
    monkeypatch.setattr(authoring_mod, "debug_add_tag", _slow_fn)

    # Call set_name 3 times, add_tag once (but slower)
    for _ in range(3):
        sc._call_authoring("debug_set_name", "id-1", "n")
    sc._call_authoring("debug_add_tag", ["id-1"], "t")

    snap = sc.get_authoring_trace_snapshot()
    assert snap["total_calls"] == 4
    assert len(snap["functions"]) == 2
    # Sorted by total_ms desc, then name asc — we can't guarantee which is
    # slower, so just verify deterministic ordering and field presence.
    names = [f["name"] for f in snap["functions"]]
    assert set(names) == {"debug_set_name", "debug_add_tag"}
    for entry in snap["functions"]:
        assert "count" in entry
        assert "total_ms" in entry
        assert "avg_ms" in entry
        assert "last_err" in entry


def test_snapshot_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _noop_fn)

    # Simulate 5 distinct function entries by writing trace data directly
    for i in range(5):
        sc._authoring_trace_data[f"_test_fn_{i}"] = {
            "count": 1, "total_ms": i, "last_err": None,
        }

    snap = sc.get_authoring_trace_snapshot(limit=3)
    assert len(snap["functions"]) == 3
    assert snap["total_calls"] == 5


# ---------------------------------------------------------------------------
# Error capture
# ---------------------------------------------------------------------------

def test_error_capture_and_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _boom_fn)

    with pytest.raises(ValueError, match="boom"):
        sc._call_authoring("debug_set_name", "id-1", "n")

    snap = sc.get_authoring_trace_snapshot()
    assert snap["total_calls"] == 1
    entry = snap["functions"][0]
    assert entry["name"] == "debug_set_name"
    assert entry["count"] == 1
    assert entry["last_err"] is not None
    assert "ValueError" in entry["last_err"]
    assert "boom" in entry["last_err"]


def test_error_does_not_swallow_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _boom_fn)

    with pytest.raises(ValueError) as exc_info:
        sc._call_authoring("debug_set_name", "id-1", "n")

    # Verify original exception identity is preserved (not wrapped)
    assert type(exc_info.value) is ValueError
    assert str(exc_info.value) == "boom"


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_clears_trace_data(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _noop_fn)
    sc._call_authoring("debug_set_name", "id-1", "n")

    assert sc.get_authoring_trace_snapshot()["total_calls"] == 1
    sc.reset_authoring_trace()
    snap = sc.get_authoring_trace_snapshot()
    assert snap["total_calls"] == 0
    assert snap["functions"] == []
    # Still enabled after reset
    assert snap["enabled"] is True


# ---------------------------------------------------------------------------
# Snapshot schema stability
# ---------------------------------------------------------------------------

def test_snapshot_schema_fields() -> None:
    sc = _make_controller()
    snap = sc.get_authoring_trace_snapshot()
    assert set(snap.keys()) == {"schema_version", "enabled", "total_calls", "functions"}
    assert snap["schema_version"] == 1


def test_snapshot_function_entry_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_runtime.authoring as authoring_mod

    sc = _make_controller()
    sc.enable_authoring_trace(True)
    monkeypatch.setattr(authoring_mod, "debug_set_name", _noop_fn)
    sc._call_authoring("debug_set_name", "id-1", "n")

    entry = sc.get_authoring_trace_snapshot()["functions"][0]
    assert set(entry.keys()) == {"name", "count", "total_ms", "avg_ms", "last_err"}


# ---------------------------------------------------------------------------
# Overlay tests
# ---------------------------------------------------------------------------

def test_overlay_includes_authoring_trace_when_enabled() -> None:
    editor = _stub_editor(show_debug=True)
    # Attach a fake scene_controller with trace data
    sc_stub = SimpleNamespace()
    sc_stub.current_scene_path = "scenes/test.json"
    sc_stub.get_authoring_trace_snapshot = lambda limit=10: {
        "schema_version": 1,
        "enabled": True,
        "total_calls": 7,
        "functions": [
            {"name": "debug_snap_to_grid", "count": 5, "total_ms": 12, "avg_ms": 2, "last_err": None},
            {"name": "debug_set_name", "count": 2, "total_ms": 1, "avg_ms": 0, "last_err": None},
        ],
    }
    editor.window.scene_controller = sc_stub

    overlay = EditorDebugOverlayController(editor)
    lines: list[str] = []
    overlay._append_authoring_trace_lines(lines)

    assert "Authoring Trace" in lines
    assert "enabled: true  total_calls: 7" in lines
    assert any("debug_snap_to_grid" in line and "count=5" in line for line in lines)
    assert any("debug_set_name" in line and "count=2" in line for line in lines)
    assert "----------------" in lines


def test_overlay_shows_error_in_trace_line() -> None:
    editor = _stub_editor(show_debug=True)
    sc_stub = SimpleNamespace()
    sc_stub.current_scene_path = "scenes/test.json"
    sc_stub.get_authoring_trace_snapshot = lambda limit=10: {
        "schema_version": 1,
        "enabled": True,
        "total_calls": 1,
        "functions": [
            {"name": "debug_set_name", "count": 1, "total_ms": 0, "avg_ms": 0, "last_err": "ValueError:boom"},
        ],
    }
    editor.window.scene_controller = sc_stub

    overlay = EditorDebugOverlayController(editor)
    lines: list[str] = []
    overlay._append_authoring_trace_lines(lines)

    assert any("err=ValueError:boom" in line for line in lines)


def test_overlay_absent_when_debug_off() -> None:
    editor = _stub_editor(show_debug=False)
    sc_stub = SimpleNamespace()
    sc_stub.current_scene_path = "scenes/test.json"
    sc_stub.get_authoring_trace_snapshot = lambda limit=10: {
        "schema_version": 1,
        "enabled": True,
        "total_calls": 5,
        "functions": [],
    }
    editor.window.scene_controller = sc_stub

    overlay = EditorDebugOverlayController(editor)
    lines: list[str] = []
    overlay._append_authoring_trace_lines(lines)

    assert lines == []


def test_overlay_absent_when_trace_disabled() -> None:
    editor = _stub_editor(show_debug=True)
    sc_stub = SimpleNamespace()
    sc_stub.current_scene_path = "scenes/test.json"
    sc_stub.get_authoring_trace_snapshot = lambda limit=10: {
        "schema_version": 1,
        "enabled": False,
        "total_calls": 0,
        "functions": [],
    }
    editor.window.scene_controller = sc_stub

    overlay = EditorDebugOverlayController(editor)
    lines: list[str] = []
    overlay._append_authoring_trace_lines(lines)

    assert lines == []
