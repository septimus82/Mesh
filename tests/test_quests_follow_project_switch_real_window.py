"""#675 item 3: the main menu's project switch moved the saves, cutscenes and items to the new project (#623), but the
quest manager kept the previous project's quest definitions (read once, from an absolute path, when the window was
made). Those kept driving the quest state, which was then saved into the new project's saves. Now the switch reads
the new project's quests again; the previous project's quest state goes with them.

A real (hidden) GameWindow in a developer launch (MESH_LEGACY_EDITOR=1; with the editor open the main menu switches projects), with the current
folder left at the first project throughout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


def _project(root: Path, tag: str) -> Path:
    (root / "scenes").mkdir(parents=True)
    (root / "assets" / "data").mkdir(parents=True)
    config = {"title": f"Game {tag}", "game_id": f"game-{tag}-0000", "start_scene": "scenes/start.json",
              "width": 320, "height": 200, "vsync": False, "fullscreen": False, "main_menu_scene": None}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "scenes" / "start.json").write_text(json.dumps(
        {"name": "Start", "schema_version": 1, "version": 1, "layers": [], "entities": []}), encoding="utf-8")
    (root / "assets" / "data" / "quests.json").write_text(json.dumps({"quests": [
        {"id": f"quest_{tag}", "title": f"Quest {tag}", "stages": [{"id": "first", "title": "First"}]}]}),
        encoding="utf-8")
    return root.resolve()


def test_a_main_menu_project_switch_reads_the_new_projects_quests(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.config import load_config
    from engine.game import GameWindow

    a, b = _project(tmp_path / "project_a", "a"), _project(tmp_path / "project_b", "b")
    monkeypatch.chdir(a)  # (as after ``mesh edit A``; it stays here)
    monkeypatch.delenv("MESH_SAVE_DIR", raising=False)
    config = load_config(str(a / "config.json"))
    monkeypatch.setenv("MESH_LEGACY_EDITOR", "1")  # (a developer launch: F4 opens the editor, whose menu may switch)
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
        quests = window.quest_manager
        assert {q.id for q in quests.get_all_quests()} == {"quest_a"}
        assert quests.start_quest("quest_a") is True

        window.main_menu_overlay._apply_project_root(str(b))
        assert Path(window.engine_config._config_base_dir).resolve() == b
        assert window.quest_manager is quests and window.game_state_controller.quests is quests
        assert {q.id for q in quests.get_all_quests()} == {"quest_b"}
        assert "quest_a" not in window.game_state_controller.state.values.get("quests", {})
        assert quests.start_quest("quest_b") is True

        assert window.save_manager.save_game("quicksave")
        saved = (b / "saves" / "quicksave.json").read_text(encoding="utf-8")
        assert "quest_b" in saved and "quest_a" not in saved, "A's quests were saved into B's game"
        assert not (a / "saves" / "quicksave.json").exists()
    finally:
        from engine.editor.live_bridge_lifecycle import stop_live_bridge

        stop_live_bridge(window.editor_controller)
        dispose_game_window(window)
