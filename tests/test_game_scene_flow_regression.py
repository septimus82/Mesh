from __future__ import annotations

from dataclasses import dataclass, field

from engine.game_runtime import scene_flow


@dataclass
class _StubParticleManager:
    events: list[str] = field(default_factory=list)

    def clear(self) -> None:
        self.events.append("clear")


@dataclass
class _StubSceneController:
    events: list[str] = field(default_factory=list)
    reload_return: bool = True
    last_reload_arg: str | None = None
    last_request_reload: bool | None = None
    last_scene_change: str | None = None

    def load_scene(self, scene_path: str):
        self.events.append(f"load:{scene_path}")
        return {"ok": True, "scene_path": scene_path}

    def request_scene_reload(self, clear_assets: bool = False) -> None:
        self.last_request_reload = clear_assets
        self.events.append(f"request_reload:{clear_assets}")

    def request_scene_change(self, scene_path: str) -> None:
        self.last_scene_change = scene_path
        self.events.append(f"request_change:{scene_path}")

    def reload_scene(self, new_path: str | None = None) -> bool:
        self.last_reload_arg = new_path
        self.events.append(f"reload:{new_path}")
        return self.reload_return


@dataclass
class _StubWindow:
    particle_manager: _StubParticleManager
    scene_controller: _StubSceneController

    def request_scene_reload(self, clear_assets: bool = False) -> None:
        self.scene_controller.request_scene_reload(clear_assets)


def test_reload_scene_clears_particles_before_scene_reload() -> None:
    events: list[str] = []
    window = _StubWindow(
        particle_manager=_StubParticleManager(events=events),
        scene_controller=_StubSceneController(events=events, reload_return=False),
    )

    ok = scene_flow.reload_scene(window, None)

    assert ok is False
    assert events == ["clear", "reload:None"]


def test_request_reload_current_scene_delegates_to_request_scene_reload() -> None:
    events: list[str] = []
    window = _StubWindow(
        particle_manager=_StubParticleManager(events=events),
        scene_controller=_StubSceneController(events=events),
    )

    scene_flow.request_reload_current_scene(window, clear_assets=True)

    assert window.scene_controller.last_request_reload is True
    assert "request_reload:True" in events
