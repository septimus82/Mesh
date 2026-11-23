"""M4-0's latency probe (tooling/m4_latency_probe.py): its link model and its statistics, without a room or a clock."""

from __future__ import annotations

import random

import pytest

from tooling.m4_latency_probe import RTO_MS, Link, pct, summary

pytestmark = pytest.mark.fast


def test_the_link_is_tcp_like_and_seeded_and_quantiles_are_samples() -> None:
    def arrivals(seed: int) -> list[float]:
        link = Link(50.0, 10.0, 0.2, random.Random(seed))
        return [link.arrival(i * 50.0) for i in range(200)]

    a = arrivals(3)
    assert a == arrivals(3) and a != arrivals(4), "one seed, one run"
    assert all(x <= y for x, y in zip(a, a[1:])), "in order: a late segment holds up the ones behind it"
    assert all(x >= i * 50.0 + 40.0 for i, x in enumerate(a)), "never sooner than the delay less its jitter"
    assert max(x - i * 50.0 for i, x in enumerate(a)) >= 40.0 + RTO_MS, "a lost segment waits for its retransmission"
    ideal = Link(0.0, 0.0, 0.0, random.Random(1))
    assert [ideal.arrival(t) for t in (0.0, 5.0, 9.0)] == [0.0, 5.0, 9.0]

    assert pct([5, 1, 4, 2, 3], 0.5) == 3 and pct([5, 1, 4, 2, 3], 0.95) == 5 and pct([7], 0.95) == 7
    assert summary([]) == {"n": 0}
    assert summary([10.0, 30.0, 20.0]) == {"n": 3, "p50": 20.0, "p95": 30.0, "max": 30.0}
