from __future__ import annotations

import pytest

import engine.lighting.shadows as shadows_mod
from engine.lighting.shadow_backend import choose_shadow_backend, decision_to_diagnostics
from engine.lighting.shadows import get_shadow_backend_diagnostics

pytestmark = [pytest.mark.fast]


def test_choose_shadow_backend_is_deterministic() -> None:
    use_decision = choose_shadow_backend(
        env={},
        flags={},
        capabilities={"has_use": True, "has_activate": True},
    )
    activate_decision = choose_shadow_backend(
        env={},
        flags={},
        capabilities={"has_use": False, "has_activate": True},
    )
    none_decision = choose_shadow_backend(
        env={},
        flags={},
        capabilities={"has_use": False, "has_activate": False},
    )

    assert use_decision.name == "fbo.use"
    assert use_decision.reason == "fbo.use available"
    assert use_decision.fallbacks == ["fbo.activate", "none"]
    assert use_decision.ok is True

    assert activate_decision.name == "fbo.activate"
    assert activate_decision.reason == "fbo.activate available"
    assert activate_decision.fallbacks == ["none"]
    assert activate_decision.ok is True

    assert none_decision.name == "none"
    assert none_decision.reason == "fbo has no use/activate"
    assert none_decision.fallbacks == []
    assert none_decision.ok is False

    # Determinism on repeated calls with same input.
    use_decision_2 = choose_shadow_backend(
        env={},
        flags={},
        capabilities={"has_use": True, "has_activate": True},
    )
    assert use_decision_2 == use_decision


def test_shadow_backend_diagnostics_schema_and_order() -> None:
    decision = choose_shadow_backend(
        env={},
        flags={},
        capabilities={"has_use": True, "has_activate": True},
    )
    diag = decision_to_diagnostics(decision)
    assert list(diag.keys()) == ["schema_version", "selected", "reason", "fallbacks"]
    assert diag["schema_version"] == 1
    assert diag["selected"] == "fbo.use"
    assert diag["reason"] == "fbo.use available"
    assert diag["fallbacks"] == ["fbo.activate", "none"]

    # Ensure shadows.py exposed diagnostics surface is deterministic and schema-stable.
    shadows_mod._set_shadow_backend_diagnostics(decision)
    cached = get_shadow_backend_diagnostics()
    assert list(cached.keys()) == ["schema_version", "selected", "reason", "fallbacks"]
    assert cached == diag

