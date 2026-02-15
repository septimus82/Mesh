from __future__ import annotations

from mesh_cli.episode import _compute_percentile_ms, _round_ms


def test_episode_replay_round_ms_is_deterministic() -> None:
    assert _round_ms(1.23456) == 1.235
    assert _round_ms(1.23444) == 1.234
    assert _round_ms(0.0) == 0.0


def test_episode_replay_percentile_uses_nearest_rank() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _compute_percentile_ms(values, 0.50) == 3.0
    assert _compute_percentile_ms(values, 0.95) == 5.0
    assert _compute_percentile_ms([], 0.95) == 0.0
