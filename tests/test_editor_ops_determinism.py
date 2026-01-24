from __future__ import annotations

import types
from typing import Any

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController


class _ParamDef:
    def __init__(self, default: Any, typ: Any) -> None:
        self.default = default
        self.type = typ


class _StubSprite:
    def __init__(self) -> None:
        self.mesh_name = "thing"
        self.mesh_entity_data: dict[str, Any] = {
            "name": "thing",
            "behaviour_config": {
                "TestBehaviour": {"z": 3, "a": 1},
            },
        }
        self.mesh_behaviours = ["TestBehaviour"]
        self.mesh_behaviours_runtime = []


class _StubSceneController:
    def _ensure_entity_data_dict(self, sprite: _StubSprite) -> dict[str, Any]:
        return sprite.mesh_entity_data

    def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        return entity_data.setdefault("behaviour_config", {})


def test_inspector_param_order_is_sorted_deterministically(monkeypatch) -> None:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    def fake_param_defs(_name: str):
        return {"b": _ParamDef(default=2, typ=int), "a": _ParamDef(default=0, typ=int)}

    monkeypatch.setattr(editor_module, "get_behaviour_param_defs", fake_param_defs)

    window = types.SimpleNamespace()
    window.strict_mode = False
    window.scene_controller = _StubSceneController()

    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True
    controller.selected_entity = _StubSprite()  # type: ignore[assignment]

    items = controller._build_inspector_items()
    keys = [item["name"] for item in items if item.get("type") == "param"]
    assert keys == ["a", "b", "z"]

