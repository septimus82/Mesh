from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_controller() -> Any:
    from engine.scene_controller import SceneController

    sc = object.__new__(SceneController)
    sc.layers = {}
    sc.window = SimpleNamespace(strict_mode=False)
    return sc


def _sprite(name: str, behaviours: list[Any]) -> Any:
    return SimpleNamespace(
        mesh_name=name,
        mesh_behaviours_runtime=behaviours,
    )


class _RecordingBehaviour:
    """Wildcard probe: records every (sprite_name, id(self), event_type) call."""

    def __init__(self, name: str) -> None:
        self.name = name

    def on_event(self, event: Any) -> None:
        _CALLS.append((self.name, id(self), event.type))


_CALLS: list[tuple[str, int, str]] = []


def _evt(t: str) -> Any:
    return SimpleNamespace(type=t)


# ---------------------------------------------------------------------------
# Test 1 — Golden multi-layer delivery ordering
#
# Probes are wildcards (subscribed_event_types returns None / not defined).
# Verifies: event-major → _layer_update_order → sprite order → behaviour order.
# ---------------------------------------------------------------------------

def test_golden_multilayer_delivery_ordering() -> None:
    """Lock: delivery is event-major → layer-order → sprite-order → behaviour-order."""
    _CALLS.clear()
    sc = _make_controller()

    # Behaviours identified by a descriptive name string.
    # Layer "background": sprite bg0 with [b0, b1], sprite bg1 with [b2]
    b0 = _RecordingBehaviour("bg0.b0")
    b1 = _RecordingBehaviour("bg0.b1")
    b2 = _RecordingBehaviour("bg1.b2")
    # Layer "entities": sprite ent0 with [b3]
    b3 = _RecordingBehaviour("ent0.b3")
    # Layer "foreground": sprite fg0 with [b4, b5]
    b4 = _RecordingBehaviour("fg0.b4")
    b5 = _RecordingBehaviour("fg0.b5")
    # Layer "overlay" (trailing, non-standard): sprite ov0 with [b6]
    b6 = _RecordingBehaviour("ov0.b6")

    sc.layers = {
        "overlay":     [_sprite("ov0", [b6])],
        "entities":    [_sprite("ent0", [b3])],
        "background":  [_sprite("bg0", [b0, b1]), _sprite("bg1", [b2])],
        "foreground":  [_sprite("fg0", [b4, b5])],
    }

    sc._deliver_events_to_behaviours([_evt("X"), _evt("Y"), _evt("Z")])

    # Derive expected sequence from _layer_update_order:
    # background → entities → foreground → overlay (insertion order for trailing)
    # Within each layer, sprite order, then behaviour order.
    layer_order = ["bg0.b0", "bg0.b1", "bg1.b2", "ent0.b3", "fg0.b4", "fg0.b5", "ov0.b6"]
    expected = [(name, id(b), et)
                for et in ("X", "Y", "Z")
                for name, b in [
                    ("bg0.b0", b0), ("bg0.b1", b1), ("bg1.b2", b2),
                    ("ent0.b3", b3), ("fg0.b4", b4), ("fg0.b5", b5),
                    ("ov0.b6", b6),
                ]]
    assert _CALLS == expected, (
        "Delivery order violated.\n"
        f"Expected event-major × [{', '.join(layer_order)}]\n"
        f"Got: {_CALLS}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Filter mechanism: frozenset() never called
# ---------------------------------------------------------------------------

def test_filter_empty_frozenset_never_called() -> None:
    """A behaviour returning frozenset() from subscribed_event_types is never called."""
    called = []

    class NeverBehaviour:
        def subscribed_event_types(self) -> frozenset[str]:
            return frozenset()

        def on_event(self, event: Any) -> None:
            called.append(event.type)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite("e", [NeverBehaviour()])]}
    sc._deliver_events_to_behaviours([_evt("foo"), _evt("bar")])
    assert called == [], f"NeverBehaviour.on_event should not be called, got {called}"


# ---------------------------------------------------------------------------
# Test 3 — Filter mechanism: declared single type gets only that type
# ---------------------------------------------------------------------------

def test_filter_single_type_receives_only_declared() -> None:
    """A behaviour declaring frozenset({'X'}) only receives event type 'X'."""
    received = []

    class SelectiveBehaviour:
        def subscribed_event_types(self) -> frozenset[str]:
            return frozenset({"X"})

        def on_event(self, event: Any) -> None:
            received.append(event.type)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite("e", [SelectiveBehaviour()])]}
    sc._deliver_events_to_behaviours([_evt("X"), _evt("Y"), _evt("X"), _evt("Z")])
    assert received == ["X", "X"], f"Expected only ['X', 'X'], got {received}"


# ---------------------------------------------------------------------------
# Test 4 — Filter mechanism: None wildcard receives all
# ---------------------------------------------------------------------------

def test_filter_none_wildcard_receives_all() -> None:
    """A behaviour returning None from subscribed_event_types receives every event."""
    received = []

    class WildcardBehaviour:
        def subscribed_event_types(self) -> None:
            return None

        def on_event(self, event: Any) -> None:
            received.append(event.type)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite("e", [WildcardBehaviour()])]}
    sc._deliver_events_to_behaviours([_evt("A"), _evt("B"), _evt("C")])
    assert received == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Test 5 — Filter mechanism: no subscribed_event_types method → wildcard
# ---------------------------------------------------------------------------

def test_filter_missing_getter_is_wildcard() -> None:
    """A behaviour with no subscribed_event_types attribute receives every event."""
    received = []

    class PlainBehaviour:
        def on_event(self, event: Any) -> None:
            received.append(event.type)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite("e", [PlainBehaviour()])]}
    sc._deliver_events_to_behaviours([_evt("P"), _evt("Q")])
    assert received == ["P", "Q"]


# ---------------------------------------------------------------------------
# Test 6 — Filter mechanism: faulty getter → treated as wildcard (never skips)
# ---------------------------------------------------------------------------

def test_filter_faulty_getter_treated_as_wildcard() -> None:
    """If subscribed_event_types raises, the behaviour is treated as wildcard."""
    received = []

    class FaultyGetterBehaviour:
        def subscribed_event_types(self) -> frozenset[str]:
            raise RuntimeError("getter exploded")

        def on_event(self, event: Any) -> None:
            received.append(event.type)

    sc = _make_controller()
    sc.layers = {"entities": [_sprite("e", [FaultyGetterBehaviour()])]}
    sc._deliver_events_to_behaviours([_evt("R"), _evt("S")])
    assert received == ["R", "S"], (
        f"Faulty getter must not suppress delivery; got {received}"
    )


# ---------------------------------------------------------------------------
# Test 7 — Interest cache: getter called at most once per behaviour per batch
# ---------------------------------------------------------------------------

def test_filter_getter_called_once_per_batch() -> None:
    """subscribed_event_types is queried at most once per behaviour per batch."""
    call_count = 0

    class CountingBehaviour:
        def subscribed_event_types(self) -> frozenset[str]:
            nonlocal call_count
            call_count += 1
            return frozenset({"ping"})

        def on_event(self, event: Any) -> None:
            pass

    sc = _make_controller()
    b = CountingBehaviour()
    sc.layers = {"entities": [_sprite("e", [b])]}
    sc._deliver_events_to_behaviours([_evt("ping"), _evt("ping"), _evt("pong"), _evt("ping")])
    assert call_count == 1, f"getter should be called once per batch, called {call_count} times"


# ---------------------------------------------------------------------------
# Test 8 — Equivalence: all-wildcard delivers identical set as old loop
# ---------------------------------------------------------------------------

def test_equivalence_all_wildcard_identical_to_broadcast() -> None:
    """With every behaviour using wildcard, delivered events match a plain broadcast."""
    delivered_filter: list[tuple[str, str]] = []
    delivered_plain: list[tuple[str, str]] = []

    class FilterBehaviour:
        def __init__(self, label: str, log: list[tuple[str, str]]) -> None:
            self.label = label
            self._log = log

        def subscribed_event_types(self) -> None:
            return None

        def on_event(self, event: Any) -> None:
            self._log.append((self.label, event.type))

    sc = _make_controller()
    sc.layers = {
        "background": [
            _sprite("s1", [FilterBehaviour("s1.b0", delivered_filter)]),
            _sprite("s2", [FilterBehaviour("s2.b0", delivered_filter)]),
        ],
        "entities": [
            _sprite("s3", [FilterBehaviour("s3.b0", delivered_filter)]),
        ],
    }
    sc._deliver_events_to_behaviours([_evt("ev1"), _evt("ev2")])

    # Plain reference: manually apply broadcast order
    for et in ("ev1", "ev2"):
        for label in ("s1.b0", "s2.b0", "s3.b0"):
            delivered_plain.append((label, et))

    assert delivered_filter == delivered_plain


# ---------------------------------------------------------------------------
# Test 9 — Equivalence: strict-mode re-raise still works with filter in place
# ---------------------------------------------------------------------------

def test_strict_mode_reraise_unaffected_by_filter() -> None:
    """strict_mode=True re-raise behaviour is unchanged after the filter rewrite."""
    sc = _make_controller()
    sc.window.strict_mode = True

    class BoomBehaviour:
        def on_event(self, event: Any) -> None:
            raise RuntimeError("kaboom")

    sc.layers = {"entities": [_sprite("e", [BoomBehaviour()])]}
    with pytest.raises(RuntimeError, match="kaboom"):
        sc._deliver_events_to_behaviours([_evt("any")])


# ---------------------------------------------------------------------------
# Test 10 — Equivalence: non-strict error delivery continues after handler error
# ---------------------------------------------------------------------------

def test_non_strict_continues_after_handler_error(capsys: pytest.CaptureFixture[str]) -> None:
    """Non-strict mode: failing behaviour doesn't block subsequent ones."""
    calls: list[tuple[str, str]] = []

    class FailingBehaviour:
        def on_event(self, event: Any) -> None:
            calls.append(("failing", event.type))
            raise RuntimeError("boom")

    class HealthyBehaviour:
        def on_event(self, event: Any) -> None:
            calls.append(("healthy", event.type))

    sc = _make_controller()
    sc.layers = {
        "entities": [
            _sprite("a", [FailingBehaviour()]),
            _sprite("b", [HealthyBehaviour()]),
        ]
    }
    sc._deliver_events_to_behaviours([_evt("ping")])

    assert calls == [("failing", "ping"), ("healthy", "ping")]
    assert "ERROR delivering 'ping'" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Test 11 — Empty events list short-circuits without touching layers
# ---------------------------------------------------------------------------

def test_empty_events_no_iteration() -> None:
    """Passing an empty list must return without touching layers at all."""
    accessed = []

    class TrackingLayer:
        def __iter__(self):
            accessed.append("iterated")
            return iter([])

    sc = _make_controller()
    sc.layers = {"entities": TrackingLayer()}
    sc._deliver_events_to_behaviours([])
    assert accessed == [], "layers should not be iterated for empty event list"
