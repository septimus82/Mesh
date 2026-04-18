from __future__ import annotations

import copy
import json

import engine.optional_arcade as optional_arcade
from tests._command_palette_window_stub import CommandPaletteWindowStub, as_game_window


def test_macro_preview_objective_zone_does_not_mutate_and_counts_stable() -> None:
    from engine.scene_controller import SceneController

    window = CommandPaletteWindowStub()
    sc = SceneController(as_game_window(window))
    sc.current_scene_path = "scenes/foo.json"
    sc._loaded_scene_source_data = {
        "entities": [
            {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0},
            {"id": "other", "prefab_id": "crate", "x": 99.0, "y": 99.0},
        ]
    }

    before = copy.deepcopy(sc.get_authored_scene_payload())
    preview = sc.debug_preview_macro_objective_zone(
        center_x=10.0,
        center_y=20.0,
        zone_id="MyZone",
        set_flag="demo.reached_mid",
        radius=24.0,
        toast=None,
    )
    after = sc.get_authored_scene_payload()
    assert after == before

    assert preview == {
        "will_create": 2,
        "will_update": 0,
        "create_ids": [
            "foo_macro_setflag_demo_reached_mid_MyZone_10_20_0_0",
            "foo_macro_triggerzone_MyZone_10_20_0_0",
        ],
        "update_ids": [],
    }


def test_macro_anchor_primary_option_only_when_selection_exists() -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState

    class _SC:
        current_scene_path = "scenes/foo.json"

        @staticmethod
        def get_authored_scene_payload() -> dict:
            return {"entities": [{"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0}]}

    window = type("W", (), {"scene_controller": _SC(), "entity_select_state": EntitySelectState(selected_ids=[], primary_id=None)})()
    cmd = next(c for c in build_default_commands(window) if c.id == "macro.objective_zone")
    anchor_step = cmd.prompts[0]
    options = anchor_step.options_provider(window) if callable(anchor_step.options_provider) else []
    assert [v for v, _lbl in options] == ["cursor", "player"]

    window.entity_select_state = EntitySelectState(selected_ids=["player"], primary_id="player")
    cmd = next(c for c in build_default_commands(window) if c.id == "macro.objective_zone")
    anchor_step = cmd.prompts[0]
    options = anchor_step.options_provider(window) if callable(anchor_step.options_provider) else []
    assert [v for v, _lbl in options] == ["primary", "cursor", "player"]


def test_command_palette_ctrl_enter_repeats_last_macro_and_is_idempotent(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = CommandPaletteWindowStub(
            command_palette_enabled=True,
            command_palette_query="objective zone",
            command_palette_index=0,
            command_palette_prompt_active=False,
            last_macro_args={
                "macro.objective_zone": {
                    "anchor": "cursor",
                    "zone_id": "MyZone",
                    "set_flag": "demo.reached_mid",
                    "radius": 24.0,
                    "toast": "",
                }
            },
        )
        window.input_controller.mouse_x = 5.0
        window.input_controller.mouse_y = 6.0
        window.screen_to_world = lambda _x, _y: (10.0, 20.0)

        sc = SceneController(as_game_window(window))
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0},
            ]
        }
        window.scene_controller = sc

        class _Mgr:
            def press(self, *_a):  # pragma: no cover
                raise AssertionError("should not dispatch gameplay input")

        controller = type("Ctl", (), {"window": window, "manager": _Mgr(), "_keys": set()})()

        capsys.readouterr()
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
        out = capsys.readouterr().out.strip()
        assert out == "AUTHOR_MACRO ok action=objective_zone created=2 updated=0"
        assert len(window.undo_stack) == 1

        authored = sc.get_authored_scene_payload()
        ids = sorted([e.get("id") for e in authored.get("entities", []) if isinstance(e, dict) and isinstance(e.get("id"), str)])
        assert "foo_macro_triggerzone_MyZone_10_20_0_0" in ids
        assert "foo_macro_setflag_demo_reached_mid_MyZone_10_20_0_0" in ids

        # Repeat is idempotent.
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
        out = capsys.readouterr().out.strip()
        assert out == "AUTHOR_MACRO noop reason=no_changes"
        assert len(window.undo_stack) == 1

        window.undo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        ids = [e.get("id") for e in authored.get("entities", []) if isinstance(e, dict)]
        assert "foo_macro_triggerzone_MyZone_10_20_0_0" not in ids

        window.redo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        ids = [e.get("id") for e in authored.get("entities", []) if isinstance(e, dict)]
        assert "foo_macro_triggerzone_MyZone_10_20_0_0" in ids
    finally:
        palette.enabled = original_enabled


def test_command_palette_ctrl_enter_macro_no_last_args_prints_reason(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = CommandPaletteWindowStub(
            command_palette_enabled=True,
            command_palette_query="objective zone",
            command_palette_index=0,
            command_palette_prompt_active=False,
            last_macro_args={},
            scene_controller=type("SC", (), {"current_scene_path": "scenes/foo.json", "get_authored_scene_payload": lambda *_a: {"entities": []}})(),
        )

        class _Mgr:
            def press(self, *_a):  # pragma: no cover
                raise AssertionError("should not dispatch gameplay input")

        controller = type("Ctl", (), {"window": window, "manager": _Mgr(), "_keys": set()})()
        capsys.readouterr()
        assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO noop reason=no_last_args"
    finally:
        palette.enabled = original_enabled


def test_command_palette_overlay_renders_preview_line() -> None:
    from engine.ui import format_command_palette_overlay_lines

    payload = {
        "enabled": True,
        "query": "macro",
        "dirty": False,
        "rev": 1,
        "armed": False,
        "undo": 0,
        "redo": 0,
        "active_mode": "none",
        "prompt_active": False,
        "preview_line": "PREVIEW create=2 update=0 (first ids: a,b,c)",
        "rows": [
            {"kind": "section", "title": "Authoring / Macros"},
            {
                "kind": "command",
                "id": "m",
                "title": "Macro",
                "hotkey_hint": "",
                "enabled": True,
                "disabled_reason": "",
            },
        ],
        "selected_row": 0,
    }
    lines = format_command_palette_overlay_lines(payload)
    assert lines[1] == "PREVIEW create=2 update=0 (first ids: a,b,c)"

