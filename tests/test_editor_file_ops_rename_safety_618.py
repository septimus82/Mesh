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
    replaced: list = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda s, d: (replaced.append((s, d)), real_replace(s, d)))

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
    replaced: list = []
    monkeypatch.setattr(os, "replace", lambda s, d: replaced.append((s, d)))

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
