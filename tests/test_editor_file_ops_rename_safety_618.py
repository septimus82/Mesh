"""#618: the legacy editor's safe rename/move never overwrites a file, never writes outside the project, and refuses
a plan whole, before any file or reference changes.

Every test drives the controller the way the editor does: ``request_safe_rename_refactor`` /
``request_safe_move_refactor`` (what F2/inline rename and Move call), then the real confirm modal's
``execute_confirm`` (what its Confirm/Enter runs). Nothing on the controller is patched; only the editor around it
(selection, feedback, undo) is a stand-in.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor import persistence_utils
from engine.editor.asset_ops import editor_file_ops_controller as efoc
from engine.editor.asset_ops.editor_file_ops_controller import EditorFileOpsController
from engine.editor.editor_confirm_modal_controller import EditorConfirmModalController

pytestmark = pytest.mark.integration


class _Feedback:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __getattr__(self, severity: str):
        return lambda message, **_kw: self.messages.append((severity, message))


class _Explorer:
    """The Project Explorer as the file-ops controller reads it: one selected row, or several selected paths."""

    def __init__(self, root: Path) -> None:
        self.root, self.paths, self.selectable_rows = root, [], []
        self.row = None

    def select(self, *rels: str) -> None:
        self.paths = list(rels)
        self.row = SimpleNamespace(entry=SimpleNamespace(path=str(self.root / rels[0]), rel_path=rels[0], is_dir=False))

    def get_selected_row(self):
        return self.row

    def selected_paths(self, _rows):
        return self.paths

    def refresh_tree(self) -> None:
        pass

    def set_selection_by_path(self, _path) -> None:
        pass


@pytest.fixture
def project(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "assets" / "sub").mkdir(parents=True)
    (root / "scenes").mkdir()
    (root / "assets" / "hero.png").write_bytes(b"HERO")
    (root / "assets" / "villain.png").write_bytes(b"VILLAIN")
    (root / "assets" / "a.png").write_bytes(b"A")
    (root / "assets" / "b.png").write_bytes(b"B")
    scene = {"entities": [{"id": n, "sprite": f"assets/{n}.png"} for n in ("hero", "villain", "a", "b")]}
    (root / "scenes" / "level.json").write_text(json.dumps(scene), encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"OUTSIDE")
    undo: list = []
    editor = SimpleNamespace(window=SimpleNamespace(repo_root=root, scene_controller=None),
                             project_explorer=_Explorer(root), feedback=_Feedback(), _push_command=undo.append)
    editor.confirm_modal = EditorConfirmModalController(editor)
    editor.file_ops = EditorFileOpsController(editor)
    return SimpleNamespace(root=root, outside=outside, editor=editor, ops=editor.file_ops, undo=undo)


def _snapshot(*roots: Path) -> dict[str, bytes]:
    """Every file under ``roots`` (links not followed), by path: what "nothing changed" compares."""
    files = {}
    for root in roots:
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                path = Path(dirpath) / name
                files[path.as_posix()] = path.read_bytes()
    return files


def _sprites(p) -> dict[str, str]:
    data = json.loads((p.root / "scenes" / "level.json").read_text(encoding="utf-8"))
    return {e["id"]: e["sprite"] for e in data["entities"]}


def _errors(p) -> list[str]:
    return [m for sev, m in p.editor.feedback.messages if sev == "error"]


def _spy_moves(monkeypatch) -> list:
    """Every file move or replace from here on (the controller's no-clobber move, and os.replace, which scene-file
    writes use), still performed."""
    calls: list = []
    real_move, real_replace = efoc._move_no_clobber, os.replace
    monkeypatch.setattr(efoc, "_move_no_clobber", lambda s, d: (calls.append((s, d)), real_move(s, d)))
    monkeypatch.setattr(os, "replace", lambda s, d: (calls.append((s, d)), real_replace(s, d)))
    return calls


def _assert_refused_untouched(p, before: dict[str, bytes], *, dialog_opened: bool) -> None:
    assert _snapshot(p.root, p.outside) == before, "a refused plan changed files"
    assert p.undo == [], "a refused plan pushed an undo step"
    assert p.ops._pending_refactor_plan is None
    if not dialog_opened:
        assert p.editor.confirm_modal._on_confirm is None, "the confirmation dialog opened for a refused plan"
    assert _errors(p), "the refusal wasn't reported"


# ---------------------------------------------------------------------------------------------- collisions
def test_rename_onto_an_existing_file_is_refused_before_the_dialog(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_rename_refactor("villain.png") is False

    _assert_refused_untouched(p, before, dialog_opened=False)
    assert "already exists" in _errors(p)[-1]


def test_rename_destination_appearing_while_the_dialog_is_open_is_refused_at_confirm(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    assert p.ops.request_safe_rename_refactor("hero2.png") is True
    (p.root / "assets" / "hero2.png").write_bytes(b"MADE-MEANWHILE")
    before = _snapshot(p.root, p.outside)

    p.editor.confirm_modal.execute_confirm()

    _assert_refused_untouched(p, before, dialog_opened=True)
    assert _sprites(p)["hero"] == "assets/hero.png"


@pytest.mark.parametrize("when", ["request", "confirm"])
def test_move_into_a_folder_holding_a_same_named_file_is_refused(project, when: str) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    if when == "request":
        (p.root / "assets" / "sub" / "hero.png").write_bytes(b"OTHER-HERO")
        before = _snapshot(p.root, p.outside)
        assert p.ops.request_safe_move_refactor("assets/sub") is False
    else:
        assert p.ops.request_safe_move_refactor("assets/sub") is True
        (p.root / "assets" / "sub" / "hero.png").write_bytes(b"OTHER-HERO")
        before = _snapshot(p.root, p.outside)
        p.editor.confirm_modal.execute_confirm()

    _assert_refused_untouched(p, before, dialog_opened=when == "confirm")


@pytest.mark.parametrize("when", ["request", "confirm"])
def test_a_collision_on_the_second_step_leaves_no_partial_state(project, monkeypatch, when: str) -> None:
    """a.png then b.png into sub/, where sub/b.png exists: the first move never runs and no reference changes."""
    p = project
    p.editor.project_explorer.select("assets/a.png", "assets/b.png")
    if when == "request":
        (p.root / "assets" / "sub" / "b.png").write_bytes(b"OTHER-B")
        assert p.ops.request_safe_move_refactor("assets/sub") is False
    else:
        assert p.ops.request_safe_move_refactor("assets/sub") is True
        assert [s.src_rel for s in p.ops._pending_refactor_plan.fs_steps] == ["assets/a.png", "assets/b.png"]
        (p.root / "assets" / "sub" / "b.png").write_bytes(b"OTHER-B")
    before = _snapshot(p.root, p.outside)
    replaced = _spy_moves(monkeypatch)

    if when == "confirm":
        p.editor.confirm_modal.execute_confirm()

    assert replaced == [], "a file step ran before the plan was refused"
    _assert_refused_untouched(p, before, dialog_opened=when == "confirm")
    assert _sprites(p) == {"hero": "assets/hero.png", "villain": "assets/villain.png",
                           "a": "assets/a.png", "b": "assets/b.png"}


def test_two_items_with_one_destination_are_refused(project) -> None:
    p = project
    (p.root / "assets" / "sub" / "a.png").write_bytes(b"SUB-A")
    (p.root / "other").mkdir()
    p.editor.project_explorer.select("assets/a.png", "assets/sub/a.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor("other") is False

    _assert_refused_untouched(p, before, dialog_opened=False)


def test_an_item_inside_another_item_being_moved_is_refused(project) -> None:
    p = project
    (p.root / "assets" / "sub" / "x.png").write_bytes(b"X")
    (p.root / "other").mkdir()
    p.editor.project_explorer.select("assets/sub", "assets/sub/x.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor("other") is False

    _assert_refused_untouched(p, before, dialog_opened=False)


def test_a_source_gone_while_the_dialog_is_open_is_refused_before_any_write(project, monkeypatch) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    assert p.ops.request_safe_rename_refactor("player.png") is True
    (p.root / "assets" / "hero.png").unlink()
    before = _snapshot(p.root, p.outside)
    replaced = _spy_moves(monkeypatch)

    p.editor.confirm_modal.execute_confirm()

    assert replaced == []
    _assert_refused_untouched(p, before, dialog_opened=True)
    assert _sprites(p)["hero"] == "assets/hero.png"


def test_a_folder_can_not_move_inside_itself(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/sub")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor("assets/sub") is False

    _assert_refused_untouched(p, before, dialog_opened=False)


# ---------------------------------------------------------------------------------------------- case-only rename
def test_case_only_rename_renames_the_file_and_keeps_its_data(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")

    assert p.ops.request_safe_rename_refactor("Hero.png") is True
    p.editor.confirm_modal.execute_confirm()

    names = os.listdir(p.root / "assets")
    assert "Hero.png" in names and "hero.png" not in names
    assert (p.root / "assets" / "Hero.png").read_bytes() == b"HERO"
    assert (p.root / "assets" / "villain.png").read_bytes() == b"VILLAIN"
    assert _sprites(p)["hero"] == "assets/Hero.png"
    assert _errors(p) == []


def test_case_only_rename_onto_a_distinct_file_is_refused_on_case_sensitive_disks(project) -> None:
    p = project
    (p.root / "assets" / "Hero.png").write_bytes(b"OTHER-HERO")
    if (p.root / "assets" / "hero.png").read_bytes() != b"HERO":
        pytest.skip("this file system is case-insensitive: hero.png and Hero.png are one file here")
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_rename_refactor("Hero.png") is False

    _assert_refused_untouched(p, before, dialog_opened=False)


# ---------------------------------------------------------------------------------------------- names and paths
_BAD_NAMES = ["../escaped.png", "..", ".", "sub/x.png", "sub\\x.png", "C:x.png", "C:\\evil.png", "D:/evil.png",
              "/abs.png", "\\abs.png", "a:stream.png", "CON", "con.png", "LPT1.txt", "NUL .png", "aux", "trail.",
              "trail ", "", "q?.png", "nul\x00.png"]


@pytest.mark.parametrize("name", _BAD_NAMES)
def test_rename_to_something_that_is_not_one_plain_name_is_refused(project, name: str) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_rename_refactor(name) is False

    _assert_refused_untouched(p, before, dialog_opened=False)


def test_rename_to_an_absolute_path_outside_the_project_is_refused(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_rename_refactor(str(p.outside / "stolen.png")) is False

    _assert_refused_untouched(p, before, dialog_opened=False)


@pytest.mark.parametrize("dest", ["../outside", "assets/../../outside", "assets/..", "./assets/sub", "/abs", "\\abs",
                                  "C:/Windows", "C:sub", "assets/CON", "assets/sub."])
def test_move_to_a_folder_that_is_not_a_plain_project_path_is_refused(project, dest: str) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor(dest) is False

    _assert_refused_untouched(p, before, dialog_opened=False)


def test_move_to_an_absolute_folder_outside_the_project_is_refused(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor(str(p.outside)) is False

    _assert_refused_untouched(p, before, dialog_opened=False)


def _link_out(link: Path, target: Path) -> None:
    """A folder link inside the project to a folder outside it: a junction on Windows (no privilege needed), a
    symlink elsewhere."""
    try:
        if sys.platform == "win32":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)
    except (OSError, AttributeError) as exc:
        pytest.skip(f"can't make a folder link here: {exc}")


def test_move_through_a_junction_out_of_the_project_is_refused(project) -> None:
    p = project
    _link_out(p.root / "assets" / "portal", p.outside)
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor("assets/portal") is False

    _assert_refused_untouched(p, before, dialog_opened=False)
    assert sorted(os.listdir(p.outside)) == ["keep.txt"]


def test_a_file_reached_through_a_junction_out_of_the_project_is_not_moved(project) -> None:
    p = project
    _link_out(p.root / "assets" / "portal", p.outside)
    p.editor.project_explorer.select("assets/portal/keep.txt")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor("assets/sub") is False

    _assert_refused_untouched(p, before, dialog_opened=False)


@pytest.mark.parametrize("dest", ["../outside", "assets/../../outside"])
def test_the_older_direct_move_refuses_a_folder_outside_the_project(project, dest: str) -> None:
    """``move_selected_asset`` (the pre-V2 move, no dialog) shares ``_perform_fs_rename``, which now takes the same
    guard."""
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.move_selected_asset(dest) is False

    assert _snapshot(p.root, p.outside) == before
    assert not (p.root.parent / "outside" / "hero.png").exists()


# ---------------------------------------------------------------------------------------------- still works
def test_plain_rename_and_move_still_work_through_confirm(project) -> None:
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    assert p.ops.request_safe_rename_refactor("player.png") is True
    p.editor.confirm_modal.execute_confirm()
    assert (p.root / "assets" / "player.png").read_bytes() == b"HERO"
    assert not (p.root / "assets" / "hero.png").exists()
    assert _sprites(p)["hero"] == "assets/player.png"

    p.editor.project_explorer.select("assets/a.png", "assets/b.png")
    assert p.ops.request_safe_move_refactor("assets/sub") is True
    p.editor.confirm_modal.execute_confirm()
    assert (p.root / "assets" / "sub" / "a.png").read_bytes() == b"A"
    assert (p.root / "assets" / "sub" / "b.png").read_bytes() == b"B"
    assert _sprites(p)["a"] == "assets/sub/a.png" and _sprites(p)["b"] == "assets/sub/b.png"
    assert _errors(p) == []
    assert [u["type"] for u in p.undo] == ["safe_rename_refactor", "safe_move_refactor"]


# ---------------------------------------------------------------------------------------------- the final move itself
def test_a_destination_made_during_confirm_is_never_overwritten(project, monkeypatch) -> None:
    """The race the up-front check can't close: the destination appears after the check, between the scene-file
    writes and the file move. The move itself refuses; scene files are restored and the failure is shown."""
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    assert p.ops.request_safe_rename_refactor("player.png") is True
    racer = p.root / "assets" / "player.png"
    real_write = persistence_utils.write_atomic_utf8

    def write_then_race(path, content):
        ok = real_write(path, content)
        if not racer.exists():
            racer.write_bytes(b"MADE-DURING-CONFIRM")
        return ok

    monkeypatch.setattr(persistence_utils, "write_atomic_utf8", write_then_race)

    p.editor.confirm_modal.execute_confirm()

    assert racer.read_bytes() == b"MADE-DURING-CONFIRM"
    assert (p.root / "assets" / "hero.png").read_bytes() == b"HERO"
    assert _sprites(p)["hero"] == "assets/hero.png"
    assert p.undo == [] and p.ops._pending_refactor_plan is None
    assert any("File System Error" in m for m in _errors(p)), p.editor.feedback.messages


def test_a_failure_during_confirm_is_rolled_back_and_shown(project) -> None:
    """A name no file system takes (300 characters): the scene files are restored, and the reason reaches the person
    (an error dialog opened during Confirm used to be closed at once)."""
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    long_name = "x" * 296 + ".png"
    assert p.ops.request_safe_rename_refactor(long_name) is True

    p.editor.confirm_modal.execute_confirm()

    assert (p.root / "assets" / "hero.png").read_bytes() == b"HERO"
    assert _sprites(p)["hero"] == "assets/hero.png"
    assert p.undo == []
    assert any("File System Error" in m for m in _errors(p)), p.editor.feedback.messages


def test_a_move_cut_short_between_link_and_unlink_is_undone(project, monkeypatch) -> None:
    """A link+unlink move interrupted after the link leaves two names of one file; rollback drops the extra name."""
    p = project
    p.editor.project_explorer.select("assets/hero.png")
    assert p.ops.request_safe_rename_refactor("player.png") is True

    def link_then_fail(src, dst):
        os.link(src, dst)
        raise OSError("interrupted before unlink")

    monkeypatch.setattr(efoc, "_move_no_clobber", link_then_fail)

    p.editor.confirm_modal.execute_confirm()

    assert not (p.root / "assets" / "player.png").exists()
    assert (p.root / "assets" / "hero.png").read_bytes() == b"HERO"
    assert _sprites(p)["hero"] == "assets/hero.png"
    assert _errors(p)


# ---------------------------------------------------------------------------------------------- older direct paths
def _scene_in_memory(p) -> dict:
    scene = {"entities": [{"id": n, "sprite": f"assets/{n}.png"} for n in ("hero", "a", "b")]}
    p.editor.window.scene_controller = SimpleNamespace(_loaded_scene_data=scene)
    return scene


def test_the_older_rename_changes_no_reference_when_the_file_is_not_renamed(project) -> None:
    p = project
    scene = _scene_in_memory(p)
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.rename_selected_asset("villain.png") is False

    assert _snapshot(p.root, p.outside) == before
    assert p.editor.window.scene_controller._loaded_scene_data["entities"][0]["sprite"] == "assets/hero.png"
    assert p.editor.window.scene_controller._loaded_scene_data is scene and p.undo == []
    assert _errors(p)


def test_the_older_batch_move_undoes_its_moves_when_one_fails(project) -> None:
    p = project
    _scene_in_memory(p)
    (p.root / "assets" / "sub" / "b.png").write_bytes(b"OTHER-B")
    before = _snapshot(p.root, p.outside)

    assert p.ops.move_selected_paths_to_folder(["assets/a.png", "assets/b.png"], "assets/sub") is False

    assert _snapshot(p.root, p.outside) == before
    sprites = {e["id"]: e["sprite"] for e in p.editor.window.scene_controller._loaded_scene_data["entities"]}
    assert sprites == {"hero": "assets/hero.png", "a": "assets/a.png", "b": "assets/b.png"}
    assert p.undo == []
    assert _errors(p)


# ---------------------------------------------------------------------------------------------- Windows specifics
@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive names: the Windows lane runs this on Windows")
def test_two_destinations_differing_only_in_case_are_one_destination_on_windows(project) -> None:
    p = project
    (p.root / "assets" / "sub" / "A.png").write_bytes(b"SUB-A")
    (p.root / "other").mkdir()
    p.editor.project_explorer.select("assets/a.png", "assets/sub/A.png")
    before = _snapshot(p.root, p.outside)

    assert p.ops.request_safe_move_refactor("other") is False

    _assert_refused_untouched(p, before, dialog_opened=False)


@pytest.mark.skipif(sys.platform != "win32",
                    reason="os.walk follows junctions on Windows only: the Windows lane runs this on Windows")
def test_a_scene_file_reached_through_a_junction_out_of_the_project_is_never_rewritten(project, tmp_path) -> None:
    p = project
    outside_scenes = tmp_path / "outside_scenes"
    outside_scenes.mkdir()
    foreign = outside_scenes / "foreign.json"
    foreign.write_text(json.dumps({"entities": [{"id": "x", "sprite": "assets/hero.png"}]}), encoding="utf-8")
    _link_out(p.root / "linked", outside_scenes)
    p.editor.project_explorer.select("assets/hero.png")
    before = _snapshot(p.root, p.outside, outside_scenes)

    assert p.ops.request_safe_rename_refactor("player.png") is False

    assert _snapshot(p.root, p.outside, outside_scenes) == before
    assert "linked/foreign.json" in _errors(p)[-1]
    assert p.undo == [] and p.editor.confirm_modal._on_confirm is None


def test_rollback_never_overwrites_a_file_made_at_an_old_path(project, monkeypatch) -> None:
    """a.png then b.png into sub/; b's move fails after a file was made where a.png used to be. Undoing a's move
    must not overwrite that file: both are kept, and the failure is shown."""
    p = project
    p.editor.project_explorer.select("assets/a.png", "assets/b.png")
    assert p.ops.request_safe_move_refactor("assets/sub") is True
    real_move = efoc._move_no_clobber

    def fail_b_after_newcomer(src, dst):
        if Path(src).name == "b.png":
            (p.root / "assets" / "a.png").write_bytes(b"NEWCOMER")
            raise OSError("b is locked")
        real_move(src, dst)

    monkeypatch.setattr(efoc, "_move_no_clobber", fail_b_after_newcomer)

    p.editor.confirm_modal.execute_confirm()

    assert (p.root / "assets" / "a.png").read_bytes() == b"NEWCOMER"
    assert (p.root / "assets" / "sub" / "a.png").read_bytes() == b"A"
    assert (p.root / "assets" / "b.png").read_bytes() == b"B"
    assert _sprites(p)["a"] == "assets/a.png"
    assert _errors(p)
