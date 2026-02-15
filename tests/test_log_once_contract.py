from __future__ import annotations

from engine.log_once import get_log_count, log_once_with_counter, reset_log_counters
from engine.singletons import get_registry, reset_registry_for_tests


def test_log_once_counts_all_calls_and_logs_once_state() -> None:
    reset_registry_for_tests(seed=1)
    reset_log_counters()
    key = "phase39.log_once"

    log_once_with_counter(key, "hello")
    log_once_with_counter(key, "hello again")

    snap = get_registry().snapshot_singletons()
    assert get_log_count(key) == 2
    assert snap["log_once_seen"] == 1
    assert snap["log_once_keys"] == 1


def test_log_once_state_resets_via_registry_reset() -> None:
    reset_registry_for_tests(seed=2)
    key = "phase39.reset"
    log_once_with_counter(key, "x")
    assert get_log_count(key) == 1

    reset_registry_for_tests(seed=2)
    assert get_log_count(key) == 0
    snap = get_registry().snapshot_singletons()
    assert snap["log_once_seen"] == 0

