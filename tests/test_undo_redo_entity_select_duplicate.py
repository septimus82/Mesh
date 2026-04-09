from __future__ import annotations

import copy

import arcade

from tests._game_window_undo_stub import bind_game_window_undo_methods


class _FakeSceneController:
    def __init__(self, *, scene_path: str, payload: dict) -> None:
        self.current_scene_path = scene_path
        self._loaded_scene_source_data = copy.deepcopy(payload)
        self._loaded_scene_data = copy.deepcopy(payload)

    def get_authored_scene_payload(self) -> dict:
        return self._loaded_scene_source_data

    def debug_apply_authored_scene_payload(self, authored_payload: dict) -> bool:
        self._loaded_scene_source_data = copy.deepcopy(authored_payload)
        self._loaded_scene_data = copy.deepcopy(authored_payload)
        return True

    def debug_duplicate_entities_by_ids(self, ids: list[str], *, dx: float, dy: float) -> dict[str, str]:
        entities = self._loaded_scene_source_data.setdefault("entities", [])
        if not isinstance(entities, list):
            entities = []
            self._loaded_scene_source_data["entities"] = entities

        existing_ids = {e.get("id") for e in entities if isinstance(e, dict)}
        mapping: dict[str, str] = {}
        for entity_id in sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()}):
            original = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
            if not isinstance(original, dict):
                continue
            k = 1
            while f"{entity_id}__dup{k}" in existing_ids:
                k += 1
            new_id = f"{entity_id}__dup{k}"
            clone = dict(original)
            clone["id"] = new_id
            clone["x"] = float(clone.get("x", 0.0)) + float(dx)
            clone["y"] = float(clone.get("y", 0.0)) + float(dy)
            entities.append(clone)
            existing_ids.add(new_id)
            mapping[entity_id] = new_id
        return mapping

    def debug_find_sprite_by_entity_id(self, entity_id: str):  # pragma: no cover
        return None


def _make_window(scene_controller: _FakeSceneController):
    from engine.entity_select_mode import EntitySelectState

    window = type(
        "W",
        (),
        {
            "show_debug": True,
            "scene_controller": scene_controller,
            "scene_dirty_counter": 0,
            "scene_dirty_reason": "",
            "scene_dirty": False,
            "undo_stack": [],
            "redo_stack": [],
            "_undo_ts_counter": 0,
            "_undo_suppress_count": 0,
            "editor_controller": type("E", (), {"active": False})(),
            "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
            "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None})(),
            "entity_snap_to_tile": False,
            "entity_select_state": EntitySelectState(selected_ids=["a", "b"], primary_id="b"),
        },
    )()

    bind_game_window_undo_methods(window, include_undo=True, include_redo=True)
    return window


def test_undo_redo_entity_select_duplicate(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        sc = _FakeSceneController(
            scene_path="scenes/foo.json",
            payload={
                "entities": [
                    {"id": "a", "prefab_id": "slime_blob", "x": 1.0, "y": 2.0},
                    {"id": "b", "prefab_id": "slime_blob", "x": 10.0, "y": 20.0},
                ]
            },
        )
        window = _make_window(sc)
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.D, arcade.key.MOD_CTRL) is True
        assert "ENTITY_DUPLICATE ok count=2" in capsys.readouterr().out.strip()
        assert len(window.undo_stack) == 1

        assert input_capture.handle_key_press(controller, arcade.key.Z, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "UNDO ok depth=0 redo=1"
        ids = sorted(e["id"] for e in sc.get_authored_scene_payload()["entities"])
        assert ids == ["a", "b"]

        assert input_capture.handle_key_press(controller, arcade.key.Y, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "REDO ok depth=1 redo=0"
        ids = sorted(e["id"] for e in sc.get_authored_scene_payload()["entities"])
        assert ids == ["a", "a__dup1", "b", "b__dup1"]
    finally:
        palette.enabled = original_enabled
