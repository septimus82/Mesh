"""#675: a main-menu project switch starts the new project's game afresh.

Item 3: the switch moved the saves, cutscenes and items to the new project (#623), but the quest manager kept the
previous project's quest definitions (read once, from an absolute path, when the window was made). Those kept driving
the quest state, which was then saved into the new project's saves. Now the switch reads the new project's quests.

#716's review: the switch also kept the whole game state, so project A's flags, values, inventory, room memory and
progress on a quest id both projects define (template-made projects share ids) went into B's quicksave. The switch now
resets the session as New Game does.

A real (hidden) GameWindow in a developer launch (MESH_LEGACY_EDITOR=1; with the editor open the main menu switches
projects), with the current folder left at the first project throughout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

SHARED = "quest_shared"  # (both projects define it, as projects made from one template do)


def _project(root: Path, tag: str) -> Path:
    (root / "scenes").mkdir(parents=True)
    (root / "assets" / "data").mkdir(parents=True)
    config = {"title": f"Game {tag}", "game_id": f"game-{tag}-0000", "start_scene": "scenes/start.json",
              "width": 320, "height": 200, "vsync": False, "fullscreen": False, "main_menu_scene": None}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "scenes" / "start.json").write_text(json.dumps(
        {"name": "Start", "schema_version": 1, "version": 1, "layers": [],
         "entities": [{"id": f"crate_{tag}", "x": 32.0, "y": 32.0}]}), encoding="utf-8")
    (root / "assets" / "data" / "quests.json").write_text(json.dumps({"quests": [
        {"id": f"quest_{tag}", "title": f"Quest {tag}", "stages": [{"id": "first", "title": "First"}]},
        {"id": SHARED, "title": f"Shared ({tag})", "stages": [{"id": "first", "title": "First"},
                                                             {"id": "second", "title": "Second"}]}]}),
        encoding="utf-8")
    (root / "assets" / "data" / "items.json").write_text(json.dumps(
        {"items": [{"id": f"gem_{tag}", "name": f"Gem {tag}"}]}), encoding="utf-8")
    return root.resolve()


def test_a_main_menu_project_switch_starts_the_new_projects_game_afresh(tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.config import load_config
    from engine.game import GameWindow
    from engine.inventory import get_or_create_inventory

    a, b = _project(tmp_path / "project_a", "a"), _project(tmp_path / "project_b", "b")
    monkeypatch.chdir(a)  # (as after ``mesh edit A``; it stays here)
    monkeypatch.delenv("MESH_SAVE_DIR", raising=False)
    monkeypatch.setenv("MESH_LEGACY_EDITOR", "1")  # (a developer launch: F4 opens the editor, whose menu may switch)
    config = load_config(str(a / "config.json"))
    config.tour_completed = True  # (a returning user: the first-launch tour takes Enter)
    window = GameWindow(width=320, height=200, title=config.title, vsync=False, config=config)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    try:
        window.load_scene("scenes/start.json")
        if window.main_menu_overlay.visible:
            window.main_menu_overlay.close()
        key = optional_arcade.arcade.key
        window.dispatch_event("on_key_press", key.F4, 0)
        window.dispatch_event("on_key_release", key.F4, 0)
        assert window.editor_controller.active is True
        state = window.game_state_controller
        quests = window.quest_manager
        assert {q.id for q in quests.get_all_quests()} == {"quest_a", SHARED}

        # Progress in A: quests, a flag, a value, an item, a room memory entry
        assert quests.start_quest("quest_a") is True
        assert quests.start_quest(SHARED) is True and quests.complete_stage(SHARED, "first") is True
        state.set_flag("flag_from_a", True)
        state.set_var("value_from_a", 7)
        state.set_var("room_memory", {"scenes/start.json": {"removed": ["coin_from_a"]}})
        assert get_or_create_inventory(state.state.values).add_item("gem_a") is True
        a_marks = ("quest_a", "flag_from_a", "value_from_a", "coin_from_a", "gem_a", "crate_a")

        window.main_menu_overlay._apply_project_root(str(b))
        assert Path(window.engine_config._config_base_dir).resolve() == b
        assert window.quest_manager is quests and window.game_state_controller.quests is quests
        assert {q.id for q in quests.get_all_quests()} == {"quest_b", SHARED}
        window.dispatch_event("on_key_press", key.F4, 0)  # (back to the game: the editor holds scene loads)
        window.dispatch_event("on_key_release", key.F4, 0)
        assert window.editor_controller.active is False
        for _ in range(240):  # (the switch asks for B's start room, as New Game does; it loads after its fade)
            window.on_update(1 / 60)
            room = window.scene_controller._loaded_scene_data
            if [e["id"] for e in room["entities"]] != ["crate_a"]:
                break
        assert [e["id"] for e in room["entities"]] == ["crate_b"], "A's room is still the one loaded"
        values =window.game_state_controller.state.values
        left = [mark for mark in a_marks if mark in json.dumps(values, default=str)]
        assert left == [], f"A's state survived the switch: {left}"
        assert "flag_from_a" not in window.game_state_controller.state.flags
        # B's quest starts fresh, as in a new game (these quests start themselves at their first stage)
        assert quests.get_state_snapshot(SHARED) == quests.get_state_snapshot("quest_b")
        assert not quests.is_stage_completed(SHARED, "first") and quests.get_current_stage(SHARED)["id"] == "first"

        assert window.save_manager.save_game("quicksave")
        saved = (b / "saves" / "quicksave.json").read_text(encoding="utf-8")
        leaked = [mark for mark in a_marks if mark in saved]
        assert leaked == [], f"A's state was saved into B's game: {leaked}"
        assert SHARED in saved and not (a / "saves" / "quicksave.json").exists()
    finally:
        from engine.editor.live_bridge_lifecycle import stop_live_bridge

        stop_live_bridge(window.editor_controller)
        dispose_game_window(window)
