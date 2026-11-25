"""#641, #631, #618: the legacy editor's file operations in a real (hidden) GameWindow, launched as ``mesh edit`` does,
with the current folder NOT the project.

The real window never had the ``repo_root`` the file operations read (only test fakes did), so in the real editor the
safe rename, move and delete returned False and did nothing, and the older ones resolved paths against the current
folder: Edit > Delete unlinked the current folder's same-named file. Edit > Delete and the palette's "Delete Selected"
also unlinked with no question and no trash. Now every operation acts in the project the Project panel shows, every
delete entry point asks first and keeps a copy in ``.mesh_trash``, and with no usable project root they refuse.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

HERO = "assets/sprites/hero.png"
VILLAIN = "assets/sprites/villain.png"


def _seed(root: Path, tag: str) -> None:
    (root / "assets" / "sprites").mkdir(parents=True)
    (root / "assets" / "other").mkdir()
    (root / HERO).write_bytes(f"{tag}-HERO".encode())
    (root / VILLAIN).write_bytes(f"{tag}-VILLAIN".encode())
    (root / "scenes").mkdir()
    (root / "scenes" / "level.json").write_text(json.dumps({"entities": [{"id": "h", "sprite": HERO}]}),
                                                encoding="utf-8")


def _files(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` by path, but the editor's own state (``.mesh/``: UI state, live session)."""
    out = {}
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".mesh"]
        for name in names:
            path = Path(dirpath) / name
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


@pytest.fixture()
def ed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """The legacy editor open on ``project/``, launched from ``launch/`` (the current folder), which holds files with
    the same names."""
    from engine.game import GameWindow

    launch, project = tmp_path / "launch", tmp_path / "project"
    _seed(launch, "LAUNCH")
    _seed(project, "PROJECT")
    monkeypatch.chdir(launch)
    monkeypatch.setenv("MESH_REPO_ROOT", str(project))  # (as a pinned launch or a main-menu project switch sets it)
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    room = tmp_path / "room.json"
    room.write_text(json.dumps({"name": "Room", "schema_version": 1, "version": 1, "layers": [], "entities": []}),
                    encoding="utf-8")
    cfg = EngineConfig(width=320, height=200, title="file ops", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    setattr(cfg, "_mesh_launch_mode", "editor")  # (as engine.game_launch does for ``mesh edit``)
    window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    window.load_scene(str(room))
    menu = getattr(window, "main_menu_overlay", None)
    if menu is not None and menu.visible:
        menu.close()
    _key(window, "F4")
    editor = window.editor_controller
    assert editor.active is True
    assert not hasattr(window, "repo_root")
    assert Path(editor.project_explorer.repo_root) == project.resolve()
    launch_before = _files(launch)
    try:
        yield SimpleNamespace(window=window, editor=editor, launch=launch, project=project, tmp=tmp_path)
        assert _files(launch) == launch_before, "a file operation changed the current folder's files"
    finally:
        from engine.editor.live_bridge_lifecycle import stop_live_bridge

        stop_live_bridge(editor)
        dispose_game_window(window)


def _key(window: Any, name: str) -> None:
    key = getattr(optional_arcade.arcade.key, name)
    window.dispatch_event("on_key_press", key, 0)
    window.dispatch_event("on_key_release", key, 0)


def _select(ed: Any, rel: str) -> None:
    editor = ed.editor
    assert editor.project_explorer_actions.reveal_path(rel)
    assert editor.project_explorer.selected_paths(editor._project_explorer_selectable_rows()) == [rel]


def _errors(ed: Any) -> list[str]:
    return [e.message for e in ed.editor.feedback.pending() if str(getattr(e.severity, "value", e.severity)) == "error"]


def _dialog_open(ed: Any) -> bool:
    return ed.editor.confirm_modal._on_confirm is not None


def _sprite(root: Path) -> str:
    return str(json.loads((root / "scenes" / "level.json").read_text(encoding="utf-8"))["entities"][0]["sprite"])


# --------------------------------------------------------------------------------------------------------- delete


@pytest.mark.parametrize("entry", ["edit_menu", "palette", "del_key"])
def test_every_delete_entry_point_asks_first_and_keeps_a_trash_copy(ed: Any, entry: str) -> None:
    from engine.editor.editor_actions import run_editor_action

    _select(ed, HERO)
    if entry == "edit_menu":
        assert run_editor_action("editor.delete", ed.editor, ed.window)
    elif entry == "palette":  # "Project Explorer: Delete Selected"
        assert run_editor_action("editor.project_explorer.delete_selected", ed.editor, ed.window)
    else:
        _key(ed.window, "DELETE")  # (the Project panel has focus: its tab is the open one)
    assert _dialog_open(ed), "deleted, or did nothing, without asking"
    assert (ed.project / HERO).read_bytes() == b"PROJECT-HERO"

    ed.editor.confirm_modal.execute_confirm()

    assert not (ed.project / HERO).exists()
    trash = {k: v for k, v in _files(ed.project).items() if k.startswith(".mesh_trash/")}
    assert list(trash.values()) == [b"PROJECT-HERO"], trash
    assert _sprite(ed.project) == ""  # (the scene's reference cleared with it)
    assert not _errors(ed)


def test_cancelling_the_delete_dialog_changes_nothing(ed: Any) -> None:
    before = _files(ed.project)
    _select(ed, HERO)
    ed.editor.run_editor_action("editor.delete")
    assert _dialog_open(ed)
    ed.editor.confirm_modal.execute_cancel()
    assert _files(ed.project) == before


# --------------------------------------------------------------------------------------------------- rename / move


def test_safe_rename_acts_in_the_project(ed: Any) -> None:
    _select(ed, HERO)
    assert ed.editor.file_ops.request_safe_rename_refactor("hero2.png") is True
    assert _dialog_open(ed)
    ed.editor.confirm_modal.execute_confirm()
    assert not (ed.project / HERO).exists()
    assert (ed.project / "assets/sprites/hero2.png").read_bytes() == b"PROJECT-HERO"
    assert _sprite(ed.project) == "assets/sprites/hero2.png"
    assert not _errors(ed)


def test_safe_move_acts_in_the_project(ed: Any) -> None:
    _select(ed, HERO)
    assert ed.editor.file_ops.request_safe_move_refactor("assets/other") is True
    assert _dialog_open(ed)
    ed.editor.confirm_modal.execute_confirm()
    assert not (ed.project / HERO).exists()
    assert (ed.project / "assets/other/hero.png").read_bytes() == b"PROJECT-HERO"
    assert _sprite(ed.project) == "assets/other/hero.png"
    assert not _errors(ed)


def test_the_older_rename_and_moves_act_in_the_project(ed: Any) -> None:
    editor = ed.editor
    _select(ed, HERO)
    assert editor.safe_rename_selected_asset("hero2.png") is True
    assert (ed.project / "assets/sprites/hero2.png").read_bytes() == b"PROJECT-HERO"
    _select(ed, "assets/sprites/hero2.png")
    assert editor.safe_move_selected_asset("assets/other") is True
    assert (ed.project / "assets/other/hero2.png").read_bytes() == b"PROJECT-HERO"
    _select(ed, VILLAIN)
    assert editor.project_explorer_actions.safe_move_selected_assets("assets/other") is True
    assert (ed.project / "assets/other/villain.png").read_bytes() == b"PROJECT-VILLAIN"
    assert not (ed.project / HERO).exists() and not (ed.project / VILLAIN).exists()


# ------------------------------------------------------------------------------------------------------- no root


def test_with_no_usable_project_root_every_operation_refuses(ed: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A main-menu project switch points the editor at another folder but the Project panel still lists the old one:
    its paths would name the other project's files, so nothing acts (and never the current folder)."""
    elsewhere = ed.tmp / "elsewhere"
    _seed(elsewhere, "ELSEWHERE")
    editor = ed.editor
    _select(ed, HERO)
    monkeypatch.setenv("MESH_REPO_ROOT", str(elsewhere))
    before = {root: _files(root) for root in (ed.project, elsewhere)}

    editor.run_editor_action("editor.delete")
    editor.run_editor_action("editor.project_explorer.delete_selected")
    assert editor.file_ops.request_safe_rename_refactor("hero2.png") is False
    assert editor.file_ops.request_safe_move_refactor("assets/other") is False
    assert editor.safe_rename_selected_asset("hero2.png") is False
    assert editor.safe_move_selected_asset("assets/other") is False
    assert editor.project_explorer_actions.safe_move_selected_assets("assets/other") is False

    assert not _dialog_open(ed)
    assert {root: _files(root) for root in before} == before
    assert any("File operation refused" in m for m in _errors(ed)), editor.feedback.pending()


def test_a_project_root_gone_while_the_dialog_is_open_refuses_at_confirm(ed: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    elsewhere = ed.tmp / "elsewhere"
    _seed(elsewhere, "ELSEWHERE")
    _select(ed, HERO)
    ed.editor.run_editor_action("editor.delete")
    assert _dialog_open(ed)
    monkeypatch.setenv("MESH_REPO_ROOT", str(elsewhere))
    before = {root: _files(root) for root in (ed.project, elsewhere)}
    ed.editor.confirm_modal.execute_confirm()
    assert {root: _files(root) for root in before} == before
    assert any("File operation refused" in m for m in _errors(ed))


# ------------------------------------------------------------------------------------------- #618 in the real editor


def test_618_rename_onto_an_existing_file_is_refused(ed: Any) -> None:
    before = _files(ed.project)
    _select(ed, HERO)
    assert ed.editor.file_ops.request_safe_rename_refactor("villain.png") is False
    assert not _dialog_open(ed)
    assert _files(ed.project) == before
    assert any("already exists" in m for m in _errors(ed))


def test_618_a_destination_made_while_the_dialog_is_open_is_never_overwritten(ed: Any) -> None:
    _select(ed, HERO)
    assert ed.editor.file_ops.request_safe_rename_refactor("hero2.png") is True
    (ed.project / "assets/sprites/hero2.png").write_bytes(b"MADE-MEANWHILE")
    before = _files(ed.project)
    ed.editor.confirm_modal.execute_confirm()
    assert _files(ed.project) == before
    assert _sprite(ed.project) == HERO
    assert any("already exists" in m for m in _errors(ed))


def test_618_move_into_a_folder_holding_a_same_named_file_is_refused(ed: Any) -> None:
    (ed.project / "assets/other/hero.png").write_bytes(b"OTHER-HERO")
    before = _files(ed.project)
    _select(ed, HERO)
    assert ed.editor.file_ops.request_safe_move_refactor("assets/other") is False
    assert ed.editor.safe_move_selected_asset("assets/other") is False
    assert not _dialog_open(ed)
    assert _files(ed.project) == before
    assert any("already exists" in m for m in _errors(ed))
