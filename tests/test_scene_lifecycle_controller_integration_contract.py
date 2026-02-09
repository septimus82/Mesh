from __future__ import annotations

from types import SimpleNamespace

from engine.scene_lifecycle_controller import handle_pending_scene_change, handle_pending_scene_load


class _Assets:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


class _Audio:
    def __init__(self) -> None:
        self.cleared = False

    def clear_cache(self) -> None:
        self.cleared = True


class _Camera:
    def __init__(self) -> None:
        self.moved_to: tuple[float, float] | None = None

    def move_to(self, pos: tuple[float, float], _duration: float) -> None:
        self.moved_to = pos


class _Window:
    def __init__(self) -> None:
        self._mesh_event_queue = ["evt"]
        self.assets = _Assets()
        self.audio = _Audio()
        self.camera = _Camera()
        self.camera_controller = SimpleNamespace(zoom_state=SimpleNamespace(current=2.0))
        self.zoom_target: float | None = None

    def get_camera_center(self) -> tuple[float, float]:
        return (7.0, 8.0)

    def set_camera_zoom_target(self, zoom: float, speed: float = 1.0) -> None:
        self.zoom_target = float(zoom)


class _Controller:
    def __init__(self) -> None:
        self.window = _Window()
        self._pending_scene_path: str | None = None
        self._pending_scene_change: dict[str, str] | None = None
        self._clear_assets_on_next_load = False
        self.current_scene_path: str | None = None
        self._preserved_camera_state: dict[str, float] | None = None
        self.loaded: list[str] = []
        self.performed: list[tuple[str, str | None]] = []

    def load_scene(self, scene_path: str) -> None:
        self.loaded.append(scene_path)

    def _perform_scene_change(self, scene_path: str, spawn_id: str | None = None) -> None:
        self.performed.append((scene_path, spawn_id))


def test_handle_pending_scene_load_reload_restores_camera() -> None:
    controller = _Controller()
    controller.current_scene_path = "scenes/a.json"
    controller._pending_scene_path = "scenes/a.json"
    controller._clear_assets_on_next_load = True
    controller._preserved_camera_state = {"x": 1.0, "y": 2.0, "zoom": 1.5}

    handled = handle_pending_scene_load(controller)

    assert handled is True
    assert controller.loaded == ["scenes/a.json"]
    assert controller.window.assets.cleared is True
    assert controller.window.audio.cleared is True
    assert controller.window.camera.moved_to == (1.0, 2.0)
    assert controller.window.zoom_target == 1.5
    assert controller._pending_scene_path is None
    assert controller._clear_assets_on_next_load is False
    assert controller._preserved_camera_state is None
    assert controller.window._mesh_event_queue == []


def test_handle_pending_scene_change_dispatches() -> None:
    controller = _Controller()
    controller._pending_scene_change = {"scene_path": "scenes/b.json", "spawn_id": "spawn"}

    handled = handle_pending_scene_change(controller)

    assert handled is True
    assert controller.performed == [("scenes/b.json", "spawn")]
    assert controller._pending_scene_change is None
