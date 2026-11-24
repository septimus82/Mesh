"""M4-0's latency probe (tooling/m4_latency_probe.py): its link model and its statistics, without a room or a clock."""

from __future__ import annotations

import argparse
import random

import pytest

from tooling.m4_latency_probe import RTO_MS, Link, pct, queue_of, summary

pytestmark = pytest.mark.fast


def test_the_link_is_tcp_like_and_seeded_and_quantiles_are_samples() -> None:
    def arrivals(seed: int) -> list[float]:
        link = Link(50.0, 10.0, 0.2, random.Random(seed))
        return [link.arrival(i * 50.0) for i in range(200)]

    a = arrivals(3)
    assert a == arrivals(3) and a != arrivals(4), "one seed, one run"
    assert all(x <= y for x, y in zip(a, a[1:])), "in order: a late segment holds up the ones behind it"
    assert all(x >= i * 50.0 + 40.0 for i, x in enumerate(a)), "never sooner than the delay less its jitter"
    assert max(x - i * 50.0 for i, x in enumerate(a)) >= 40.0 + 100.0 + RTO_MS, "a loss waits a retransmission: RTT + RTO"
    ideal = Link(0.0, 0.0, 0.0, random.Random(1))
    assert [ideal.arrival(t) for t in (0.0, 5.0, 9.0)] == [0.0, 5.0, 9.0]

    assert pct([5, 1, 4, 2, 3], 0.5) == 3 and pct([5, 1, 4, 2, 3], 0.95) == 5 and pct([7], 0.95) == 7
    assert summary([]) == {"n": 0}
    assert summary([10.0, 30.0, 20.0]) == {"n": 3, "p50": 20.0, "p95": 30.0, "max": 30.0}


def test_a_knob_given_beats_the_preset_as_on_the_server() -> None:
    """--depth/--hold/--drain given beat --queue's values (mesh_net.server.queue_from's order); the rest come from the
    preset, else the game's default; checked."""

    def args(queue: str | None = None, depth: int | None = None, hold: int | None = None,
             drain: int | None = None) -> argparse.Namespace:
        return argparse.Namespace(queue=queue, depth=depth, hold=hold, drain=drain)

    assert queue_of(args()) == (8, 1, 4)
    assert queue_of(args("small")) == (2, 5, 0)
    assert queue_of(args("small", depth=4)) == (4, 5, 0)
    assert queue_of(args("deep", drain=6, hold=2)) == (8, 2, 6)
    with pytest.raises(ValueError, match="depth"):
        queue_of(args("deep", depth=0))
