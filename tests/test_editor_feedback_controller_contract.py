from __future__ import annotations

import pytest

from engine.editor.editor_feedback_controller import EditorFeedbackController
from engine.editor.editor_feedback_model import FeedbackSeverity


pytestmark = [pytest.mark.fast]


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


def _make_controller(clock: _Clock | None = None) -> tuple[EditorFeedbackController, _Clock]:
    fake_clock = clock or _Clock()
    return EditorFeedbackController(object(), clock=fake_clock), fake_clock


def test_info_enqueues_default_ttl() -> None:
    controller, clock = _make_controller()

    controller.info("Saved")

    pending = controller.pending()
    assert len(pending) == 1
    assert pending[0].severity is FeedbackSeverity.INFO
    assert pending[0].message == "Saved"
    assert pending[0].expires_at == pytest.approx(clock.value + 4.0)


def test_warning_and_error_use_expected_severities() -> None:
    controller, _clock = _make_controller()

    controller.warning("Careful")
    controller.error("Broken")

    pending = controller.pending()
    assert [entry.severity for entry in pending] == [FeedbackSeverity.WARNING, FeedbackSeverity.ERROR]


def test_error_sticky_has_no_expiry() -> None:
    controller, _clock = _make_controller()

    controller.error("Broken", sticky=True)

    pending = controller.pending()
    assert pending[0].sticky is True
    assert pending[0].expires_at is None


def test_toast_accepts_explicit_severity() -> None:
    controller, clock = _make_controller()

    controller.toast("Warn", FeedbackSeverity.WARNING, ttl=2.5)

    pending = controller.pending()
    assert pending[0].severity is FeedbackSeverity.WARNING
    assert pending[0].expires_at == pytest.approx(clock.value + 2.5)


def test_pending_excludes_expired_entries() -> None:
    controller, clock = _make_controller()

    controller.info("Soon gone", ttl=0.5)
    clock.value += 0.6

    assert controller.pending() == tuple()


def test_sticky_entries_do_not_expire() -> None:
    controller, clock = _make_controller()

    controller.error("Sticky", sticky=True)
    clock.value += 99.0

    pending = controller.pending()
    assert len(pending) == 1
    assert pending[0].message == "Sticky"


def test_overflow_evicts_oldest_non_sticky() -> None:
    controller, clock = _make_controller()
    for index in range(8):
        controller.info(f"msg-{index}", ttl=60.0)
        clock.value += 1.1

    controller.info("msg-8", ttl=60.0)

    pending = controller.pending()
    assert len(pending) == 8
    assert [entry.message for entry in pending] == [f"msg-{index}" for index in range(1, 9)]


def test_all_sticky_overflow_evicts_oldest_overall() -> None:
    controller, clock = _make_controller()
    for index in range(8):
        controller.error(f"sticky-{index}", sticky=True)
        clock.value += 1.1

    controller.error("sticky-8", sticky=True)

    pending = controller.pending()
    assert len(pending) == 8
    assert [entry.message for entry in pending] == [f"sticky-{index}" for index in range(1, 9)]


def test_duplicate_collapse_refreshes_entry_and_count() -> None:
    controller, clock = _make_controller()

    controller.info("Repeat")
    first = controller.pending()[0]
    clock.value += 0.5
    controller.info("Repeat")

    pending = controller.pending()
    assert len(pending) == 1
    assert pending[0].id == first.id
    assert pending[0].count == 2
    assert pending[0].created_at == pytest.approx(clock.value)
    assert pending[0].expires_at == pytest.approx(clock.value + 4.0)


def test_duplicate_collapse_boundary_creates_new_entry() -> None:
    controller, clock = _make_controller()

    controller.info("Repeat")
    clock.value += 1.01
    controller.info("Repeat")

    pending = controller.pending()
    assert len(pending) == 2
    assert [entry.count for entry in pending] == [1, 1]


def test_clear_empties_queue() -> None:
    controller, _clock = _make_controller()
    controller.info("A")
    controller.clear()
    assert controller.pending() == tuple()


def test_dismiss_removes_target_entry() -> None:
    controller, _clock = _make_controller()
    controller.info("A")
    controller.info("B")
    target = controller.pending()[0].id

    assert controller.dismiss(target) is True
    assert [entry.message for entry in controller.pending()] == ["B"]
    assert controller.dismiss("missing") is False


def test_tick_removes_expired_entries() -> None:
    controller, clock = _make_controller()
    controller.info("A", ttl=0.2)
    controller.info("B", ttl=1.0)

    clock.value += 0.25
    controller.tick(clock.value)

    assert [entry.message for entry in controller.pending()] == ["B"]