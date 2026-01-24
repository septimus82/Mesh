from __future__ import annotations

import arcade


def test_entity_select_delete_removes_all_selected_except_player() -> None:
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        sprites = {"e1": {"prefab_id": "slime_blob"}, "p1": {"prefab_id": "player"}}

        class _Scene:
            def debug_remove_entity_by_id(self, entity_id: str) -> bool:
                s = sprites.get(entity_id)
                if s is None:
                    return False
                if s.get("prefab_id") == "player":
                    return False
                del sprites[entity_id]
                return True

        class _Console:
            active = False

            def toggle(self) -> None:  # pragma: no cover
                return

            def process_key(self, _key: int, _mod: int) -> bool:
                return False

        class _UI:
            def on_key_press(self, _key: int, _mod: int) -> bool:
                return False

        class _Window:
            show_debug = True
            console_controller = _Console()
            ui_controller = _UI()
            editor_controller = type("E", (), {"active": False})()
            scene_inspector_overlay = type("O", (), {"visible": False})()
            scene_controller = _Scene()
            entity_select_state = EntitySelectState(selected_ids=["p1", "e1"], primary_id="p1")

            def __init__(self) -> None:
                self.scene_dirty_reason = ""
                self.scene_dirty_counter = 0

            def mark_scene_dirty(self, reason: str) -> None:
                self.scene_dirty_reason = str(reason)
                self.scene_dirty_counter += 1

        window = _Window()
        controller = type("C", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert input_capture.handle_key_press(controller, arcade.key.DELETE, 0) is True
        assert "e1" not in sprites
        assert "p1" in sprites
        assert window.entity_select_state.selected_ids == []
        assert window.scene_dirty_reason == "entity_select_multi"
        assert window.scene_dirty_counter == 1
    finally:
        palette.enabled = original_enabled

