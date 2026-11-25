"""#660: F4 in a game launch never opens the legacy editor, through the real key path of a real (hidden) GameWindow.

#347 put the legacy editor off a game's path, but only on the action-registry route, which no key uses: a plain F4
reached ``EditorModeController.toggle`` from ``input_dispatch`` (and from the key router's shadowed route) unchecked,
so a player of an exported game could open the editor and Edit > Delete the game's own files. ``toggle`` now asks
``legacy_editor_allowed`` itself, so every route is refused in a game launch; an editor launch, MESH_LEGACY_EDITOR=1,
and leaving an open editor are kept.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

VICTIM = "assets/data/precious.json"


def _window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launch_mode: str | None) -> Any:
    from engine.game import GameWindow

    monkeypatch.chdir(tmp_path)  # (a game runs in its own folder; the editor would list and delete files there)
    (tmp_path / VICTIM).parent.mkdir(parents=True)
    (tmp_path / VICTIM).write_text("{}", encoding="utf-8")
    room = tmp_path / "room.json"
    room.write_text(json.dumps({"name": "Room", "schema_version": 1, "version": 1, "layers": [], "entities": []}),
                    encoding="utf-8")
    cfg = EngineConfig(width=320, height=200, title="F4 gate", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    if launch_mode is not None:
        setattr(cfg, "_mesh_launch_mode", launch_mode)  # (as engine.game_launch does for ``mesh edit``)
    window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    window.editor_controller._repo_root_override = tmp_path  # (the editor lists, and would delete, this game's files)
    window.editor_controller.project_explorer.set_repo_root(tmp_path)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    window.scene_controller.load_scene(str(room))
    return window


@pytest.fixture()
def game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """A game launch: ``main.py`` or an exported game, no launch mode, no MESH_LEGACY_EDITOR."""
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    window = _window(tmp_path, monkeypatch, None)
    try:
        yield window
    finally:
        _close(window)


def _close(window: Any) -> None:
    from engine.editor.live_bridge_lifecycle import stop_live_bridge

    stop_live_bridge(window.editor_controller)
    dispose_game_window(window)


def _f4(window: Any) -> None:
    key = optional_arcade.arcade.key
    window.dispatch_event("on_key_press", key.F4, 0)
    window.dispatch_event("on_key_release", key.F4, 0)


def _assert_refused(window: Any, root: Path) -> None:
    editor = window.editor_controller
    assert editor.active is False
    assert editor.live_bridge is None
    assert not (root / ".mesh" / "live_session.json").exists()
    assert not window.paused


def test_f4_in_a_game_launch_leaves_the_legacy_editor_closed(game: Any, tmp_path: Path) -> None:
    _f4(game)
    _assert_refused(game, tmp_path)
    _f4(game)  # (again: still nothing)
    _assert_refused(game, tmp_path)


def test_the_key_routers_f4_route_alone_opens_nothing_in_a_game(game: Any, tmp_path: Path) -> None:
    from engine.input_runtime import capture_key_router
    from engine.input_runtime.capture_focus_query import get_capture_focus_snapshot
    from engine.input_runtime.capture_key_router_handlers_global import dispatch_global_action

    key, controller = optional_arcade.arcade.key, game.input_controller
    snapshot = get_capture_focus_snapshot(controller, 0)
    capture_key_router.route_and_dispatch(controller, key.F4, 0, snapshot)
    _assert_refused(game, tmp_path)
    # The route's own handler, reached directly (the router sends "capture.editor.*" to the editor handlers, which
    # don't know it, and input_dispatch takes a plain F4 first): it calls the same gated toggle.
    assert dispatch_global_action(controller, snapshot, "capture.editor.toggle") is True
    _assert_refused(game, tmp_path)


def test_f4_then_edit_delete_in_a_game_launch_deletes_nothing(game: Any, tmp_path: Path) -> None:
    _f4(game)
    editor = game.editor_controller
    # Selected as the Project explorer would (a player can't reach it: the editor stays closed), then Edit > Delete.
    assert editor.project_explorer_actions.reveal_path(VICTIM)
    assert editor.project_explorer.selected_paths(editor._project_explorer_selectable_rows()) == [VICTIM]
    editor.run_editor_action("editor.delete")
    assert (tmp_path / VICTIM).is_file()
    _assert_refused(game, tmp_path)


def test_f4_opens_the_legacy_editor_in_an_editor_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    window = _window(tmp_path, monkeypatch, "editor")  # ``mesh edit`` on a project without a world
    try:
        _f4(window)
        assert window.editor_controller.active is True and window.paused
    finally:
        _close(window)


def test_f4_opens_the_legacy_editor_with_mesh_legacy_editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_LEGACY_EDITOR", "1")
    window = _window(tmp_path, monkeypatch, None)
    try:
        _f4(window)
        assert window.editor_controller.active is True
    finally:
        _close(window)


def test_f4_closes_an_open_legacy_editor_in_a_game_launch(game: Any, tmp_path: Path) -> None:
    editor = game.editor_controller
    editor._enable_editor_mode()  # (opened as an editor launch does; the game launch itself never allows F4 to)
    assert editor.active is True
    _f4(game)
    _assert_refused(game, tmp_path)  # closed, its live session gone, the game unpaused
