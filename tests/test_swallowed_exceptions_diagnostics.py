from __future__ import annotations

import sys
import types

import pytest

from engine.game_runtime import tick
from engine.swallowed_exceptions import (
    format_swallowed_summary,
    get_and_reset_counts,
    read_counts,
    read_sites,
    record_swallowed,
    reset,
    should_log,
)

pytestmark = [pytest.mark.fast]


def test_record_swallowed_increments() -> None:
    reset()
    record_swallowed("test.site", RuntimeError("boom"))
    record_swallowed("test.site", RuntimeError("boom2"))
    counts = read_counts()
    assert counts.get("test.site") == 2
    sites = read_sites()
    assert sites["test.site"].count == 2
    assert sites["test.site"].first_seen_ts <= sites["test.site"].last_seen_ts
    summary = format_swallowed_summary(limit=10)
    assert "swallowed_exceptions summary:" in summary
    assert "test.site: count=2" in summary
    reset()


def test_should_log_samples_per_site(monkeypatch: pytest.MonkeyPatch) -> None:
    reset()
    now = {"value": 100.0}

    def _fake_time() -> float:
        return now["value"]

    import engine.swallowed_exceptions as mod

    monkeypatch.setattr(mod.time, "time", _fake_time)
    assert should_log("site.alpha", sample_seconds=5.0) is True
    assert should_log("site.alpha", sample_seconds=5.0) is False
    now["value"] += 5.1
    assert should_log("site.alpha", sample_seconds=5.0) is True
    reset()


def test_tick_restore_records_swallow(monkeypatch: pytest.MonkeyPatch) -> None:
    reset()
    module_name = "engine.editor.editor_sprite_ghosting"
    monkeypatch.setitem(sys.modules, module_name, types.SimpleNamespace())
    tick._restore_editor_sprite_ghosting([object()], {})
    counts = read_counts()
    assert counts.get("engine.game_runtime.tick._restore_editor_sprite_ghosting", 0) >= 1
    get_and_reset_counts()
