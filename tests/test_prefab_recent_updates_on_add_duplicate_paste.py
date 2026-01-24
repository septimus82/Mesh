from __future__ import annotations

import arcade


def test_prefab_recent_updates_on_add_duplicate_paste(capsys) -> None:
    from engine.entity_paint_mode import EntityPaintState, PrefabInfo
    from engine.entity_select_mode import EntitySelectState
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _SceneController:
            current_scene_path = "scenes/test.json"

            def __init__(self) -> None:
                self._authored = {"entities": []}

            def get_authored_scene_payload(self) -> dict:
                return self._authored

            def debug_add_entity_payload(self, payload: dict) -> bool:
                ents = self._authored.setdefault("entities", [])
                assert isinstance(ents, list)
                ents.append(dict(payload))
                return True

            def debug_duplicate_entities_by_ids(self, ids: list[str], *, dx: float, dy: float) -> dict[str, str]:
                ents = self._authored.setdefault("entities", [])
                assert isinstance(ents, list)
                existing_ids = {e.get("id") for e in ents if isinstance(e, dict)}
                mapping: dict[str, str] = {}
                for entity_id in sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()}):
                    original = next((e for e in ents if isinstance(e, dict) and e.get("id") == entity_id), None)
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
                    ents.append(clone)
                    existing_ids.add(new_id)
                    mapping[entity_id] = new_id
                return mapping

            def debug_paste_entities_from_clipboard(
                self, clip: dict, *, anchor_x: float, anchor_y: float, snap_to_tile: bool = False  # noqa: ARG002
            ) -> tuple[list[str], str]:
                ents = self._authored.setdefault("entities", [])
                assert isinstance(ents, list)
                pasted: list[str] = []
                entities = clip.get("entities") if isinstance(clip, dict) else None
                rel = clip.get("rel_offsets") if isinstance(clip, dict) else None
                if not isinstance(entities, list) or not isinstance(rel, dict):
                    return ([], "")
                for entry in entities:
                    if not isinstance(entry, dict):
                        continue
                    orig_id = str(entry.get("orig_id") or "").strip()
                    if not orig_id:
                        continue
                    k = 0
                    new_id = f"{orig_id}__paste{k}"
                    dx = rel.get(orig_id, {}).get("dx", 0.0) if isinstance(rel.get(orig_id), dict) else 0.0
                    dy = rel.get(orig_id, {}).get("dy", 0.0) if isinstance(rel.get(orig_id), dict) else 0.0
                    clone = dict(entry)
                    clone.pop("orig_id", None)
                    clone["id"] = new_id
                    clone["x"] = float(anchor_x) + float(dx)
                    clone["y"] = float(anchor_y) + float(dy)
                    ents.append(clone)
                    pasted.append(new_id)
                pasted.sort()
                primary = pasted[0] if pasted else ""
                return (pasted, primary)

        entity_state = EntityPaintState(
            enabled=True,
            prefabs=(PrefabInfo(prefab_id="slime_blob", tags=("enemy",)), PrefabInfo(prefab_id="crate", tags=())),
            selected_index=0,
            filter_mode="all",
        )

        class _Window:
            show_debug = True
            scene_controller = _SceneController()
            entity_paint_state = entity_state
            tile_paint_state = type("TP", (), {"enabled": False})()
            capture_state = type("CS", (), {"enabled": False})()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()
            editor_controller = type("E", (), {"active": False})()
            entity_snap_to_tile = False
            input_controller = type("I", (), {"mouse_x": 0, "mouse_y": 0})()
            entity_select_state = EntitySelectState(selected_ids=[], primary_id="")

            @staticmethod
            def screen_to_world(x: float, y: float) -> tuple[float, float]:
                return (float(x), float(y))

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        # Add via Entity Paint (updates recent).
        assert input_capture.handle_mouse_press(controller, 1.0, 1.0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        capsys.readouterr()
        assert getattr(window, "prefab_recent", []) == ["slime_blob"]

        # Disable Entity Paint so entity-select duplicate can run.
        window.entity_paint_state.enabled = False

        # Add a second prefab manually and duplicate both.
        window.scene_controller.debug_add_entity_payload({"id": "b", "prefab_id": "crate", "x": 2.0, "y": 2.0})
        window.entity_select_state.selected_ids = ["b", "test_slime_blob_1_1_0_0"]
        window.entity_select_state.primary_id = "b"
        assert input_capture.handle_key_press(controller, arcade.key.D, arcade.key.MOD_CTRL) is True
        capsys.readouterr()
        assert getattr(window, "prefab_recent", [])[:2] == ["slime_blob", "crate"]

        # Paste a different prefab and ensure it becomes most recent.
        window.entity_clipboard = {
            "scene_path": "scenes/test.json",
            "primary_id": "p",
            "entities": [{"orig_id": "p", "prefab_id": "anvil_guard", "layer": "entities"}],
            "rel_offsets": {"p": {"dx": 0.0, "dy": 0.0}},
        }
        assert input_capture.handle_key_press(controller, arcade.key.V, arcade.key.MOD_CTRL) is True
        capsys.readouterr()
        assert getattr(window, "prefab_recent", [])[:3] == ["anvil_guard", "slime_blob", "crate"]
    finally:
        palette.enabled = original_enabled

