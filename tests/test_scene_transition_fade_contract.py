from types import SimpleNamespace

from engine.scene_runtime import transitions
from engine.ui_overlays.transition_fade import TransitionFadeOverlay


def test_scene_transition_fade_defers_scene_change(monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def _fake_perform(controller, scene_path: str, spawn_id: str | None = None) -> None:
        calls.append((scene_path, spawn_id))

    monkeypatch.setattr(transitions, "perform_scene_change", _fake_perform)

    window = SimpleNamespace(
        engine_config=SimpleNamespace(scene_fade_enabled=True, scene_fade_out_s=0.2, scene_fade_in_s=0.3)
    )
    overlay = TransitionFadeOverlay(window)
    window.transition_fade_overlay = overlay
    controller = SimpleNamespace(window=window, scene_settings={})

    transitions.request_scene_change(controller, "scenes/demo.json")

    assert calls == []
    overlay.update(0.1)
    assert calls == []

    overlay.update(0.1)
    assert calls == [("scenes/demo.json", None)]

    alpha_at_start = overlay.alpha
    overlay.update(0.1)
    assert overlay.alpha < alpha_at_start
