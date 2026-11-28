"""#641, #631, #618: the legacy editor's file operations in a real (hidden) GameWindow, launched as ``mesh edit`` does,
with the current folder NOT the project.

The real window never had the ``repo_root`` the file operations read (only test fakes did), so in the real editor the
safe rename, move and delete returned False and did nothing, and the older ones resolved paths against the current
folder: Edit > Delete unlinked the current folder's same-named file. Edit > Delete and the palette's "Delete Selected"
also unlinked with no question and no trash. Now every operation acts in the project the Project panel shows, every
delete entry point asks first and keeps a copy in ``.mesh_trash``, and with no usable project root they refuse.

#632: every delete stages into its own trash folder, so deleting a re-created file again keeps both copies, and the
reference scan skips ``.mesh_trash``. #670: an inline rename (F2, typed name, Return) commits through the safe rename
on both Return routes.
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
                       main_menu_scene=None, tour_completed=True)  # (a returning user: the tour takes Enter)
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


def _scene_reference_in_memory(ed: Any) -> dict[str, Any]:
    """The open scene holds a reference into assets/sprites, as an edited scene would (the folder delete rewrote it
    to "/hero.png" before it was refused: #668 review)."""
    scene = ed.window.scene_controller._loaded_scene_data
    scene["entities"].append({"id": "ref", "sprite": HERO})
    return scene


@pytest.mark.parametrize("entry", ["edit_menu", "palette", "del_key"])
def test_deleting_a_folder_is_refused_at_every_entry_point(ed: Any, entry: str) -> None:
    import copy

    from engine.editor.editor_actions import run_editor_action

    scene = _scene_reference_in_memory(ed)
    scene_before, files_before = copy.deepcopy(scene), _files(ed.project)
    _select(ed, "assets/sprites")
    if entry == "edit_menu":
        run_editor_action("editor.delete", ed.editor, ed.window)
    elif entry == "palette":
        run_editor_action("editor.project_explorer.delete_selected", ed.editor, ed.window)
    else:
        _key(ed.window, "DELETE")
    assert not _dialog_open(ed)
    assert _files(ed.project) == files_before
    assert ed.window.scene_controller._loaded_scene_data == scene_before
    assert any("Deleting folders isn't supported here" in m for m in _errors(ed)), ed.editor.feedback.pending()


def test_a_selection_mixing_files_and_a_folder_is_refused_whole(ed: Any) -> None:
    import copy

    (ed.project / "assets/other/box.png").write_bytes(b"PROJECT-BOX")
    scene = _scene_reference_in_memory(ed)
    scene_before, files_before = copy.deepcopy(scene), _files(ed.project)
    _select(ed, HERO)
    ed.editor.project_explorer._toggle_selection_by_path("assets/other")
    editor = ed.editor
    assert sorted(editor.project_explorer.selected_paths(editor._project_explorer_selectable_rows())) == [
        "assets/other", HERO]
    editor.run_editor_action("editor.delete")
    assert not _dialog_open(ed)
    assert _files(ed.project) == files_before
    assert ed.window.scene_controller._loaded_scene_data == scene_before
    assert any("Deleting folders isn't supported here" in m for m in _errors(ed))


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


# ------------------------------------------------------------------------------------------ #632 unique trash entries


def _trash(root: Path) -> dict[str, bytes]:
    return {k: v for k, v in _files(root).items() if k.startswith(".mesh_trash/")}


def _confirm_delete(ed: Any, rel: str) -> str:
    """Delete ``rel`` through Edit > Delete and Confirm; the plan's op_id."""
    _select(ed, rel)
    ed.editor.run_editor_action("editor.delete")
    assert _dialog_open(ed)
    op_id = ed.editor.file_ops._pending_refactor_plan.op_id
    ed.editor.confirm_modal.execute_confirm()
    return str(op_id)


def test_632_delete_recreate_delete_keeps_both_trash_copies(ed: Any) -> None:
    first = _confirm_delete(ed, VILLAIN)
    (ed.project / VILLAIN).write_bytes(b"VILLAIN-2")
    ed.editor.project_explorer.refresh_tree()  # (the panel lists the re-created file)
    second = _confirm_delete(ed, VILLAIN)

    assert first == second  # (the same plan: the deterministic trash path collided here)
    assert not (ed.project / VILLAIN).exists()
    trash = _trash(ed.project)
    assert sorted(trash.values()) == [b"PROJECT-VILLAIN", b"VILLAIN-2"], trash
    assert all(k.endswith("/" + VILLAIN) for k in trash)
    assert not _errors(ed)


def test_632_a_later_rename_never_rewrites_scene_files_in_the_trash(ed: Any) -> None:
    old_layout = ed.project / ".mesh_trash" / "0123456789ab" / "scenes" / "old.json"  # (a trash entry from before #632)
    old_layout.parent.mkdir(parents=True)
    old_layout.write_text(json.dumps({"entities": [{"id": "o", "sprite": HERO}]}), encoding="utf-8")
    level_before = (ed.project / "scenes/level.json").read_bytes()
    _confirm_delete(ed, "scenes/level.json")  # (a scene that references HERO, now in the trash)
    trash_before = _trash(ed.project)
    assert level_before in trash_before.values()

    _select(ed, HERO)
    assert ed.editor.file_ops.request_safe_rename_refactor("hero2.png") is True
    ed.editor.confirm_modal.execute_confirm()

    assert (ed.project / "assets/sprites/hero2.png").read_bytes() == b"PROJECT-HERO"
    assert _trash(ed.project) == trash_before
    assert not _errors(ed)


def test_632_rollback_after_a_failed_reference_write_restores_from_its_own_trash_folder(
        ed: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.editor.persistence_utils as persistence_utils

    level = ed.project / "scenes/level.json"
    level_before = level.read_bytes()
    first = _confirm_delete(ed, HERO)
    assert _trash(ed.project) and _sprite(ed.project) == ""
    level.write_bytes(level_before)  # (the same plan again: HERO re-created, still referenced)
    (ed.project / HERO).write_bytes(b"HERO-2")
    ed.editor.project_explorer.refresh_tree()

    real_write = persistence_utils.write_atomic_utf8

    def failing_write(path: Any, text: str, *args: Any, **kwargs: Any) -> Any:
        if Path(path).name == "level.json":
            raise OSError("disk full")
        return real_write(path, text, *args, **kwargs)

    monkeypatch.setattr(persistence_utils, "write_atomic_utf8", failing_write)
    trash_before = _trash(ed.project)
    assert _confirm_delete(ed, HERO) == first

    assert (ed.project / HERO).read_bytes() == b"HERO-2"  # (restored from this staging's folder)
    assert level.read_bytes() == level_before
    assert _trash(ed.project) == trash_before  # (the earlier copy untouched)
    assert list(trash_before.values()) == [b"PROJECT-HERO"]
    assert any("Reference update failed" in m for m in _errors(ed)), ed.editor.feedback.pending()


# ---------------------------------------------------------------------------- #668 review: folder at Confirm time


def test_a_file_turned_into_a_folder_while_the_dialog_is_open_is_refused_at_confirm(ed: Any) -> None:
    _select(ed, HERO)
    ed.editor.run_editor_action("editor.delete")
    assert _dialog_open(ed)
    (ed.project / HERO).unlink()
    (ed.project / HERO).mkdir()
    (ed.project / HERO / "inside.png").write_bytes(b"INSIDE")
    before = _files(ed.project)
    ed.editor.confirm_modal.execute_confirm()
    assert _files(ed.project) == before
    assert _sprite(ed.project) == HERO
    assert any("is a folder" in m for m in _errors(ed)), ed.editor.feedback.pending()


# ----------------------------------------------------------------------------- #670 inline rename with real keys


def _type(window: Any, text: str) -> None:
    for ch in text:
        window.dispatch_event("on_text", ch)


def _start_inline_rename(ed: Any, rel: str, new_stem: str) -> None:
    """F2 on ``rel`` in the Project panel and the stem replaced by ``new_stem``, all real keys and typed text."""
    _select(ed, rel)
    _key(ed.window, "F2")
    project = ed.editor.project_explorer
    assert project.inline_rename_active, "F2 didn't start an inline rename"
    for _ in project.inline_rename_state.current_text:
        _key(ed.window, "BACKSPACE")
    _type(ed.window, new_stem)


def _capture_router_return(ed: Any) -> bool:
    """Return through the capture key router's own route. The editor's router runs first and takes Enter in an inline
    rename itself; this route is the one reached whenever the editor leaves it unhandled."""
    from engine.input_runtime import capture_key_router as router
    from engine.input_runtime.capture_focus_query import get_capture_focus_snapshot

    controller = ed.window.input_controller
    ret = optional_arcade.arcade.key.RETURN
    return bool(router.route_and_dispatch(controller, ret, 0, get_capture_focus_snapshot(controller, 0)))


@pytest.mark.parametrize("route", ["return_key", "capture_router"])
def test_670_f2_typed_name_and_return_renames_through_the_safe_rename(ed: Any, route: str) -> None:
    _start_inline_rename(ed, HERO, "hero2")
    if route == "return_key":
        _key(ed.window, "RETURN")
    else:
        assert _capture_router_return(ed)
    assert _dialog_open(ed), "Return did nothing"
    ed.editor.confirm_modal.execute_confirm()
    assert not (ed.project / HERO).exists()
    assert (ed.project / "assets/sprites/hero2.png").read_bytes() == b"PROJECT-HERO"
    assert _sprite(ed.project) == "assets/sprites/hero2.png"  # (references follow: the safe rename)
    assert not ed.editor.project_explorer.inline_rename_active
    assert not _errors(ed)


@pytest.mark.parametrize("route", ["return_key", "capture_router"])
def test_670_return_onto_an_existing_name_is_refused(ed: Any, route: str) -> None:
    before = _files(ed.project)
    _start_inline_rename(ed, HERO, "villain")
    if route == "return_key":
        _key(ed.window, "RETURN")
    else:
        _capture_router_return(ed)
    assert not _dialog_open(ed)
    assert _files(ed.project) == before
    assert any("already exists" in m for m in _errors(ed)), ed.editor.feedback.pending()


def test_670_with_the_editor_closed_a_left_over_rename_leaves_return_to_the_game(ed: Any) -> None:
    _start_inline_rename(ed, HERO, "hero2")
    ed.editor.toggle()
    assert ed.editor.active is False and ed.editor.project_explorer.inline_rename_active
    assert _capture_router_return(ed) is False  # (unhandled: the commit is disabled, so the game still gets Enter)
    assert (ed.project / HERO).exists() and not _dialog_open(ed)
