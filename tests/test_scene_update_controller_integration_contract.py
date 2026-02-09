from __future__ import annotations

from types import SimpleNamespace

import engine.scene_update_controller as scene_update_controller
from engine.scene_update_controller import SceneUpdateController


def test_update_controller_runs_stages_in_order(monkeypatch) -> None:
    calls: list[str] = []

    def _handle_load(_controller: object) -> bool:
        calls.append("pending_load")
        return True

    def _handle_change(_controller: object) -> bool:
        calls.append("pending_change")
        return True

    monkeypatch.setattr(scene_update_controller, "handle_pending_scene_load", _handle_load)
    monkeypatch.setattr(scene_update_controller, "handle_pending_scene_change", _handle_change)

    controller = SimpleNamespace(
        _pending_scene_path=None,
        _pending_scene_change=None,
        window=SimpleNamespace(paused=False),
        _pre_update_behaviour_stage=lambda dt: calls.append("pre"),
        _update_behaviour_stage=lambda dt: calls.append("behaviour"),
        _update_movement_stage=lambda dt: calls.append("movement"),
        _update_animation_stage=lambda dt: calls.append("animation"),
        _late_update_stage=lambda dt: calls.append("late"),
    )

    SceneUpdateController().handle_update(0.1, controller)

    assert calls == ["pre", "behaviour", "movement", "animation", "late"]


def test_update_controller_pending_load_short_circuits(monkeypatch) -> None:
    calls: list[str] = []

    def _handle_load(_controller: object) -> bool:
        calls.append("pending_load")
        return True

    monkeypatch.setattr(scene_update_controller, "handle_pending_scene_load", _handle_load)

    controller = SimpleNamespace(
        _pending_scene_path="scenes/a.json",
        _pending_scene_change=None,
        window=SimpleNamespace(paused=False),
        _pre_update_behaviour_stage=lambda dt: calls.append("pre"),
        _update_behaviour_stage=lambda dt: calls.append("behaviour"),
        _update_movement_stage=lambda dt: calls.append("movement"),
        _update_animation_stage=lambda dt: calls.append("animation"),
        _late_update_stage=lambda dt: calls.append("late"),
    )

    SceneUpdateController().handle_update(0.1, controller)

    assert calls == ["pending_load"]


def test_update_controller_paused_does_not_run_stages(monkeypatch) -> None:
    calls: list[str] = []

    def _handle_load(_controller: object) -> bool:
        calls.append("pending_load")
        return True

    monkeypatch.setattr(scene_update_controller, "handle_pending_scene_load", _handle_load)

    controller = SimpleNamespace(
        _pending_scene_path=None,
        _pending_scene_change=None,
        window=SimpleNamespace(paused=True),
        _pre_update_behaviour_stage=lambda dt: calls.append("pre"),
        _update_behaviour_stage=lambda dt: calls.append("behaviour"),
        _update_movement_stage=lambda dt: calls.append("movement"),
        _update_animation_stage=lambda dt: calls.append("animation"),
        _late_update_stage=lambda dt: calls.append("late"),
    )

    SceneUpdateController().handle_update(0.1, controller)

    assert calls == []
