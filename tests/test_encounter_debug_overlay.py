from __future__ import annotations

import arcade


def test_format_encounter_debug_text_is_stable() -> None:
    from engine.ui import format_encounter_debug_text

    payload = {
        "scene_path": "scenes/x.json",
        "difficulty": "easy",
        "encounter_preset_id": "easy",
        "encounter_budget": 8.0,
        "boss_budget_reserve": 1.5,
        "elite_cap": None,
        "mini_boss_cap": None,
        "allow_elites": True,
        "allow_mini_bosses": None,
        "spawn_count": 3,
        "elite_count": 1,
        "mini_boss_count": 0,
        "total_spawn_cost": 12.34,
        "elite_cost_share": 0.25,
        "mini_boss_cost_share": 0.75,
    }

    text = format_encounter_debug_text(payload)
    assert "scene: scenes/x.json" in text
    assert "difficulty: easy preset: easy" in text
    assert "budget: 8.00 reserve: 1.50" in text
    assert "caps elite=- mini=->elite" in text
    assert "allow elites=Y mini=->elites" in text
    assert "spawns=3 elite=1 mini=0" in text
    assert "cost=12.34 shares elite=0.2500 mini=0.7500" in text


def test_encounter_debug_overlay_toggle_key() -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    class _Overlay:
        visible = False

        def toggle(self) -> bool:
            self.visible = not self.visible
            return self.visible

    overlay = _Overlay()

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        encounter_debug_overlay = overlay

    controller = type("C", (), {"window": _Window()})()

    assert input_capture.handle_key_press(controller, arcade.key.F8, 0) is True
    assert overlay.visible is True
    assert input_capture.handle_key_press(controller, arcade.key.F8, 0) is True
    assert overlay.visible is False
