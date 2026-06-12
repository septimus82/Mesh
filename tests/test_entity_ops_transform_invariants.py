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


def _state_by_id(controller: _FakeSceneController, ids: list[str]) -> dict[str, tuple[float, float, float]]:
    by_id = {str(ent.get("id")): ent for ent in controller._authored.get("entities", []) if isinstance(ent, dict)}
    out: dict[str, tuple[float, float, float]] = {}
    for entity_id in ids:
        ent = by_id[entity_id]
        out[entity_id] = (
            float(ent.get("x", 0.0)),
            float(ent.get("y", 0.0)),
            float(ent.get("rotation", 0.0)),
        )
    return out


def test_snap_idempotence(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    ids = ["a", "b"]
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 7.0, "y": 9.0},
            {"id": "b", "x": -9.0, "y": 31.0},
        )
    )
    first = entity_ops.debug_snap_to_grid(controller, ids, step=8, axes="xy", mode="nearest")
    assert first["ok"] is True
    after_first = _state_by_id(controller, ids)
    second = entity_ops.debug_snap_to_grid(controller, ids, step=8, axes="xy", mode="nearest")
    after_second = _state_by_id(controller, ids)
    assert after_second == after_first
    assert second["moved"] == 0


def test_nudge_linearity(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    ids = ["a", "b"]
    start = _make_entities(
        {"id": "a", "x": 1.0, "y": 2.0},
        {"id": "b", "x": 5.0, "y": -3.0},
    )
    controller_twice = _FakeSceneController(_make_entities(*start))
    controller_once = _FakeSceneController(_make_entities(*start))

    entity_ops.debug_nudge_selection(controller_twice, ids, dx=1.5, dy=-2.0, count=1)
    entity_ops.debug_nudge_selection(controller_twice, ids, dx=1.5, dy=-2.0, count=1)

    entity_ops.debug_nudge_selection(controller_once, ids, dx=3.0, dy=-4.0, count=1)

    assert _state_by_id(controller_twice, ids) == _state_by_id(controller_once, ids)


def test_rotate_cw_then_ccw_reverses_within_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    ids = ["a", "b", "c"]
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 0.0, "y": 0.0, "rotation": 10.0},
            {"id": "b", "x": 20.0, "y": 0.0, "rotation": 45.0},
            {"id": "c", "x": 10.0, "y": 10.0, "rotation": 120.0},
        )
    )
    baseline = _state_by_id(controller, ids)

    result_cw = entity_ops.debug_rotate_selection(controller, ids, deg=90.0, about="group")
    assert result_cw["ok"] is True
    result_ccw = entity_ops.debug_rotate_selection(controller, ids, deg=-90.0, about="group")
    assert result_ccw["ok"] is True
    after = _state_by_id(controller, ids)

    for entity_id in ids:
        bx, by, br = baseline[entity_id]
        ax, ay, ar = after[entity_id]
        assert ax == pytest.approx(bx, abs=1e-6)
        assert ay == pytest.approx(by, abs=1e-6)
        assert ar == pytest.approx(br, abs=1e-6)


@pytest.mark.parametrize("axis", ["x", "y"])
def test_mirror_twice_returns_original(axis: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_authoring(monkeypatch)
    ids = ["a", "b"]
    controller = _FakeSceneController(
        _make_entities(
            {"id": "a", "x": 3.0, "y": 7.0, "rotation": 20.0},
            {"id": "b", "x": 13.0, "y": 11.0, "rotation": 200.0},
        )
    )
    baseline = _state_by_id(controller, ids)

    first = entity_ops.debug_mirror_selection(controller, ids, axis=axis, about="group", include_rotation=True)
    assert first["ok"] is True
    second = entity_ops.debug_mirror_selection(controller, ids, axis=axis, about="group", include_rotation=True)
    assert second["ok"] is True
    after = _state_by_id(controller, ids)

    for entity_id in ids:
        bx, by, br = baseline[entity_id]
        ax, ay, ar = after[entity_id]
        assert ax == pytest.approx(bx, abs=1e-6)
        assert ay == pytest.approx(by, abs=1e-6)
        assert ar == pytest.approx(br, abs=1e-6)

