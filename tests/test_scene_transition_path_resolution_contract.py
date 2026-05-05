from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.scene_runtime import transitions

pytestmark = [pytest.mark.fast]


class _ExistingPath:
    def __init__(self, exists: bool) -> None:
        self._exists = bool(exists)

    def exists(self) -> bool:
        return self._exists


class _WorldController:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = dict(mapping)

    def get_scene_path(self, key: str) -> str | None:
        return self.mapping.get(key)


def _controller(*, world_controller: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(window=SimpleNamespace(world_controller=world_controller), scene_settings={})


def test_request_scene_change_resolves_world_scene_key() -> None:
    controller = _controller(world_controller=_WorldController({"upper_hall": "scenes/upper_hall.json"}))

    transitions.request_scene_change(controller, "upper_hall")

    assert controller._pending_scene_path == "scenes/upper_hall.json"
    assert controller._clear_assets_on_next_load is False


def test_queue_scene_change_resolves_bare_scene_stem(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _resolve(path: str) -> _ExistingPath:
        seen.append(path)
        return _ExistingPath(path == "scenes/cellar.json")

    monkeypatch.setattr(transitions, "resolve_path", _resolve)
    controller = _controller()

    transitions.queue_scene_change(controller, "cellar", spawn_id="stairs")

    assert seen == ["scenes/cellar.json"]
    assert controller._pending_scene_change == {"scene_path": "scenes/cellar.json", "spawn_id": "stairs"}


def test_request_scene_change_blank_input_returns_without_queueing() -> None:
    for value in ("", " "):
        controller = _controller()

        transitions.request_scene_change(controller, value)

        assert not hasattr(controller, "_pending_scene_path")
        assert not hasattr(controller, "_clear_assets_on_next_load")


def test_queue_scene_change_blank_input_returns_without_queueing() -> None:
    for value in ("", " "):
        controller = _controller()

        transitions.queue_scene_change(controller, value, spawn_id="stairs")

        assert not hasattr(controller, "_pending_scene_change")


def test_request_scene_change_preserves_explicit_json_path() -> None:
    controller = _controller(world_controller=_WorldController({"demo": "scenes/other.json"}))

    transitions.request_scene_change(controller, "scenes/demo.json")

    assert controller._pending_scene_path == "scenes/demo.json"


def test_request_scene_change_preserves_unknown_bare_input_when_no_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transitions, "resolve_path", lambda _path: _ExistingPath(False))
    controller = _controller(world_controller=None)

    transitions.request_scene_change(controller, "unknown_scene")

    assert controller._pending_scene_path == "unknown_scene"
