"""M1-B-2: the frame-time report's statistics (tooling/hd2d_m1b_scene.py ``summary``): median, nearest-rank p95/p99, the
worst frame and the five worst by index. Pure: no window, no timing."""

from __future__ import annotations

import importlib
import sys

import pytest

pytestmark = pytest.mark.fast


def test_summary_percentiles_and_worst_frames() -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "path", list(sys.path))  # (the tool puts the repo and tooling/ on its path: not ours)
        summary = importlib.import_module("tooling.hd2d_m1b_scene").summary

    values = [float(v) for v in range(1, 101)]  # 1 .. 100 ms
    values[10], values[50] = 500.0, 250.0  # two spikes, at frames 10 and 50
    got = summary(values)
    assert got["n"] == 100
    assert got["median_ms"] == 52.5  # (1..100 without 11 and 51, plus the spikes: the 50th and 51st are 52, 53)
    assert got["p95_ms"] == 97.0 and got["p99_ms"] == 250.0  # nearest rank: the 95th and 99th smallest
    assert got["max_ms"] == 500.0
    assert got["worst"] == [[10, 500.0], [50, 250.0], [99, 100.0], [98, 99.0], [97, 98.0]]
    assert summary([3.333])["p95_ms"] == summary([3.333])["max_ms"] == 3.33
