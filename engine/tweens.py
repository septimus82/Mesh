"""Tween / property animation system for Mesh Engine.

Provides a lightweight tweening API for animating arbitrary numeric properties
over time with configurable easing functions.

Usage Example::

    from engine.tweens import TweenManager, Easing

    tweens = TweenManager()

    # Animate a sprite's alpha from 255 to 0 over 1 second with ease-out
    tweens.add(
        target=sprite,
        property="alpha",
        start=255,
        end=0,
        duration=1.0,
        easing=Easing.EASE_OUT_QUAD,
    )

    # Each frame:
    tweens.update(dt)

Architecture:
    - ``TweenManager`` owns all active tweens and ticks them each frame.
    - ``Tween`` is a single animation of one property on one target.
    - ``Easing`` provides common easing curves (linear, quad, cubic, elastic, etc.)
    - Tweens auto-remove on completion. Optional ``on_complete`` callback.
    - Supports chaining via ``then()`` for sequential animations.
"""

from __future__ import annotations

import math
import builtins
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional
from engine.swallowed_exceptions import _log_swallow


class Easing(Enum):
    """Built-in easing functions for tweens."""

    LINEAR = "linear"
    EASE_IN_QUAD = "ease_in_quad"
    EASE_OUT_QUAD = "ease_out_quad"
    EASE_IN_OUT_QUAD = "ease_in_out_quad"
    EASE_IN_CUBIC = "ease_in_cubic"
    EASE_OUT_CUBIC = "ease_out_cubic"
    EASE_IN_OUT_CUBIC = "ease_in_out_cubic"
    EASE_IN_SINE = "ease_in_sine"
    EASE_OUT_SINE = "ease_out_sine"
    EASE_IN_OUT_SINE = "ease_in_out_sine"
    EASE_IN_EXPO = "ease_in_expo"
    EASE_OUT_EXPO = "ease_out_expo"
    EASE_IN_OUT_EXPO = "ease_in_out_expo"
    EASE_IN_ELASTIC = "ease_in_elastic"
    EASE_OUT_ELASTIC = "ease_out_elastic"
    EASE_IN_BACK = "ease_in_back"
    EASE_OUT_BACK = "ease_out_back"
    EASE_OUT_BOUNCE = "ease_out_bounce"


def apply_easing(t: float, easing: Easing) -> float:
    """Apply an easing function to a normalized time value ``t`` in [0, 1].

    Args:
        t: Progress ratio from 0.0 (start) to 1.0 (end).
        easing: The easing curve to use.

    Returns:
        The eased value, typically in [0, 1] but may overshoot for elastic/back.
    """
    t = max(0.0, min(1.0, t))

    if easing == Easing.LINEAR:
        return t

    if easing == Easing.EASE_IN_QUAD:
        return t * t

    if easing == Easing.EASE_OUT_QUAD:
        return 1.0 - (1.0 - t) * (1.0 - t)

    if easing == Easing.EASE_IN_OUT_QUAD:
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0

    if easing == Easing.EASE_IN_CUBIC:
        return t * t * t

    if easing == Easing.EASE_OUT_CUBIC:
        return 1.0 - (1.0 - t) ** 3

    if easing == Easing.EASE_IN_OUT_CUBIC:
        if t < 0.5:
            return 4.0 * t * t * t
        return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0

    if easing == Easing.EASE_IN_SINE:
        return 1.0 - math.cos(t * math.pi / 2.0)

    if easing == Easing.EASE_OUT_SINE:
        return math.sin(t * math.pi / 2.0)

    if easing == Easing.EASE_IN_OUT_SINE:
        return -(math.cos(math.pi * t) - 1.0) / 2.0

    if easing == Easing.EASE_IN_EXPO:
        return 0.0 if t == 0.0 else 2.0 ** (10.0 * t - 10.0)

    if easing == Easing.EASE_OUT_EXPO:
        return 1.0 if t == 1.0 else 1.0 - 2.0 ** (-10.0 * t)

    if easing == Easing.EASE_IN_OUT_EXPO:
        if t == 0.0:
            return 0.0
        if t == 1.0:
            return 1.0
        if t < 0.5:
            return float(2.0 ** (20.0 * t - 10.0) / 2.0)
        return float((2.0 - 2.0 ** (-20.0 * t + 10.0)) / 2.0)

    if easing == Easing.EASE_IN_ELASTIC:
        if t == 0.0:
            return 0.0
        if t == 1.0:
            return 1.0
        c4 = (2.0 * math.pi) / 3.0
        return float(-(2.0 ** (10.0 * t - 10.0)) * math.sin((t * 10.0 - 10.75) * c4))

    if easing == Easing.EASE_OUT_ELASTIC:
        if t == 0.0:
            return 0.0
        if t == 1.0:
            return 1.0
        c4 = (2.0 * math.pi) / 3.0
        return float(2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0)

    if easing == Easing.EASE_IN_BACK:
        c1 = 1.70158
        c3 = c1 + 1.0
        return c3 * t * t * t - c1 * t * t

    if easing == Easing.EASE_OUT_BACK:
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2

    if easing == Easing.EASE_OUT_BOUNCE:
        if t < 1.0 / 2.75:
            return 7.5625 * t * t
        if t < 2.0 / 2.75:
            t -= 1.5 / 2.75
            return 7.5625 * t * t + 0.75
        if t < 2.5 / 2.75:
            t -= 2.25 / 2.75
            return 7.5625 * t * t + 0.9375
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375

    return t


@dataclass(slots=True)
class Tween:
    """A single property animation on a target object.

    Attributes:
        target: The object whose property is being animated.
        property: The attribute name to animate.
        start: Starting value.
        end: Ending value.
        duration: Total animation time in seconds.
        easing: Easing curve to use.
        elapsed: Time elapsed so far.
        delay: Optional delay before the tween starts.
        on_complete: Optional callback when tween finishes.
        tag: Optional string tag for bulk cancellation.
        _next: Optional chained tween to start after this one completes.
    """

    target: Any
    property: str
    start: float
    end: float
    duration: float
    easing: Easing = Easing.LINEAR
    elapsed: float = 0.0
    delay: float = 0.0
    on_complete: Optional[Callable[[], None]] = None
    tag: Optional[str] = None
    _next: Optional[Tween] = field(default=None, repr=False)

    @builtins.property
    def finished(self) -> bool:
        """Whether the tween has completed."""
        return self.elapsed >= self.duration and self.delay <= 0.0

    @builtins.property
    def progress(self) -> float:
        """Raw progress ratio 0..1."""
        if self.duration <= 0.0:
            return 1.0
        return min(1.0, max(0.0, self.elapsed / self.duration))

    @builtins.property
    def value(self) -> float:
        """Current interpolated value based on progress and easing."""
        t = apply_easing(self.progress, self.easing)
        return self.start + (self.end - self.start) * t

    def then(
        self,
        *,
        property: str | None = None,
        start: float | None = None,
        end: float,
        duration: float,
        easing: Easing = Easing.LINEAR,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> Tween:
        """Chain another tween to run after this one completes.

        Args:
            property: Property to animate (defaults to same property).
            start: Start value (defaults to this tween's end value).
            end: End value for the chained tween.
            duration: Duration in seconds.
            easing: Easing curve.
            on_complete: Callback when chained tween finishes.

        Returns:
            The newly chained Tween (for further chaining).
        """
        chained = Tween(
            target=self.target,
            property=property or self.property,
            start=start if start is not None else self.end,
            end=end,
            duration=duration,
            easing=easing,
            on_complete=on_complete,
            tag=self.tag,
        )
        # Walk to the end of the chain
        tail = self
        while tail._next is not None:
            tail = tail._next
        tail._next = chained
        return chained


class TweenManager:
    """Manages all active tweens and ticks them each frame.

    Usage::

        manager = TweenManager()

        # Add a tween
        tween = manager.add(target=sprite, property="alpha",
                            start=255, end=0, duration=0.5,
                            easing=Easing.EASE_OUT_QUAD)

        # Chain another tween
        tween.then(end=255, duration=0.5, easing=Easing.EASE_IN_QUAD)

        # Tick every frame
        manager.update(dt)

        # Cancel all tweens on a target
        manager.cancel(target=sprite)

        # Cancel by tag
        manager.cancel(tag="fade_group")
    """

    def __init__(self) -> None:
        self._tweens: list[Tween] = []

    @property
    def active_count(self) -> int:
        """Number of currently active tweens."""
        return len(self._tweens)

    def add(
        self,
        target: Any,
        property: str,
        start: float,
        end: float,
        duration: float,
        easing: Easing = Easing.LINEAR,
        *,
        delay: float = 0.0,
        on_complete: Optional[Callable[[], None]] = None,
        tag: Optional[str] = None,
    ) -> Tween:
        """Create and register a new tween.

        Args:
            target: Object whose attribute will be animated.
            property: Attribute name on target to animate.
            start: Starting numeric value.
            end: Ending numeric value.
            duration: Duration in seconds.
            easing: Easing curve to use.
            delay: Seconds to wait before starting.
            on_complete: Callback when tween finishes.
            tag: Optional string tag for bulk cancellation.

        Returns:
            The created Tween instance (for chaining).
        """
        tween = Tween(
            target=target,
            property=property,
            start=start,
            end=end,
            duration=max(0.0, float(duration)),
            easing=easing,
            delay=max(0.0, float(delay)),
            on_complete=on_complete,
            tag=tag,
        )
        self._tweens.append(tween)
        return tween

    def update(self, dt: float) -> None:
        """Advance all tweens by *dt* seconds. Completed tweens are removed.

        Args:
            dt: Delta time in seconds since last frame.
        """
        dt = max(0.0, float(dt))
        completed: list[Tween] = []

        for tween in self._tweens:
            # Handle delay
            if tween.delay > 0.0:
                tween.delay -= dt
                if tween.delay > 0.0:
                    continue
                # Remaining time after delay consumed
                dt_remaining = -tween.delay
                tween.delay = 0.0
            else:
                dt_remaining = dt

            tween.elapsed += dt_remaining

            # Apply current value to target
            try:
                setattr(tween.target, tween.property, tween.value)
            except (AttributeError, TypeError):
                # Target is gone or property doesn't exist — remove
                completed.append(tween)
                continue

            if tween.finished:
                # Ensure we set the exact end value
                try:
                    setattr(tween.target, tween.property, tween.end)
                except (AttributeError, TypeError):
                    pass
                completed.append(tween)

        for tween in completed:
            if tween in self._tweens:
                self._tweens.remove(tween)
            # Fire completion callback
            if tween.on_complete is not None:
                try:
                    tween.on_complete()
                except Exception:  # noqa: BLE001  # REASON: tween completion callbacks are optional user hooks and should not break chained tween processing
                    _log_swallow("TWEE-001", "engine/tweens.py pass-only blanket swallow")
                    pass
            # Start chained tween if present
            if tween._next is not None:
                chained = tween._next
                chained.elapsed = 0.0
                self._tweens.append(chained)

    def cancel(
        self,
        *,
        target: Any = None,
        tag: str | None = None,
        property: str | None = None,
    ) -> int:
        """Cancel active tweens matching the given criteria.

        At least one of ``target``, ``tag``, or ``property`` must be provided.
        Criteria are AND-combined when multiple are given.

        Args:
            target: Cancel tweens on this target object.
            tag: Cancel tweens with this tag.
            property: Cancel tweens animating this property name.

        Returns:
            Number of tweens cancelled.
        """
        if target is None and tag is None and property is None:
            return 0

        to_remove: list[Tween] = []
        for tween in self._tweens:
            match = True
            if target is not None and tween.target is not target:
                match = False
            if tag is not None and tween.tag != tag:
                match = False
            if property is not None and tween.property != property:
                match = False
            if match:
                to_remove.append(tween)

        for tween in to_remove:
            self._tweens.remove(tween)
        return len(to_remove)

    def cancel_all(self) -> int:
        """Cancel all active tweens.

        Returns:
            Number of tweens cancelled.
        """
        count = len(self._tweens)
        self._tweens.clear()
        return count

    def has_tweens(self, target: Any) -> bool:
        """Check if a target has any active tweens."""
        return any(t.target is target for t in self._tweens)
