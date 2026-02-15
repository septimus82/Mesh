from __future__ import annotations

import engine.action_runtime.registry as action_registry
import engine.behaviours as behaviours_pkg
import engine.encounter_sets as encounter_sets
from engine.singletons import get_registry, reset_registry_for_tests


def test_registry_reset_propagates_seed_deterministically() -> None:
    registry_a = reset_registry_for_tests(seed=12345)
    seq_a = [registry_a.rng_service.randint(0, 10_000) for _ in range(8)]

    registry_b = reset_registry_for_tests(seed=12345)
    seq_b = [registry_b.rng_service.randint(0, 10_000) for _ in range(8)]

    assert seq_a == seq_b


def test_registry_reset_clears_known_mutable_singletons() -> None:
    reset_registry_for_tests(seed=7)
    _ = action_registry.get_actions()
    setattr(behaviours_pkg, "_BUILTINS_LOADED", True)
    setattr(encounter_sets, "_THEME_MANAGER", object())

    before = get_registry().snapshot_singletons()
    assert before["action_registry_cached_actions"] > 0
    assert isinstance(before["behaviours_builtins_loaded"], bool)
    assert isinstance(before["encounter_theme_manager_initialized"], bool)

    after_registry = reset_registry_for_tests(seed=7)
    after = after_registry.snapshot_singletons()
    assert after["action_registry_cached_actions"] == 0
    assert isinstance(after["editor_shortcut_conflicts_warned"], int)
    assert after["editor_shortcut_conflicts_warned"] >= 0
    assert after["behaviours_builtins_loaded"] is False
    assert after["encounter_theme_manager_initialized"] is False


def test_registry_gameplay_bus_factory_returns_fresh_bus_instances() -> None:
    registry = reset_registry_for_tests(seed=1)
    bus_a = registry.create_gameplay_event_bus()
    bus_b = registry.create_gameplay_event_bus()

    bus_a.emit("alpha")
    assert bus_a.pending_count() == 1
    assert bus_b.pending_count() == 0
