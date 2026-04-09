from __future__ import annotations

from types import SimpleNamespace

from engine.ui_overlays import providers as ui_providers
from engine import physics_runtime


def test_physics_broadphase_provider_payload(monkeypatch) -> None:
    window = SimpleNamespace(show_debug=True)

    monkeypatch.setattr(
        physics_runtime,
        "get_broadphase_stats",
        lambda: {
            "enabled": True,
            "build_count": 3,
            "candidate_count": 5,
            "exact_checks_count": 7,
        },
    )
    payload = ui_providers.physics_broadphase_provider(window)

    assert payload["enabled"] is True
    assert payload["build_count"] == 3
    assert payload["candidate_count"] == 5
    assert payload["exact_checks_count"] == 7
