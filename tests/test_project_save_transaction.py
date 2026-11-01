"""F3 (#422): a Studio project's save writes every changed file or none (``engine.project_save``).

A save changes several files: an HD-2D room's map file, the changed rooms, the world file and the prefab catalogue
holding the shared player. Each was written in turn, so a failure after the first left a mix of new and old on disk
while Save said it failed. Now every document is serialised and staged before any is replaced; a replacement that
fails puts back the ones before it; a put-back that fails keeps the previous version and says where (recovery
needed). Every failure is a SaveError with a report, given to Studio, ``mesh author`` and MCP clients alike.

Failures are injected at each file step (stage, keep the original, replace, put back) on a real project on disk.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest

from engine import authoring_session, project_save
from engine import project_ops as ops
from engine.project_save import SaveError, save_documents
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.integration

WORLD = "packs/core_regions/worlds/main.json"
START, CELLAR = "packs/core_regions/scenes/start.json", "packs/core_regions/scenes/cellar.json"
PREFABS = "assets/prefabs.json"
ORDER = [CELLAR, START, WORLD, PREFABS]  # (what a save of every kind of change writes, in order)
HERO = "assets/sprites/hero.png"


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A blank project with a second room, Cellar, saved: copied per test."""
    root = tmp_path_factory.mktemp("f3") / "game"
    create_project(root, "Game", template_id="blank")
    project = _open(root)
    assert project.add_room("Cellar") == "cellar"
    project.save()
    return root


@pytest.fixture()
def root(made: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(made, tmp_path / "game", copy_function=shutil.copy2))


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _mark(scene: dict) -> dict:
    return {**scene, "name": f"{scene.get('name', '')} (edited)"}


def _edit_everything(project: Project) -> None:
    """Both rooms, the world (a new start room) and the shared player (its picture): four files to save."""
    project.edit_scene(_mark, "start")
    project.edit_scene(_mark, "cellar")
    player = next(e for e in ops.entities(project.scene("start")) if e.get("tag") == "player")
    project.edit_scene(lambda scene: ops.set_picture(scene, player["id"], HERO), "start")
    project.set_start_room("cellar")


def _tree(root: Path) -> dict[str, tuple[bytes, int]]:
    """Every file in the project, with its bytes and modification time."""
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def _memory(project: Project) -> tuple[Any, ...]:
    """What a failed save must not change: the edits, dirty flags, undo/redo, revision, what was seen on disk."""
    return (json.dumps(project.all_documents(), sort_keys=True), sorted(project.dirty), project.world_dirty,
            project.player_dirty, project.revision, len(project._undo), len(project._redo), dict(project._seen_on_disk))


def _failing(monkeypatch: pytest.MonkeyPatch, step: str, when: Callable[[int, tuple[Any, ...]], bool]) -> list[tuple]:
    """Make ``project_save.<step>`` raise OSError on the calls ``when(call number, args)`` picks; returns the calls."""
    real, calls = getattr(project_save, step), []

    def step_(*args: Any) -> Any:
        calls.append(args)
        if when(len(calls), args):
            raise OSError(28, f"injected: {step} failed", str(args[-1]))
        return real(*args)

    monkeypatch.setattr(project_save, step, step_)
    return calls


def _report(project: Project) -> dict:
    assert project.last_save_report is not None
    return project.last_save_report


def _no_save_files(root: Path) -> None:
    assert not [p for p in root.rglob("*") if ".save-" in p.name or p.name.endswith(".tmp")]


# --- the failure the brief describes, at the base and now --------------------------------------------------------
def test_a_failure_writing_the_second_file_leaves_the_project_on_disk_as_it_was(root: Path, monkeypatch) -> None:
    project = _open(root)
    _edit_everything(project)
    disk, memory = _tree(root), _memory(project)
    _failing(monkeypatch, "_replace", lambda n, _a: n == 2)  # (the base wrote the cellar, then failed on the start room)
    with pytest.raises(SaveError) as caught:
        project.save()
    report = caught.value.report
    assert (report["ok"], report["stage"], report["reason"]) == (False, "commit", "commit_failed")
    assert [d["path"] for d in report["documents"]] == ORDER
    assert [d["result"] for d in report["documents"]] == ["restored", "not_written", "not_written", "not_written"]
    assert report["restored"] == [CELLAR] and report["committed"] == [] and not report["recovery_required"]
    assert report["unsaved_edits_kept"] and "the project on disk is as it was before this save" in report["message"]
    assert _tree(root) == disk, "every file as it was, to the byte and its time; nothing left beside them"
    assert _memory(project) == memory and project.is_dirty, "the edits are still there, unsaved, undo as it was"
    assert project.last_save_report == report and project.last_save_backups == []


@pytest.mark.parametrize("fails", [1, 3, 4], ids=["first", "third", "last"])
def test_a_failure_replacing_any_file_puts_back_every_one_before_it(root: Path, monkeypatch, fails: int) -> None:
    project = _open(root)
    _edit_everything(project)
    disk, memory = _tree(root), _memory(project)
    _failing(monkeypatch, "_replace", lambda n, _a: n == fails)
    with pytest.raises(SaveError) as caught:
        project.save()
    assert caught.value.report["restored"] == ORDER[:fails - 1]
    assert _tree(root) == disk and _memory(project) == memory


def test_the_player_failing_after_the_rooms_and_world_were_written_puts_them_back(root: Path, monkeypatch) -> None:
    project = _open(root)
    _edit_everything(project)
    disk = _tree(root)
    _failing(monkeypatch, "_replace", lambda _n, args: Path(args[1]).name == "prefabs.json")
    with pytest.raises(SaveError, match=r"Writing assets/prefabs\.json failed .* the 3 file\(s\) already written were put back"):
        project.save()
    assert _report(project)["restored"] == [CELLAR, START, WORLD]
    assert _tree(root) == disk and project.player_dirty and project.player["sprite"] == HERO


@pytest.mark.parametrize("step,fails", [("_write_new", 1), ("_write_new", 3), ("_preserve", 2)],
                         ids=["staging-first", "staging-later", "keeping-an-original"])
def test_a_failure_while_staging_changes_no_project_file(root: Path, monkeypatch, step: str, fails: int) -> None:
    project = _open(root)
    _edit_everything(project)
    disk, memory = _tree(root), _memory(project)
    _failing(monkeypatch, step, lambda n, _a: n == fails)
    with pytest.raises(SaveError, match="no project file was changed") as caught:
        project.save()
    report = caught.value.report
    assert (report["stage"], report["reason"]) == ("stage", "stage_failed")
    assert all(d["result"] == "not_written" for d in report["documents"]) and not report["committed"]
    assert _tree(root) == disk and _memory(project) == memory


def test_an_interrupt_mid_save_puts_back_what_was_written_and_still_interrupts(root: Path, monkeypatch) -> None:
    project = _open(root)
    _edit_everything(project)
    disk, memory = _tree(root), _memory(project)
    real, interrupts = project_save._replace, [1]

    def interrupted(src: Path, dst: Path) -> None:
        real(src, dst)
        if Path(dst).name == "main.json" and interrupts:
            interrupts.pop()
            raise KeyboardInterrupt  # (just after the world file was replaced: it is put back too)

    monkeypatch.setattr(project_save, "_replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        project.save()
    assert _tree(root) == disk and _memory(project) == memory


# --- putting back that fails: visible, recoverable -----------------------------------------------------------------
def test_a_put_back_that_fails_keeps_the_previous_version_and_says_where(root: Path, monkeypatch) -> None:
    project = _open(root)
    _edit_everything(project)
    old_cellar, old_start = (root / CELLAR).read_bytes(), (root / START).read_bytes()
    memory = _memory(project)
    _failing(monkeypatch, "_replace",
             lambda _n, args: Path(args[1]).name == "main.json"  # the world file fails...
             or (Path(args[0]).name.endswith(".original") and Path(args[1]).name == "cellar.json"))  # ...and the cellar can't go back
    with pytest.raises(SaveError) as caught:
        project.save()
    report = caught.value.report
    assert (report["stage"], report["reason"], report["recovery_required"]) == ("rollback", "rollback_incomplete", True)
    assert report["restored"] == [START] and report["committed"] == [CELLAR]
    [stuck] = report["needs_recovery"]
    assert stuck["path"] == CELLAR and stuck["original"].startswith(CELLAR + ".save-") and stuck["original"].endswith(".original")
    assert stuck["action"] == f"copy {stuck['original']} back over {CELLAR}"
    assert (root / stuck["original"]).read_bytes() == old_cellar, "the previous version is kept, where the report says"
    assert (root / CELLAR).read_bytes() != old_cellar and (root / START).read_bytes() == old_start
    message = str(caught.value)
    assert "RECOVERY NEEDED" in message and stuck["original"] in message and "Put back as they were: " + START in message
    assert _memory(project)[:7] == memory[:7] and project.is_dirty, "the edits are still there, to save again"
    monkeypatch.undo()
    project.save()  # (fixed: saving again writes everything, and doesn't take its own file for an outside change)
    assert not project.is_dirty and project.last_save_backups == []
    assert (root / stuck["original"]).read_bytes() == old_cellar, "a recovery copy is never deleted by a later save"


def test_a_new_file_that_cant_be_taken_back_is_named_for_deletion(root: Path, monkeypatch) -> None:
    project = _open(root)
    key = project.add_room("Attic")
    rel = project.path(key)
    assert not (root / rel).exists()
    _failing(monkeypatch, "_replace", lambda _n, args: Path(args[1]).name == "main.json")
    _failing(monkeypatch, "_unlink", lambda _n, args: Path(args[0]).name == Path(rel).name)
    with pytest.raises(SaveError) as caught:
        project.save()
    [stuck] = caught.value.report["needs_recovery"]
    assert stuck == {"path": rel, "original": None, "action": f"delete {rel} (it didn't exist before)"}
    assert [d["existed"] for d in caught.value.report["documents"] if d["path"] == rel] == [False]


def test_a_new_room_is_taken_away_again_and_an_existing_one_put_back(root: Path, monkeypatch) -> None:
    project = _open(root)
    key = project.add_room("Attic")  # (absent on disk until saved)
    project.edit_scene(_mark, "start")  # (present)
    rel = project.path(key)
    disk = _tree(root)
    _failing(monkeypatch, "_replace", lambda _n, args: Path(args[1]).name == "main.json")
    with pytest.raises(SaveError) as caught:
        project.save()
    existed = {d["path"]: d["existed"] for d in caught.value.report["documents"]}
    assert existed[rel] is False and existed[START] is True
    assert not (root / rel).exists() and _tree(root) == disk


# --- HD-2D: a map file resized with its room --------------------------------------------------------------------------
def test_a_resized_map_file_goes_back_to_its_size_when_its_room_fails(root: Path, monkeypatch) -> None:
    project = _open(root)
    key, _kit = project.add_hd2d_room("Meadow", 40, 30)
    project.save()
    map_rel = project.map_path(key)
    assert map_rel is not None
    project.edit_scene(lambda s: ops.expand_hd2d_room(s, 48, 36), key)
    disk = _tree(root)
    _failing(monkeypatch, "_replace", lambda _n, args: Path(args[1]) == root / project.path(key))
    with pytest.raises(SaveError) as caught:
        project.save()
    documents = caught.value.report["documents"]
    assert [(d["path"], d["kind"]) for d in documents[:2]] == [(map_rel, "map"), (project.path(key), "room")]
    assert caught.value.report["restored"] == [map_rel]
    assert _tree(root) == disk and json.loads((root / map_rel).read_text(encoding="utf-8"))["width"] == 40
    monkeypatch.undo()
    assert project.save()[:2] == [map_rel, project.path(key)]
    assert json.loads((root / map_rel).read_text(encoding="utf-8"))["width"] == 48


def test_a_map_file_that_cant_be_resized_refuses_before_anything_is_written(root: Path) -> None:
    project = _open(root)
    key, _kit = project.add_hd2d_room("Meadow", 40, 30)
    project.save()
    map_rel = project.map_path(key)
    assert map_rel is not None
    project.edit_scene(_mark, "start")
    project.edit_scene(lambda s: ops.expand_hd2d_room(s, 48, 36), key)
    (root / map_rel).write_text("{broken", encoding="utf-8")
    disk = _tree(root)
    with pytest.raises(SaveError, match="nothing was saved") as caught:
        project.save()
    report = caught.value.report
    assert (report["stage"], report["reason"]) == ("validate", "map_file_conflict")
    assert {d["path"] for d in report["documents"]} == {START, project.path(key)}
    assert all(d["result"] == "not_written" for d in report["documents"]) and _tree(root) == disk


# --- the prefab catalogue (H1-F2 kept) -----------------------------------------------------------------------------------
def test_an_unreadable_catalogue_still_refuses_before_anything_is_written(root: Path) -> None:
    project = _open(root)
    _edit_everything(project)
    (root / PREFABS).write_bytes(b"{not json")
    disk, memory = _tree(root), _memory(project)
    with pytest.raises(ops.OpError, match=r"assets/prefabs\.json isn't a prefab list Studio can read") as caught:
        project.save()
    report = cast(SaveError, caught.value).report
    assert (report["stage"], report["reason"]) == ("validate", "prefab_catalogue_unreadable")
    assert [d["path"] for d in report["documents"]] == ORDER and not report["committed"]
    assert _tree(root) == disk and _memory(project) == memory


# --- outside changes: kept, never overwritten, never taken for a Studio save -------------------------------------------
def _change_outside(root: Path, rel: str, text: str) -> bytes:
    path = root / rel
    data = path.read_text(encoding="utf-8").replace('"Cellar"', f'"{text}"', 1).encode("utf-8")
    path.write_bytes(data)
    later = path.stat().st_mtime + 2  # (later than Studio read it, however coarse the clock)
    os.utime(path, (later, later))
    return data


def test_an_outside_change_is_kept_in_place_and_beside_it_when_the_save_fails(root: Path, monkeypatch) -> None:
    project = _open(root)
    _edit_everything(project)
    outside = _change_outside(root, CELLAR, "Changed outside")
    _failing(monkeypatch, "_replace", lambda n, _a: n == 3)
    with pytest.raises(SaveError) as caught:
        project.save()
    backup = CELLAR + ".outside-change.bak"
    assert caught.value.report["outside_change_backups"] == [backup] == project.last_save_backups
    assert (root / CELLAR).read_bytes() == outside, "the outside version is back in place"
    assert (root / backup).read_bytes() == outside
    monkeypatch.undo()
    project.save()  # (again: still an outside change to Studio, kept in the same backup, not a second one)
    assert project.last_save_backups == [backup] and (root / backup).read_bytes() == outside
    assert not (root / (CELLAR + ".outside-change-2.bak")).exists()
    _no_save_files(root)


def test_an_earlier_different_backup_is_never_overwritten(root: Path) -> None:
    project = _open(root)
    project.edit_scene(_mark, "cellar")
    backup = root / (CELLAR + ".outside-change.bak")
    backup.write_bytes(b"an earlier outside version")
    outside = _change_outside(root, CELLAR, "Changed again")
    project.save()
    assert project.last_save_backups == [CELLAR + ".outside-change-2.bak"]
    assert backup.read_bytes() == b"an earlier outside version"
    assert (root / (CELLAR + ".outside-change-2.bak")).read_bytes() == outside


def test_a_file_changed_during_the_save_is_not_replaced(root: Path, monkeypatch) -> None:
    project = _open(root)
    _edit_everything(project)
    real, outside = project_save._replace, {}

    def meanwhile(src: Path, dst: Path) -> None:
        if not outside:  # (just before the first file is replaced, something else edits a later one)
            outside["data"] = (root / WORLD).read_bytes() + b"\n"
            (root / WORLD).write_bytes(outside["data"])
        real(src, dst)

    monkeypatch.setattr(project_save, "_replace", meanwhile)
    with pytest.raises(SaveError) as caught:
        project.save()
    report = caught.value.report
    assert (report["stage"], report["reason"]) == ("commit", "changed_during_save")
    assert (root / WORLD).read_bytes() == outside["data"], "the other program's edit is kept"
    assert report["restored"] == [CELLAR, START] and project.world_dirty


# --- a save that works ----------------------------------------------------------------------------------------------
def test_a_multi_room_save_reopens_as_saved_with_nothing_left_beside_it(root: Path) -> None:
    project = _open(root)
    _edit_everything(project)
    undo_steps, revision = len(project._undo), project.revision
    assert project.save() == ORDER
    report = _report(project)
    assert report["ok"] and report["stage"] is None and report["committed"] == ORDER
    assert all(d["result"] == "saved" for d in report["documents"]) and not report["leftovers"]
    assert not project.is_dirty and (len(project._undo), project.revision) == (undo_steps, revision)
    assert all(project._seen_on_disk[rel] == (root / rel).stat().st_mtime for rel in ORDER)
    _no_save_files(root)
    reopened = _open(root)
    assert json.dumps(reopened.all_documents(), sort_keys=True) == json.dumps(project.all_documents(), sort_keys=True)
    assert reopened.start_key() == "cellar" and reopened.player is not None and reopened.player["sprite"] == HERO
    assert project.undo() and project.is_dirty, "undoing past a save leaves something to save again (as before)"


def test_files_are_written_exactly_as_before(root: Path) -> None:
    from engine.json_io import dumps_stable

    project = _open(root)
    _edit_everything(project)
    project.save()
    rooms = project.all_documents()["rooms"]
    assert (root / START).read_bytes() == (dumps_stable(rooms["start"]) + "\n").encode("utf-8")


# --- the service itself: folders, serialising -------------------------------------------------------------------------
def test_a_new_folder_made_for_a_file_is_removed_when_the_save_is_put_back(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "old.json").write_text("{}\n", encoding="utf-8")
    _failing(monkeypatch, "_replace", lambda n, _a: n == 2)
    with pytest.raises(SaveError):
        save_documents(tmp_path, [("rooms/new/a.json", "room", {"a": 1}), ("old.json", "world", {"b": 2})], {})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["old.json"]


def test_a_document_that_isnt_json_refuses_before_anything_is_touched(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SaveError) as caught:
        save_documents(tmp_path, [("a.json", "room", {"a": 1}), ("b.json", "room", {"bad": {1, 2}})], {})
    assert (caught.value.report["stage"], caught.value.report["reason"]) == ("serialize", "serialize_failed")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"] and (tmp_path / "a.json").read_text() == "{}\n"


# --- who sees it: Studio, mesh author, MCP clients ----------------------------------------------------------------------
def test_studio_says_the_save_failed_and_that_the_changes_are_still_there(root: Path, monkeypatch) -> None:
    from engine.studio import Studio
    from engine.studio_ai import StudioAIHost

    project = _open(root)
    _edit_everything(project)
    said: list[tuple[str, bool]] = []
    studio = SimpleNamespace(project=project, _flush_fields=lambda: True, _rebuild=lambda: None, message="",
                             _say=lambda text, ok=True: said.append((text, ok)), window=None)
    _failing(monkeypatch, "_replace", lambda n, _a: n == 2)
    assert Studio.save(cast(Studio, studio)) is False
    text, ok = said[-1]
    assert not ok and text.startswith(f"Couldn't save: Writing {START} failed")
    assert text.endswith("Your changes are still here, unsaved.") and project.is_dirty
    read = StudioAIHost(studio).read_live_scene()  # (what an AI reads from the open Studio: the last save's report)
    assert read["unsaved"] is True and read["last_save"]["reason"] == "commit_failed"


CHANGES = [{"op": "place_prefab", "room": "cellar", "prefab": "person", "x": 64, "y": 64},
           {"op": "place_prefab", "room": "start", "prefab": "person", "x": 96, "y": 96}]


def test_an_agent_applying_to_the_files_is_told_the_truth(root: Path, monkeypatch) -> None:
    from engine.mcp_server import tools

    disk = _tree(root)
    _failing(monkeypatch, "_replace", lambda n, _a: n == 2)
    result = authoring_session.apply(root, CHANGES)
    assert result["ok"] is False and result["reason"] == "save_failed" and "written" not in result
    assert result["message"].startswith("The changes were checked but not saved: Writing ")
    save = result["save"]
    assert (save["stage"], save["reason"], save["recovery_required"]) == ("commit", "commit_failed", False)
    assert save["restored"] == [CELLAR] and save["unsaved_edits_kept"] is False
    assert _tree(root) == disk
    _failing(monkeypatch, "_replace", lambda n, _a: n == 2)
    assert tools.apply_changes(CHANGES, root=str(root))["save"]["reason"] == "commit_failed"  # (MCP: the same result)
    assert _tree(root) == disk


def test_mesh_author_apply_prints_the_report_and_exits_1(root: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    from mesh_cli import author

    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps(CHANGES), encoding="utf-8")
    _failing(monkeypatch, "_replace", lambda _n, args: Path(args[0]).name.endswith(".original")
             or Path(args[1]).name == "start.json")  # (the start room fails, and the cellar can't be put back)
    code = author.handle(SimpleNamespace(author_command="apply", project=str(root), changes=str(changes), dry_run=False))
    printed = json.loads(capsys.readouterr().out)
    assert code == 1 and printed["reason"] == "save_failed"
    assert printed["save"]["recovery_required"] is True and printed["save"]["needs_recovery"][0]["path"] == CELLAR
    assert "Apply the changes again once the files are put back." in printed["message"]
