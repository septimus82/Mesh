from __future__ import annotations

from engine.editor import editor_actions
from engine.editor.editor_actions_registry import DEFAULT_ACTION_DEFS


def test_registry_deterministic_order() -> None:
    ids_a = [spec.id for spec in DEFAULT_ACTION_DEFS]
    ids_b = [spec.id for spec in DEFAULT_ACTION_DEFS]
    assert ids_a == ids_b


def test_registry_callables_resolve() -> None:
    for spec in DEFAULT_ACTION_DEFS:
        enabled_fn = getattr(editor_actions, spec.enabled, None)
        run_fn = getattr(editor_actions, spec.run, None)
        assert callable(enabled_fn), f"enabled not callable: {spec.enabled}"
        assert callable(run_fn), f"run not callable: {spec.run}"
