"""Tests for engine.tweens module."""

from __future__ import annotations

import math

import pytest

from engine.tweens import Easing, Tween, TweenManager, apply_easing

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Easing tests
# ---------------------------------------------------------------------------


class TestEasing:
    """Verify all easing curves produce correct boundary values."""

    @pytest.mark.parametrize("easing", list(Easing))
    def test_easing_at_zero(self, easing: Easing) -> None:
        """All easing functions should return ~0 at t=0."""
        assert apply_easing(0.0, easing) == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.parametrize("easing", list(Easing))
    def test_easing_at_one(self, easing: Easing) -> None:
        """All easing functions should return ~1 at t=1."""
        assert apply_easing(1.0, easing) == pytest.approx(1.0, abs=1e-6)

    def test_linear_midpoint(self) -> None:
        assert apply_easing(0.5, Easing.LINEAR) == pytest.approx(0.5)

    def test_ease_in_quad_midpoint(self) -> None:
        assert apply_easing(0.5, Easing.EASE_IN_QUAD) == pytest.approx(0.25)

    def test_ease_out_quad_midpoint(self) -> None:
        assert apply_easing(0.5, Easing.EASE_OUT_QUAD) == pytest.approx(0.75)

    def test_clamp_below_zero(self) -> None:
        assert apply_easing(-0.5, Easing.LINEAR) == pytest.approx(0.0)

    def test_clamp_above_one(self) -> None:
        assert apply_easing(1.5, Easing.LINEAR) == pytest.approx(1.0)

    def test_ease_out_bounce_midpoints(self) -> None:
        val = apply_easing(0.5, Easing.EASE_OUT_BOUNCE)
        assert 0.0 <= val <= 1.5  # bounce can overshoot slightly

    def test_ease_in_back_overshoot(self) -> None:
        """Ease-in-back should go negative at low t."""
        val = apply_easing(0.2, Easing.EASE_IN_BACK)
        assert val < 0.0


# ---------------------------------------------------------------------------
# Tween tests
# ---------------------------------------------------------------------------


class DummyTarget:
    """A simple target object for testing."""

    def __init__(self) -> None:
        self.alpha: float = 255.0
        self.x: float = 0.0
        self.y: float = 0.0
        self.scale: float = 1.0


class TestTween:
    def test_basic_properties(self) -> None:
        target = DummyTarget()
        tw = Tween(
            target=target, property="alpha", start=0.0, end=100.0, duration=1.0
        )
        assert tw.progress == 0.0
        assert tw.value == 0.0
        assert not tw.finished

    def test_progress_at_half(self) -> None:
        tw = Tween(
            target=DummyTarget(),
            property="x",
            start=0.0,
            end=10.0,
            duration=2.0,
        )
        tw.elapsed = 1.0
        assert tw.progress == pytest.approx(0.5)
        assert tw.value == pytest.approx(5.0)

    def test_finished(self) -> None:
        tw = Tween(
            target=DummyTarget(),
            property="x",
            start=0.0,
            end=10.0,
            duration=1.0,
        )
        tw.elapsed = 1.0
        assert tw.finished

    def test_zero_duration_finished(self) -> None:
        tw = Tween(
            target=DummyTarget(),
            property="x",
            start=0.0,
            end=5.0,
            duration=0.0,
        )
        assert tw.finished
        assert tw.value == pytest.approx(5.0)

    def test_then_chaining(self) -> None:
        target = DummyTarget()
        tw = Tween(
            target=target, property="alpha", start=0.0, end=100.0, duration=1.0
        )
        chained = tw.then(end=200.0, duration=0.5)
        assert chained.start == 100.0
        assert chained.end == 200.0
        assert chained.duration == 0.5
        assert tw._next is chained

    def test_then_chaining_custom_property(self) -> None:
        target = DummyTarget()
        tw = Tween(
            target=target, property="x", start=0.0, end=50.0, duration=1.0
        )
        chained = tw.then(property="y", start=10.0, end=20.0, duration=0.5)
        assert chained.property == "y"
        assert chained.start == 10.0


# ---------------------------------------------------------------------------
# TweenManager tests
# ---------------------------------------------------------------------------


class TestTweenManager:
    def test_add_and_count(self) -> None:
        mgr = TweenManager()
        mgr.add(DummyTarget(), "x", 0.0, 10.0, duration=1.0)
        assert mgr.active_count == 1

    def test_update_applies_value(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        mgr.add(target, "alpha", 255.0, 0.0, duration=1.0)
        mgr.update(0.5)
        # Linear at 50%: 255 + (0 - 255) * 0.5 = 127.5
        assert target.alpha == pytest.approx(127.5)

    def test_tween_completes_and_removes(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        mgr.add(target, "x", 0.0, 100.0, duration=0.5)
        mgr.update(1.0)
        assert target.x == pytest.approx(100.0)
        assert mgr.active_count == 0

    def test_on_complete_callback(self) -> None:
        mgr = TweenManager()
        called = []
        mgr.add(
            DummyTarget(),
            "x",
            0.0,
            10.0,
            duration=0.1,
            on_complete=lambda: called.append(True),
        )
        mgr.update(1.0)
        assert len(called) == 1

    def test_delay(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        mgr.add(target, "x", 0.0, 100.0, duration=1.0, delay=0.5)
        mgr.update(0.3)
        assert target.x == pytest.approx(0.0)  # still delayed
        mgr.update(0.3)  # 0.6 total, 0.1 into actual tween
        assert target.x > 0.0

    def test_cancel_by_target(self) -> None:
        mgr = TweenManager()
        t1 = DummyTarget()
        t2 = DummyTarget()
        mgr.add(t1, "x", 0.0, 10.0, duration=1.0)
        mgr.add(t2, "x", 0.0, 10.0, duration=1.0)
        removed = mgr.cancel(target=t1)
        assert removed == 1
        assert mgr.active_count == 1

    def test_cancel_by_tag(self) -> None:
        mgr = TweenManager()
        mgr.add(DummyTarget(), "x", 0.0, 10.0, duration=1.0, tag="group_a")
        mgr.add(DummyTarget(), "x", 0.0, 10.0, duration=1.0, tag="group_b")
        removed = mgr.cancel(tag="group_a")
        assert removed == 1

    def test_cancel_by_property(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        mgr.add(target, "x", 0.0, 10.0, duration=1.0)
        mgr.add(target, "y", 0.0, 10.0, duration=1.0)
        removed = mgr.cancel(target=target, property="x")
        assert removed == 1
        assert mgr.active_count == 1

    def test_cancel_all(self) -> None:
        mgr = TweenManager()
        mgr.add(DummyTarget(), "x", 0.0, 10.0, duration=1.0)
        mgr.add(DummyTarget(), "y", 0.0, 10.0, duration=1.0)
        removed = mgr.cancel_all()
        assert removed == 2
        assert mgr.active_count == 0

    def test_cancel_no_criteria_returns_zero(self) -> None:
        mgr = TweenManager()
        mgr.add(DummyTarget(), "x", 0.0, 10.0, duration=1.0)
        assert mgr.cancel() == 0
        assert mgr.active_count == 1

    def test_has_tweens(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        assert not mgr.has_tweens(target)
        mgr.add(target, "x", 0.0, 10.0, duration=1.0)
        assert mgr.has_tweens(target)

    def test_chained_tween_auto_starts(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        tw = mgr.add(target, "x", 0.0, 50.0, duration=0.5)
        tw.then(end=100.0, duration=0.5)

        # Complete first tween
        mgr.update(0.6)
        assert target.x == pytest.approx(50.0)
        assert mgr.active_count == 1  # chained tween now active

        # Complete chained tween
        mgr.update(0.6)
        assert target.x == pytest.approx(100.0)
        assert mgr.active_count == 0

    def test_eased_tween(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        mgr.add(target, "x", 0.0, 100.0, duration=1.0, easing=Easing.EASE_IN_QUAD)
        mgr.update(0.5)
        # ease_in_quad at t=0.5 → 0.25 → value = 25.0
        assert target.x == pytest.approx(25.0)

    def test_multiple_tweens_same_target(self) -> None:
        mgr = TweenManager()
        target = DummyTarget()
        mgr.add(target, "x", 0.0, 100.0, duration=1.0)
        mgr.add(target, "y", 0.0, 200.0, duration=1.0)
        mgr.update(0.5)
        assert target.x == pytest.approx(50.0)
        assert target.y == pytest.approx(100.0)

    def test_broken_target_removed(self) -> None:
        """Tween whose target property cannot be set gets cleaned up."""
        mgr = TweenManager()

        class Frozen:
            __slots__ = ("x",)
            def __init__(self) -> None:
                self.x = 0.0

        target = Frozen()
        mgr.add(target, "nonexistent_prop", 0.0, 10.0, duration=1.0)
        mgr.update(0.5)
        assert mgr.active_count == 0
