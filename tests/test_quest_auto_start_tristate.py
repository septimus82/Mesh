"""SL-3: explicit ``auto_start: false`` waits for a trigger / explicit start; absent keeps the legacy implicit start."""

from __future__ import annotations

from typing import Any

import pytest

from engine.events import MeshEvent
from engine.save_runtime import payloads as save_payloads
from tests.test_quest_stage_progress_roundtrip import _Window

pytestmark = pytest.mark.fast

_STAGES = [{"id": "s1", "title": "One", "text": "x"}, {"id": "s2", "title": "Two", "text": "y"}]
_TRIGGERED = [{"id": "s1", "title": "One", "text": "x", "start_on_event": {"type": "go"}}, _STAGES[1]]


def _window(stages: list[dict[str, Any]], **extra: Any) -> _Window:
    window = _Window()
    qm = window.quest_manager
    quest = qm._normalize_quest({"id": "q", "title": "Q", "stages": stages, **extra})
    assert quest is not None
    qm._definitions = {"q": quest}
    qm._rebuild_stage_lookup()
    qm.reload_from_state()
    return window


@pytest.mark.parametrize("extra,active", [({"auto_start": True}, True), ({}, True), ({"auto_start": False}, False)])
def test_start_at_load(extra: dict[str, Any], active: bool) -> None:
    assert _window(_STAGES, **extra).quest_manager.is_quest_active("q") is active


def test_explicit_false_starts_on_its_trigger() -> None:
    window = _window(_TRIGGERED, auto_start=False)
    assert not window.quest_manager.is_quest_active("q")
    window.quest_manager.handle_event(MeshEvent("go", {}))
    assert window.quest_manager.is_quest_active("q")


def test_explicit_false_starts_on_explicit_start_then_follows_stages() -> None:
    window = _window(_STAGES, auto_start=False)
    qm = window.quest_manager
    assert qm.start_quest("q") is True
    assert qm.is_quest_active("q")
    assert qm.complete_stage("q") is True
    snap = qm.get_state_snapshot("q")
    assert snap is not None and snap["current_stage"] == "s2"  # later stages still follow their predecessor


def test_explicit_false_inactive_survives_save_load() -> None:
    window = _window(_STAGES, auto_start=False)
    snapshot, _ = save_payloads.build_slot_payload(window, "s", compact=False, timestamp="2026-06-25T00:00:00Z")
    fresh = _window(_STAGES, auto_start=False)
    assert save_payloads.apply_loaded_payload(fresh, snapshot, mode="slot") is True
    assert not fresh.quest_manager.is_quest_active("q")
    state = fresh.quest_manager.get_state_snapshot("q")
    assert state is not None and state["status"] == "inactive"
