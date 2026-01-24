from __future__ import annotations

import json


def test_authoring_macro_objective_zone_idempotent_and_undo_redo(capsys) -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState
    from engine.game import GameWindow
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "scene_dirty": False,
                "scene_dirty_reason": "",
                "scene_dirty_counter": 0,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
            },
        )()

        def _mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter = int(getattr(self, "scene_dirty_counter", 0) or 0) + 1

        window.mark_scene_dirty = _mark_scene_dirty.__get__(window)  # type: ignore[attr-defined]
        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]
        window.undo = lambda: GameWindow.undo(window)  # type: ignore[attr-defined]
        window.redo = lambda: GameWindow.redo(window)  # type: ignore[attr-defined]

        sc = SceneController(window)  # type: ignore[arg-type]
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0},
                {"id": "anchor", "prefab_id": "crate", "x": 10.0, "y": 20.0},
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["anchor"], primary_id="anchor")

        cmd = next(c for c in build_default_commands(window) if c.id == "macro.objective_zone")
        arg = json.dumps(
            {"anchor": "primary", "zone_id": "MyZone", "set_flag": "demo.reached_mid", "radius": "24", "toast": ""},
            sort_keys=True,
        )

        capsys.readouterr()
        cmd.action(window, arg)
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO ok action=objective_zone created=2 updated=0"
        assert len(window.undo_stack) == 1

        authored = sc.get_authored_scene_payload()
        trigger_id = "foo_macro_triggerzone_MyZone_10_20_0_0"
        hook_id = "foo_macro_setflag_demo_reached_mid_MyZone_10_20_0_0"
        trigger = next(e for e in authored["entities"] if e["id"] == trigger_id)
        hook = next(e for e in authored["entities"] if e["id"] == hook_id)
        assert "TriggerZone" in (trigger.get("behaviours") or [])
        assert trigger["name"] == "MyZone"
        assert trigger["behaviour_config"]["TriggerZone"]["trigger_target"] == "Player"
        assert trigger["behaviour_config"]["TriggerZone"]["trigger_radius"] == 24.0
        assert trigger["behaviour_config"]["TriggerZone"]["zone_id"] == "MyZone"

        assert "SetGameStateOnEvent" in (hook.get("behaviours") or [])
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["event_type"] == "entered_zone"
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["payload_field"] == "zone"
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["payload_value"] == "MyZone"
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["once"] is True
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["set_flags"]["demo.reached_mid"] is True

        # Idempotent re-run.
        cmd.action(window, arg)
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO noop reason=no_changes"
        assert len(window.undo_stack) == 1

        window.undo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        assert not any(e.get("id") in (trigger_id, hook_id) for e in authored.get("entities", []))

        window.redo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        assert any(e.get("id") == trigger_id for e in authored.get("entities", []))
        assert any(e.get("id") == hook_id for e in authored.get("entities", []))
    finally:
        palette.enabled = original_enabled


def test_authoring_macro_door_transition_patches_selected_transition_and_undo_redo(capsys) -> None:
    from engine.command_palette import build_default_commands
    from engine.entity_select_mode import EntitySelectState
    from engine.game import GameWindow
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "scene_dirty": False,
                "scene_dirty_reason": "",
                "scene_dirty_counter": 0,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
            },
        )()

        def _mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter = int(getattr(self, "scene_dirty_counter", 0) or 0) + 1

        window.mark_scene_dirty = _mark_scene_dirty.__get__(window)  # type: ignore[attr-defined]
        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]
        window.undo = lambda: GameWindow.undo(window)  # type: ignore[attr-defined]
        window.redo = lambda: GameWindow.redo(window)  # type: ignore[attr-defined]

        sc = SceneController(window)  # type: ignore[arg-type]
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 100.0, "y": 200.0},
                {
                    "id": "door",
                    "prefab_id": "door",
                    "x": 1.0,
                    "y": 2.0,
                    "behaviours": ["SceneTransition"],
                    "behaviour_config": {"SceneTransition": {"target_scene": "scenes/old.json", "spawn_id": "old"}},
                },
            ]
        }
        window.scene_controller = sc
        window.entity_select_state = EntitySelectState(selected_ids=["door"], primary_id="door")

        cmd = next(c for c in build_default_commands(window) if c.id == "macro.door_transition")
        arg = json.dumps({"target_scene": "scenes/bar.json", "spawn_id": "entry"}, sort_keys=True)

        capsys.readouterr()
        cmd.action(window, arg)
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO ok action=door_transition created=0 updated=1"
        assert len(window.undo_stack) == 1

        authored = sc.get_authored_scene_payload()
        door = next(e for e in authored["entities"] if e["id"] == "door")
        assert door["behaviour_config"]["SceneTransition"]["target_scene"] == "scenes/bar.json"
        assert door["behaviour_config"]["SceneTransition"]["spawn_id"] == "entry"

        cmd.action(window, arg)
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO noop reason=no_changes"
        assert len(window.undo_stack) == 1

        window.undo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        door = next(e for e in authored["entities"] if e["id"] == "door")
        assert door["behaviour_config"]["SceneTransition"]["target_scene"] == "scenes/old.json"
        assert door["behaviour_config"]["SceneTransition"]["spawn_id"] == "old"

        window.redo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        door = next(e for e in authored["entities"] if e["id"] == "door")
        assert door["behaviour_config"]["SceneTransition"]["target_scene"] == "scenes/bar.json"
        assert door["behaviour_config"]["SceneTransition"]["spawn_id"] == "entry"
    finally:
        palette.enabled = original_enabled


def test_authoring_macro_dialogue_choice_flag_idempotent_and_undo_redo(capsys) -> None:
    from engine.command_palette import build_default_commands
    from engine.game import GameWindow
    from engine.palette_mode import get_state
    from engine.scene_controller import SceneController

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "scene_dirty": False,
                "scene_dirty_reason": "",
                "scene_dirty_counter": 0,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
            },
        )()

        def _mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter = int(getattr(self, "scene_dirty_counter", 0) or 0) + 1

        window.mark_scene_dirty = _mark_scene_dirty.__get__(window)  # type: ignore[attr-defined]
        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]
        window.undo = lambda: GameWindow.undo(window)  # type: ignore[attr-defined]
        window.redo = lambda: GameWindow.redo(window)  # type: ignore[attr-defined]

        sc = SceneController(window)  # type: ignore[arg-type]
        sc.current_scene_path = "scenes/foo.json"
        sc._loaded_scene_source_data = {
            "entities": [
                {"id": "player", "prefab_id": "player", "tags": ["player"], "x": 0.0, "y": 0.0},
                {
                    "id": "speaker",
                    "prefab_id": "npc",
                    "x": 1.0,
                    "y": 2.0,
                    "behaviours": ["Dialogue"],
                    "behaviour_config": {
                        "Dialogue": {"dialogue": {"nodes": {"root": {"text": "hi", "choices": []}}, "start": "root", "speaker": ""}}
                    },
                },
            ]
        }
        window.scene_controller = sc

        cmd = next(c for c in build_default_commands(window) if c.id == "macro.dialogue_choice_flag")
        arg = json.dumps(
            {
                "speaker_id": "speaker",
                "choice_id": "accept",
                "choice_text": "Sure.",
                "set_flag": "demo.started",
                "toast": "",
            },
            sort_keys=True,
        )

        capsys.readouterr()
        cmd.action(window, arg)
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO ok action=dialogue_choice_flag created=1 updated=1"
        assert len(window.undo_stack) == 1

        authored = sc.get_authored_scene_payload()
        speaker = next(e for e in authored["entities"] if e["id"] == "speaker")
        choices = speaker["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["choices"]
        assert any(isinstance(c, dict) and c.get("id") == "accept" and c.get("text") == "Sure." for c in choices)

        hook_id = "foo_macro_choiceflag_demo_started_accept_0_0"
        hook = next(e for e in authored["entities"] if e["id"] == hook_id)
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["event_type"] == "dialogue_choice"
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["payload_field"] == "choice_id"
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["payload_value"] == "accept"
        assert hook["behaviour_config"]["SetGameStateOnEvent"]["set_flags"]["demo.started"] is True

        cmd.action(window, arg)
        assert capsys.readouterr().out.strip() == "AUTHOR_MACRO noop reason=no_changes"
        assert len(window.undo_stack) == 1

        window.undo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        assert not any(e.get("id") == hook_id for e in authored.get("entities", []))
        speaker = next(e for e in authored["entities"] if e["id"] == "speaker")
        choices = speaker["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["choices"]
        assert not any(isinstance(c, dict) and c.get("id") == "accept" for c in choices)

        window.redo()
        capsys.readouterr()
        authored = sc.get_authored_scene_payload()
        assert any(e.get("id") == hook_id for e in authored.get("entities", []))
        speaker = next(e for e in authored["entities"] if e["id"] == "speaker")
        choices = speaker["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["choices"]
        assert any(isinstance(c, dict) and c.get("id") == "accept" for c in choices)
    finally:
        palette.enabled = original_enabled
