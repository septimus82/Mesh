from __future__ import annotations

from typing import Any

import pytest

import engine.scene_runtime.authoring.entity_ops as entity_ops


pytestmark = [pytest.mark.fast]


def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(spec) for spec in specs]


class _FakeSceneController:
    def __init__(self, entities: list[dict[str, Any]]) -> None:
        self._authored: dict[str, Any] = {"entities": entities}

    def get_authored_scene_payload(self) -> dict[str, Any]:
        return self._authored

    def apply_authored_scene_payload(self, payload: dict[str, Any]) -> None:
        self._authored = payload


def _patch_authoring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        entity_ops,
        "get_authored_scene_payload",
        lambda controller: controller.get_authored_scene_payload(),
    )
    monkeypatch.setattr(
        entity_ops,
        "debug_apply_authored_scene_payload",
        lambda controller, payload: controller.apply_authored_scene_payload(payload),
    )


def _ent_by_id(controller: _FakeSceneController, entity_id: str) -> dict[str, Any]:
    return next(ent for ent in controller._authored.get("entities", []) if ent.get("id") == entity_id)


def test_transform_symbols_exposed_on_entity_ops() -> None:
    for name in (
        "_SNAP_VALID_AXES",
        "_SNAP_VALID_MODES",
        "_ROTATE_VALID_ABOUT",
        "_MIRROR_VALID_AXES",
        "_MIRROR_VALID_ABOUT",
        "_snap_value",
        "debug_snap_to_grid",
        "debug_nudge_selection",
        "debug_rotate_selection",
        "debug_mirror_selection",
    ):
        assert hasattr(entity_ops, name)
    assert callable(entity_ops._snap_value)
    assert callable(entity_ops.debug_snap_to_grid)
    assert callable(entity_ops.debug_nudge_selection)
    assert callable(entity_ops.debug_rotate_selection)
    assert callable(entity_ops.debug_mirror_selection)


def test_snap_to_grid_changes_entity_position(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(_make_entities({"id": "a", "x": 7.0, "y": 9.0}))
    result = entity_ops.debug_snap_to_grid(controller, ["a"], step=8, axes="xy", mode="nearest")
    assert result["ok"] is True
    assert _ent_by_id(controller, "a")["x"] == pytest.approx(8.0)
    assert _ent_by_id(controller, "a")["y"] == pytest.approx(8.0)


def test_nudge_invalid_count_returns_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(_make_entities({"id": "a", "x": 1.0, "y": 2.0}))
    result = entity_ops.debug_nudge_selection(controller, ["a"], dx=1.0, dy=0.0, count=0)
    assert result["ok"] is False


def test_rotate_self_updates_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(_make_entities({"id": "a", "x": 0.0, "y": 0.0, "rotation": 10.0}))
    result = entity_ops.debug_rotate_selection(controller, ["a"], deg=45.0, about="self")
    assert result["ok"] is True
    assert _ent_by_id(controller, "a")["rotation"] == pytest.approx(55.0)


def test_mirror_invalid_axis_returns_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(_make_entities({"id": "a", "x": 0.0, "y": 0.0}))
    result = entity_ops.debug_mirror_selection(controller, ["a"], axis="z")
    assert result["ok"] is False
