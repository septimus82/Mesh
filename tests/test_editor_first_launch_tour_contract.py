"""Contract tests for the first-launch editor tour.

Covers:
- Tour starts when tour_completed=False
- Tour does NOT start when tour_completed=True
- Step transitions 0→1→2→3→4
- advance() on final step calls complete()
- complete() sets tour_completed=True and deactivates tour
- skip() sets tour_completed=True and deactivates tour
- start() restarts tour even when tour_completed=True
- current_text returns correct locked step strings
- is_final_step is True only on step 4
- EditorTourSession dataclass has expected default values
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor.editor_first_launch_tour_controller import (
    TOUR_STEP_COUNT,
    TOUR_STEPS,
    EditorTourController,
)
from engine.editor.state import EditorTourSession

pytestmark = [pytest.mark.fast]


def _make_config(**kwargs: Any) -> SimpleNamespace:
    defaults = {"tour_completed": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_editor(**kwargs: Any) -> SimpleNamespace:
    config = kwargs.pop("config", _make_config())
    return SimpleNamespace(config=config, **kwargs)


# ---------------------------------------------------------------------------
# EditorTourSession dataclass
# ---------------------------------------------------------------------------


def test_tour_session_default_values() -> None:
    session = EditorTourSession()
    assert session.is_active is False
    assert session.current_step == 0


# ---------------------------------------------------------------------------
# maybe_start
# ---------------------------------------------------------------------------


def test_maybe_start_when_tour_not_completed_starts_tour() -> None:
    editor = _make_editor(config=_make_config(tour_completed=False))
    tour = EditorTourController(editor)
    tour.maybe_start()
    assert tour.is_active is True
    assert tour.current_step == 0


def test_maybe_start_when_tour_completed_does_not_start() -> None:
    editor = _make_editor(config=_make_config(tour_completed=True))
    tour = EditorTourController(editor)
    tour.maybe_start()
    assert tour.is_active is False


def test_maybe_start_when_no_config_does_not_crash() -> None:
    editor = SimpleNamespace()  # no config attribute
    tour = EditorTourController(editor)
    tour.maybe_start()  # must not raise
    assert tour.is_active is False


# ---------------------------------------------------------------------------
# start / restart
# ---------------------------------------------------------------------------


def test_start_sets_is_active_true_at_step_zero() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    assert tour.is_active is True
    assert tour.current_step == 0


def test_start_restarts_tour_even_when_tour_completed() -> None:
    editor = _make_editor(config=_make_config(tour_completed=True))
    tour = EditorTourController(editor)
    tour.start()
    assert tour.is_active is True
    assert tour.current_step == 0


# ---------------------------------------------------------------------------
# Step transitions
# ---------------------------------------------------------------------------


def test_advance_progresses_through_all_steps() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    for expected_step in range(1, TOUR_STEP_COUNT - 1):
        tour.advance()
        assert tour.current_step == expected_step
        assert tour.is_active is True


def test_advance_on_final_step_completes_tour() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    for _ in range(TOUR_STEP_COUNT - 1):
        tour.advance()
    # Now on last step; one more advance should complete
    tour.advance()
    assert tour.is_active is False
    assert editor.config.tour_completed is True


def test_advance_does_nothing_when_tour_inactive() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.advance()  # tour not started — must not raise
    assert tour.is_active is False
    assert tour.current_step == 0


# ---------------------------------------------------------------------------
# complete / skip
# ---------------------------------------------------------------------------


def test_complete_deactivates_tour_and_persists() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    tour.complete()
    assert tour.is_active is False
    assert editor.config.tour_completed is True


def test_skip_deactivates_tour_and_persists() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    tour.skip()
    assert tour.is_active is False
    assert editor.config.tour_completed is True


# ---------------------------------------------------------------------------
# current_text and is_final_step
# ---------------------------------------------------------------------------


def test_current_text_matches_locked_step_strings() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    for i in range(TOUR_STEP_COUNT):
        tour.current_step = i
        assert tour.current_text == TOUR_STEPS[i]


def test_is_final_step_true_only_on_last_step() -> None:
    editor = _make_editor()
    tour = EditorTourController(editor)
    tour.start()
    for i in range(TOUR_STEP_COUNT - 1):
        tour.current_step = i
        assert tour.is_final_step is False
    tour.current_step = TOUR_STEP_COUNT - 1
    assert tour.is_final_step is True


# ---------------------------------------------------------------------------
# Locked step count
# ---------------------------------------------------------------------------


def test_tour_has_exactly_five_steps() -> None:
    assert TOUR_STEP_COUNT == 5
    assert len(TOUR_STEPS) == 5
