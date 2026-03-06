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


def _positions_by_id(controller: _FakeSceneController, ids: list[str]) -> dict[str, tuple[float, float]]:
    by_id = {str(ent.get("id")): ent for ent in controller._authored.get("entities", []) if isinstance(ent, dict)}
    out: dict[str, tuple[float, float]] = {}
    for entity_id in ids:
        ent = by_id[entity_id]
        out[entity_id] = (float(ent.get("x", 0.0)), float(ent.get("y", 0.0)))
    return out


def test_align_idempotence(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    ids = ["a", "b", "c"]
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 0.0, "y": 2.0, "width": 20.0},
            {"id": "b", "x": 13.0, "y": 5.0, "width": 10.0},
            {"id": "c", "x": 35.0, "y": 8.0, "width": 16.0},
        )
    )
    first = entity_ops.debug_align_selection(controller, ids, axis="x", mode="left", reference="group")
    assert first["ok"] is True
    after_first = _positions_by_id(controller, ids)
    second = entity_ops.debug_align_selection(controller, ids, axis="x", mode="left", reference="group")
    assert second["ok"] is True
    after_second = _positions_by_id(controller, ids)
    assert after_second == after_first


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("mode", ["gap", "center"])
def test_distribute_endpoint_preservation(axis: str, mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    ids = ["a", "b", "c", "d"]
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 0.0, "y": 10.0, "width": 10.0, "height": 8.0},
            {"id": "b", "x": 10.0, "y": 30.0, "width": 12.0, "height": 10.0},
            {"id": "c", "x": 40.0, "y": 70.0, "width": 16.0, "height": 12.0},
            {"id": "d", "x": 90.0, "y": 120.0, "width": 20.0, "height": 14.0},
        )
    )
    before = _positions_by_id(controller, ids)
    result = entity_ops.debug_distribute_selection(controller, ids, axis=axis, mode=mode, reference="group")
    assert result["ok"] is True
    after = _positions_by_id(controller, ids)

    if axis == "x":
        assert after["a"][0] == pytest.approx(before["a"][0])
        assert after["d"][0] == pytest.approx(before["d"][0])
    else:
        assert after["a"][1] == pytest.approx(before["a"][1])
        assert after["d"][1] == pytest.approx(before["d"][1])


def test_align_input_order_independence(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    entities = _make_entities(
        {"id": "a", "x": 5.0, "y": 10.0, "height": 12.0},
        {"id": "b", "x": 15.0, "y": 25.0, "height": 10.0},
        {"id": "c", "x": 30.0, "y": 40.0, "height": 8.0},
    )
    controller_a = _FakeSceneController(_make_entities(*entities))
    controller_b = _FakeSceneController(_make_entities(*entities))

    ids_sorted = ["a", "b", "c"]
    ids_shuffled = ["c", "a", "b"]

    result_a = entity_ops.debug_align_selection(controller_a, ids_sorted, axis="y", mode="top", reference="group")
    result_b = entity_ops.debug_align_selection(controller_b, ids_shuffled, axis="y", mode="top", reference="group")
    assert result_a["ok"] is True
    assert result_b["ok"] is True

    pos_a = _positions_by_id(controller_a, ids_sorted)
    pos_b = _positions_by_id(controller_b, ids_sorted)
    assert pos_a == pos_b

