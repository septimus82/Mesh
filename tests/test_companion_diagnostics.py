from __future__ import annotations

import pytest

from engine.monster.companion_mind import CompanionMind, LearnedWeights

pytestmark = pytest.mark.fast


def test_companion_diagnostics_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_COMPANION_DIAG", raising=False)
    from engine.companion_diagnostics import log_companion_battle_start

    log_companion_battle_start(
        instance_id="sproutling_0001",
        source="saved",
        mind=CompanionMind(),
    )


def test_companion_diagnostics_enabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import companion_diagnostics

    monkeypatch.delenv("MESH_COMPANION_DIAG", raising=False)
    assert companion_diagnostics.enabled() is False
    monkeypatch.setenv("MESH_COMPANION_DIAG", "1")
    assert companion_diagnostics.enabled() is True
    companion_diagnostics.log_companion_battle_start(
        instance_id="sproutling_0001",
        source="saved",
        mind=CompanionMind(
            learned=LearnedWeights(ATTACK=12.0, DEFEND=3.0, HESITATE=1.0),
            trust=72.0,
            bond=48.0,
        ),
    )
    companion_diagnostics.log_companion_battle_end(
        instance_id="sproutling_0001",
        mind=CompanionMind(bond=49.0, trust=74.0, learned=LearnedWeights(ATTACK=17.0)),
        outcome="won",
        party_ids=["sproutling_0001"],
    )
