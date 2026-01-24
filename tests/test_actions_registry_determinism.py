from __future__ import annotations

from engine.action_runtime import registry


def test_action_table_keys_are_stable() -> None:
    first = registry.build_actions()
    second = registry.build_actions()
    assert list(first.keys()) == list(second.keys())


def test_list_actions_is_sorted() -> None:
    actions = registry.get_actions()
    listed = registry.list_actions()
    assert listed == sorted(actions.keys())


def test_required_actions_is_stable() -> None:
    first = sorted(registry.build_required_actions())
    second = sorted(registry.build_required_actions())
    assert first == second

