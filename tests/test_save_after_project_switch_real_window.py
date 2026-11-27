"""#721: in a developer launch with the legacy editor open, a main-menu project switch resets the game state (#716), but
the new project's start room only loads once the editor closes (the editor holds scene loads). A quicksave taken
meanwhile recorded the previous project's room objects in the new project's save. And if the editor had unsaved
changes and the creator picked Cancel, the start-room request was dropped and the previous room kept playing.

Now, until a room of the switched-to project loads, saving and loading are refused with a toast (the switch says so
too). The previous room's collected objects stay out of the fresh game's room memory (the reset began a new session,
which room memory already respects; pinned here).

Real (hidden) GameWindows, the current folder left at project A.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.action_runtime.registry import dispatch_action
from tests._game_window_live import dispose_game_window
from tests.test_quests_follow_project_switch_real_window import _project

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


def _press(window: Any, name: str) -> None:
    key = getattr(optional_arcade.arcade.key, name)
    window.dispatch_event("on_key_press", key, 0)
    window.dispatch_event("on_key_release", key, 0)


def _launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Path, Path]:
    """A developer launch on A with the legacy editor open (F4), A's crate collected in its room."""
    from engine.config import load_config
    from engine.game import GameWindow

    a, b = _project(tmp_path / "project_a", "a"), _project(tmp_path / "project_b", "b")
    monkeypatch.chdir(a)
    monkeypatch.delenv("MESH_SAVE_DIR", raising=False)
    monkeypatch.setenv("MESH_LEGACY_EDITOR", "1")
    config = load_config(str(a / "config.json"))
    config.tour_completed = True  # (a returning user: the first-launch tour takes Enter)
    window = GameWindow(width=320, height=200, title=config.title, vsync=False, config=config)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    window.load_scene("scenes/start.json")
    if window.main_menu_overlay.visible:
        window.main_menu_overlay.close()
    crate = next(s for s in window.scene_controller.all_sprites if getattr(s, "mesh_id", None) == "crate_a")
    crate.remove_from_sprite_lists()  # (collected in A's room: room memory would record it on leaving)
    _press(window, "F4")
    assert window.editor_controller.active is True
    return window, a, b


def _close(window: Any) -> None:
    from engine.editor.live_bridge_lifecycle import stop_live_bridge

    stop_live_bridge(window.editor_controller)
    dispose_game_window(window)


def _room_ids(window: Any) -> list[str]:
    return [e["id"] for e in window.scene_controller._loaded_scene_data["entities"]]


def _settle(window: Any) -> None:
    for _ in range(240):  # (a start room loads after its fade)
        window.on_update(1 / 60)
        if _room_ids(window) == ["crate_b"]:
            return


def _assert_refused_while_a_room_is_built(window: Any, b: Path) -> None:
    assert window.switch_room_pending is True and _room_ids(window) == ["crate_a"]
    _press(window, "F5")  # (the quicksave key: it has no editor gate)
    assert window.save_manager.save_game("quicksave") is False
    assert window.save_manager.load_game("quicksave") is False
    # (#723) the snapshot actions, invoked directly whichever hotkey system wins: nothing written, nothing loaded
    assert dispatch_action(window, "quick_save") and dispatch_action(window, "quick_load")
    assert window.switch_room_pending is True and _room_ids(window) == ["crate_a"]
    assert not (b / "saves" / "quicksave.json").exists() and not (b / "saves" / "quick.json").exists()
    assert not any("snapshot" in toast.lower() for toast in window.player_hud.active_toasts())  # (neither one ran)
    assert any("room hasn't loaded yet" in toast for toast in window.player_hud.active_toasts())


def _assert_saves_b_only(window: Any, b: Path) -> None:
    assert window.switch_room_pending is False and _room_ids(window) == ["crate_b"]
    assert window.save_manager.save_game("quicksave") is True
    saved = (b / "saves" / "quicksave.json").read_text(encoding="utf-8")
    assert "crate_a" not in saved and "crate_b" in saved
    assert "crate_a" not in json.dumps(window.game_state_controller.state.values)  # (no room memory of A's room)


def test_saving_waits_for_the_switched_to_projects_room(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _a, b = _launch(tmp_path, monkeypatch)
    try:
        window.main_menu_overlay._apply_project_root(str(b))
        assert any("loads when the editor closes" in toast for toast in window.player_hud.active_toasts())
        _assert_refused_while_a_room_is_built(window, b)
        _press(window, "F4")  # (the editor closes: B's start room loads)
        assert window.editor_controller.active is False
        _settle(window)
        _assert_saves_b_only(window, b)
    finally:
        _close(window)


def test_a_cancelled_start_room_keeps_saving_refused_until_a_room_of_the_project_loads(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window, _a, b = _launch(tmp_path, monkeypatch)
    editor = window.editor_controller
    try:
        editor.dirty_state.is_dirty = True  # (unsaved editor changes: the start room asks Save / Discard / Cancel)
        window.main_menu_overlay._apply_project_root(str(b))
        assert editor.unsaved_confirm.is_open is True
        _press(window, "ESCAPE")  # (Cancel: the start-room request is dropped)
        assert editor.unsaved_confirm.is_open is False
        _assert_refused_while_a_room_is_built(window, b)
        editor.dirty_state.is_dirty = False
        _press(window, "F4")
        _settle(window)
        _assert_refused_while_a_room_is_built(window, b)  # (still A's room: nothing loaded it away)
        window.main_menu_overlay._handle_start_game_impl()  # (New Game: B's start room)
        _settle(window)
        _assert_saves_b_only(window, b)
    finally:
        _close(window)
