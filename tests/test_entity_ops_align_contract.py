from __future__ import annotations

from typing import Any

import pytest

import engine.scene_runtime.authoring.entity_ops as entity_ops


pytestmark = [pytest.mark.fast]


def _make_entities(*specs: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        out.append(dict(spec))
    return out


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


def test_align_distribute_symbols_exposed_on_entity_ops() -> None:
    for name in (
        "debug_align_selection",
        "debug_distribute_selection",
        "_ALIGN_X_MODES",
        "_ALIGN_Y_MODES",
        "_ALIGN_VALID_AXES",
        "_ALIGN_VALID_REFS",
        "_DISTRIBUTE_VALID_MODES",
    ):
        assert hasattr(entity_ops, name)
    assert callable(entity_ops.debug_align_selection)
    assert callable(entity_ops.debug_distribute_selection)


def test_distribute_center_keeps_endpoints_and_moves_middle(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 10.0, "y": 0.0},
            {"id": "c", "x": 90.0, "y": 0.0},
        )
    )
    result = entity_ops.debug_distribute_selection(controller, ["a", "b", "c"], axis="x", mode="center")
    assert result["ok"] is True
    assert _ent_by_id(controller, "a")["x"] == pytest.approx(0.0)
    assert _ent_by_id(controller, "b")["x"] == pytest.approx(45.0)
    assert _ent_by_id(controller, "c")["x"] == pytest.approx(90.0)


def test_distribute_gap_fewer_than_three_entities_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
        )
    )
    result = entity_ops.debug_distribute_selection(controller, ["a", "b"], axis="x", mode="gap")
    assert result["ok"] is False


def test_align_invalid_axis_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0},
            {"id": "b", "x": 50.0, "y": 0.0},
        )
    )
    result = entity_ops.debug_align_selection(controller, ["a", "b"], axis="z", mode="left")
    assert result["ok"] is False
