"""#462 S4: a room's map file follows the room through undo, redo, failed batches and closing; nobody else's file is touched.

A new room's map file (and one ``add_map`` makes) is written straight away, before the room is saved, because Studio and
play-tests load it from disk. Undo, a failed AI batch or a failed save put the documents back but left that file: the
same name could never be used again ("There is already a file ... that isn't one of this project's rooms"), and a room
made again with that name got the old room's key and player id, so a stale AI proposal pinned to the old room changed
the new one.

Now (``engine.studio_project``):
- a new room never gets a key this session has had (``keys_seen``): "Cellar" made again after undo is ``cellar_2``,
  with its own files and ids; redo of the first one brings back ``cellar`` itself;
- Mesh remembers each map file it made, as made. It removes one only when no room of the project, of an undo or redo
  step, or of a save uses it, and only if the file is still exactly as made (checked after moving it aside). One that
  was changed, replaced, made a link, or is reached through a link is left, and said so in ``kept_files``;
- a map file a room undone and redone needs, gone from disk meanwhile, is written again before the room is used;
- once saved with a room, a map file is part of the person's project: Mesh never removes it;
- ``add_map`` keeps only a file Mesh made for the room (or exactly what it would write), never someone else's.

A real blank project on disk per test (integration).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import authoring, authoring_session, studio_project
from engine import project_ops as ops
from engine.project_save import refused
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration

PACK = "packs/core_regions"
SCENES, MAPS = f"{PACK}/scenes", f"{PACK}/maps"
THEIRS = b'{"made by": "another tool", "width": 99, "height": 99, "layers": []}\n'


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("s4") / "game"
    create_project(root, "Game", template_id="blank")
    return root


@pytest.fixture()
def root(made: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(made, tmp_path / "game", copy_function=shutil.copy2))


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _tree(root: Path) -> dict[str, Any]:
    """Every file in the project with its bytes and modification time (links and folders by kind)."""
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() and not p.is_symlink()
            else "link" if p.is_symlink() else "folder" for p in sorted(root.rglob("*"))}


def _add(project: Project, label: str, kind: str) -> str:
    return project.add_hd2d_room(label, 24, 16)[0] if kind == "hd2d" else project.add_room(label)


def _players(project: Project, key: str) -> list[str]:
    return [str(e["id"]) for e in project.scene(key)["entities"] if e.get("tag") == "player"]


def _every_listed_room_loads(root: Path) -> None:
    """The world on disk never lists a room whose map file can't be loaded."""
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    for key, entry in json.loads((root / world_file).read_text(encoding="utf-8"))["scenes"].items():
        room = json.loads((root / entry["path"]).read_text(encoding="utf-8"))
        tilemap = room.get("tilemap")
        if tilemap:
            map_file = (root / entry["path"]).parent / tilemap["path"]
            assert json.loads(map_file.read_text(encoding="utf-8"))["width"] > 0, f"{key}: {map_file} won't load"


def _bare_room(root: Path) -> Project:
    """A room without a map, made by another tool (listed, its scene on disk)."""
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    (root / f"{SCENES}/bare.json").write_text(json.dumps({"name": "Bare", "schema_version": 1, "version": 1,
                                                          "entities": []}), encoding="utf-8")
    world = json.loads((root / world_file).read_text(encoding="utf-8"))
    world["scenes"]["bare"] = {"label": "Bare", "path": f"{SCENES}/bare.json", "tags": []}
    (root / world_file).write_text(json.dumps(world, indent=2), encoding="utf-8")
    return _open(root)


class _FakeStudio:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=f"{SCENES}/start.json"))

    def on_ai_proposal(self, _proposal: Any) -> None:
        pass

    def on_ai_decided(self, _proposal: Any) -> None:
        pass


# --- the reported defect: a room made again after undo ---------------------------------------------------------------
@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_a_room_made_again_after_undo_is_a_new_room_and_the_old_map_file_goes(root: Path, kind: str) -> None:
    project = _open(root)
    key = _add(project, "Cellar", kind)
    old_map = project.map_path(key)
    assert key == "cellar" and old_map == f"{MAPS}/cellar.json" and (root / old_map).is_file()
    old_player = _players(project, key)
    project.undo()
    assert (root / old_map).is_file(), "kept while redo can bring the room back"
    disk = _tree(root)

    again = _add(project, "Cellar", kind)  # was: "There is already a file at .../maps/cellar.json"
    assert again == "cellar_2" and project.label(again) == "Cellar"
    assert project.map_path(again) == f"{MAPS}/cellar_2.json" and _players(project, again) != old_player
    assert not project.can_redo() and not (root / old_map).exists(), "nothing can bring the old room back now"
    now = _tree(root)
    assert set(now) - set(disk) == {f"{MAPS}/cellar_2.json"} and set(disk) - set(now) == {old_map}
    assert project.kept_files == []
    assert f"{SCENES}/cellar_2.json" in project.save()
    _every_listed_room_loads(root)


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_redo_brings_back_the_same_room_with_its_map_file(root: Path, kind: str) -> None:
    project = _open(root)
    key = _add(project, "Cellar", kind)
    room, player, map_rel = project.scene(key), _players(project, key), project.map_path(key)
    made = (root / map_rel).read_bytes()
    project.undo()
    project.redo()
    assert project.scene(key) == room and _players(project, key) == player, "the same room, ids and all"
    assert (root / map_rel).read_bytes() == made
    project.save()
    _every_listed_room_loads(root)
    assert _open(root).scene(key)["name"] == "Cellar"


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_a_map_file_deleted_while_its_room_was_undone_is_written_again_on_redo(root: Path, kind: str) -> None:
    project = _open(root)
    key = _add(project, "Cellar", kind)
    map_rel = project.map_path(key)
    made = (root / map_rel).read_bytes()
    project.undo()
    (root / map_rel).unlink()  # (deleted outside Studio: "it's an orphan")
    project.redo()
    assert (root / map_rel).read_bytes() == made, "before the room is used again"
    assert project.save() and project.kept_files == []
    _every_listed_room_loads(root)


def test_a_map_file_replaced_while_its_room_was_undone_is_kept_as_it_is(root: Path) -> None:
    project = _open(root)
    key = project.add_room("Cellar")
    map_rel = project.map_path(key)
    project.undo()
    (root / map_rel).write_bytes(THEIRS)
    project.redo()
    assert (root / map_rel).read_bytes() == THEIRS
    assert project.kept_files == [{"path": map_rel, "reason": "it was changed after Mesh made it, so the room uses it "
                                                            "as it is now"}]
    project.undo()
    project.add_room("Attic")  # (the redo step goes: the replaced file isn't Mesh's any more, so it stays)
    assert (root / map_rel).read_bytes() == THEIRS


def test_a_map_file_replaced_before_its_room_is_dropped_is_kept_and_said_so(root: Path) -> None:
    project = _open(root)
    map_rel = project.map_path(project.add_room("Cellar"))
    project.undo()
    (root / map_rel).write_bytes(THEIRS)
    stamp = (root / map_rel).stat().st_mtime_ns
    project.add_room("Attic")
    assert (root / map_rel).read_bytes() == THEIRS and (root / map_rel).stat().st_mtime_ns == stamp
    assert project.kept_files == [{"path": map_rel, "reason": "it was changed after Mesh made it"}]


# --- failed batches and saves ---------------------------------------------------------------------------------------
def test_a_failed_ai_batch_leaves_no_file_and_the_name_free(root: Path) -> None:
    project = _open(root)
    disk = _tree(root)
    with pytest.raises(authoring.ChangeError, match="Change 1"):
        authoring.apply(project, [{"op": "add_room", "label": "Vault"},
                                  {"op": "move_entity", "room": "vault", "entity_id": "nobody", "x": 1, "y": 1}])
    assert _tree(root) == disk and "vault" not in project.world["scenes"] and not project.can_undo()
    assert project.add_room("Vault") == "vault", "never a room of the project: its key is free"


def test_a_failed_batch_with_add_map_leaves_no_file(root: Path) -> None:
    project = _bare_room(root)
    disk = _tree(root)
    with pytest.raises(authoring.ChangeError, match="Change 1"):
        authoring.apply(project, [{"op": "add_map", "key": "bare"},
                                  {"op": "move_entity", "room": "bare", "entity_id": "nobody", "x": 1, "y": 1}])
    assert _tree(root) == disk and "tilemap" not in project.scene("bare")


def test_a_transaction_whose_map_file_was_replaced_before_it_failed_keeps_that_file(root: Path) -> None:
    project = _open(root)
    with pytest.raises(RuntimeError), project.transaction():
        map_rel = project.map_path(project.add_room("Vault"))
        (root / map_rel).write_bytes(THEIRS)
        raise RuntimeError("a later change fails")
    assert (root / map_rel).read_bytes() == THEIRS
    assert project.kept_files == [{"path": map_rel, "reason": "it was changed after Mesh made it"}]


def test_direct_ai_authoring_whose_save_fails_leaves_no_map_file(root: Path) -> None:
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    disk = _tree(root)
    os.chmod(root / world_file, 0o444)
    try:
        result = authoring_session.apply(root, [{"op": "add_room", "label": "Vault"}])
    finally:
        os.chmod(root / world_file, 0o644)
    assert (result["ok"], result["reason"]) == (False, "save_failed")
    assert not (root / f"{MAPS}/vault.json").exists()
    assert {k for k in _tree(root) if ".save-" not in k} == set(disk)  # (F3 keeps its own record of the save)
    again = authoring_session.apply(root, [{"op": "add_room", "label": "Vault"}])
    assert again["ok"] is True and (root / f"{MAPS}/vault.json").is_file()


def test_a_save_that_needs_recovery_leaves_the_map_file(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def half_done(root_: Path, documents: Any, *_args: Any) -> Any:
        err = refused("disk_full", "Half written.", [(rel, kind) for rel, kind, _doc in documents], root_)
        err.report["recovery_required"] = True
        raise err

    monkeypatch.setattr(studio_project, "save_documents", half_done)
    result = authoring_session.apply(root, [{"op": "add_room", "label": "Vault"}])
    assert (result["ok"], result["reason"]) == (False, "save_failed")
    assert (root / f"{MAPS}/vault.json").is_file(), "the files' state isn't known: nothing is removed"


# --- saves, closing ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_save_undo_save_redo_save_reopen_never_loses_the_map_file(root: Path, kind: str) -> None:
    from engine.tooling.export_bundle import compute_export_plan

    project = _open(root)
    key = _add(project, "Attic", kind)
    map_rel, scene_rel = project.map_path(key), project.path(key)
    project.save()
    made = (root / map_rel).read_bytes()
    for step in (project.undo, project.save, project.redo, project.save, project.undo, project.save, project.redo,
                 project.save):
        step()
        assert (root / map_rel).read_bytes() == made
        _every_listed_room_loads(root)
    reopened = _open(root)
    assert reopened.scene(key)["name"] == "Attic" and reopened.map_path(key) == map_rel
    plan = compute_export_plan(root)  # (an exported game has the room and its map)
    assert plan.missing_deps == [] and {scene_rel, map_rel} <= {f.rel_path for f in plan.files}

    project.undo()
    project.save()
    project.add_room("Cellar")  # (the redo step goes; the room was saved, so its files are the person's now)
    saved_scene = (root / scene_rel).read_bytes()
    project.discard_unsaved_files()
    assert (root / map_rel).read_bytes() == made and (root / scene_rel).read_bytes() == saved_scene
    assert project.kept_files == []


def test_closing_without_saving_removes_only_unsaved_map_files(root: Path) -> None:
    project = _open(root)
    saved = project.map_path(project.add_room("Attic"))
    project.save()
    unsaved = project.map_path(project.add_room("Cellar"))
    undone = project.map_path(project.add_room("Vault"))
    project.undo()
    project.discard_unsaved_files()
    assert (root / saved).is_file() and not (root / unsaved).exists() and not (root / undone).exists()
    _every_listed_room_loads(root)


# --- what Mesh never removes ------------------------------------------------------------------------------------------
def test_a_file_moved_in_while_the_map_is_removed_is_kept(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Between the check and the removal another tool replaces the file: it is moved aside, found not Mesh's, put back."""
    project = _open(root)
    map_rel = project.map_path(project.add_room("Cellar"))
    project.undo()
    real = os.rename

    def raced(src: Any, dst: Any) -> None:
        if str(dst).endswith(".mesh-release-" + str(dst).rsplit("-", 1)[-1]) and Path(src).name == "cellar.json":
            Path(src).write_bytes(THEIRS)  # (just before it is moved aside)
        real(src, dst)

    monkeypatch.setattr(studio_project.os, "rename", raced)
    project.add_room("Attic")
    assert (root / map_rel).read_bytes() == THEIRS
    assert project.kept_files == [{"path": map_rel, "reason": "it was changed after Mesh made it"}]
    assert [p.name for p in (root / MAPS).iterdir() if "mesh-release" in p.name] == []


def test_when_something_new_is_there_too_both_are_kept(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _open(root)
    map_rel = project.map_path(project.add_room("Cellar"))
    project.undo()
    real = os.rename

    def raced(src: Any, dst: Any) -> None:
        if Path(src).name == "cellar.json" and "mesh-release" in str(dst):
            Path(src).write_bytes(THEIRS)
            real(src, dst)
            Path(src).write_bytes(b"and another\n")  # (another file appears where it was)
            return
        real(src, dst)

    monkeypatch.setattr(studio_project.os, "rename", raced)
    project.add_room("Attic")
    assert (root / map_rel).read_bytes() == b"and another\n"
    aside = [p for p in (root / MAPS).iterdir() if "mesh-release" in p.name]
    assert [p.read_bytes() for p in aside] == [THEIRS]
    assert project.kept_files[0]["reason"].endswith(f"it is kept as {aside[0].name}")


def _symlink(target: Path, to: Path, *, folder: bool = False) -> None:
    try:
        os.symlink(to, target, target_is_directory=folder)
    except (OSError, NotImplementedError) as exc:  # (Windows without the privilege)
        pytest.skip(f"symbolic links can't be made here: {exc}")


def test_a_map_file_made_a_link_is_never_removed(root: Path, tmp_path: Path) -> None:
    project = _open(root)
    map_rel = project.map_path(project.add_room("Cellar"))
    project.undo()
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_bytes((root / map_rel).read_bytes())
    (root / map_rel).unlink()
    _symlink(root / map_rel, elsewhere)
    project.add_room("Attic")
    assert (root / map_rel).is_symlink() and elsewhere.is_file()
    assert project.kept_files[0]["path"] == map_rel


def test_a_map_folder_reached_through_a_link_is_never_touched(root: Path, tmp_path: Path) -> None:
    project = _open(root)
    map_rel = project.map_path(project.add_room("Cellar"))
    project.undo()
    outside = tmp_path / "outside_maps"
    shutil.move(str(root / MAPS), outside)
    if os.name == "nt":  # (a junction: no privilege needed, and Path.resolve follows it like a link)
        import _winapi

        _winapi.CreateJunction(str(outside), str(root / MAPS))
    else:
        _symlink(root / MAPS, outside, folder=True)
    project.add_room("Attic")
    assert (outside / "cellar.json").is_file()
    assert project.kept_files[0] == {"path": map_rel, "reason": "it is reached through a link, so Mesh leaves it alone"}


def test_add_map_never_takes_over_another_tools_file(root: Path) -> None:
    project = _bare_room(root)
    project.add_map("bare")
    map_rel = project.map_path("bare")
    project.undo()
    (root / map_rel).write_bytes(THEIRS)
    disk, revision = _tree(root), project.revision
    with pytest.raises(ops.OpError, match=r"There is already a file at packs/core_regions/maps/bare\.json, where this "
                                          r"room's map would go, and it isn't a map Mesh made for it"):
        project.add_map("bare")  # (was: used it, 99 x 99 on disk for a 24 x 16 room)
    assert _tree(root) == disk and project.revision == revision and "tilemap" not in project.scene("bare")


def test_add_map_uses_a_file_that_is_exactly_what_it_would_write_and_never_removes_it(root: Path) -> None:
    project = _bare_room(root)
    trial = project.clone()
    trial.add_map("bare")
    map_rel = trial.map_path("bare")
    width, height = ops.map_size_for(project.scene("bare"))
    skeleton = ops.map_skeleton(map_rel, width, height, tilesets=project.project_tilesets())
    from engine.json_io import json_bytes

    (root / map_rel).write_bytes(json_bytes(skeleton))  # (an earlier session's, say)
    project.add_map("bare")
    project.undo()
    project.add_room("Attic")
    project.discard_unsaved_files()
    assert (root / map_rel).read_bytes() == json_bytes(skeleton), "not Mesh's to remove"


# --- identity: a stale proposal never reaches the new room ----------------------------------------------------------
def test_a_stale_proposal_for_an_undone_room_never_changes_the_new_room_with_its_name(root: Path) -> None:
    project = _open(root)
    host = StudioAIHost(_FakeStudio(project))
    key = project.add_room("Cellar")
    player = _players(project, key)[0]
    proposal = host.stage_proposal_payload({"changes": [
        {"op": "move_entity", "room": key, "entity_id": player, "x": 300, "y": 40},
        {"op": "place_prefab", "room": key, "prefab": "person", "x": 64, "y": 64}], "source": "test"})
    project.undo()
    again = project.add_room("Cellar")
    room = project.scene(again)
    decided = host.accept(proposal)
    assert decided["ok"] is False and project.scene(again) == room, "was: moved the new room's player, added a person"
    assert again != key and _players(project, again) != [player]


def test_a_proposal_for_a_room_undone_and_redone_still_applies_to_it(root: Path) -> None:
    project = _open(root)
    host = StudioAIHost(_FakeStudio(project))
    key = project.add_room("Cellar")
    proposal = host.stage_proposal_payload({"changes": [{"op": "place_prefab", "room": key, "prefab": "person",
                                                         "x": 64, "y": 64}], "source": "test"})
    project.undo()
    project.redo()  # (the same room: S1-ID's contract, an undone thing coming back is the same thing)
    assert host.accept(proposal)["ok"] is True and len(project.scene(key)["entities"]) == 2


def test_an_ai_dry_run_after_undo_names_the_room_as_accepting_will(root: Path) -> None:
    project = _open(root)
    host = StudioAIHost(_FakeStudio(project))
    project.add_room("Cellar")
    project.undo()
    proposal = host.stage_proposal_payload({"changes": [{"op": "add_room", "label": "Cellar"}], "source": "test"})
    predicted = set(proposal.after["world"]["scenes"])
    assert "cellar_2" in predicted and "cellar" not in predicted
    assert host.accept(proposal)["ok"] is True
    assert set(project.world["scenes"]) == predicted
    assert (root / f"{MAPS}/cellar_2.json").is_file() and not (root / f"{MAPS}/cellar.json").exists()


# --- from review ------------------------------------------------------------------------------------------------------
def test_add_map_undo_add_map_keeps_the_file_the_room_uses_again(root: Path) -> None:
    project = _bare_room(root)
    project.add_map("bare")
    map_rel = project.map_path("bare")
    made = (root / map_rel).read_bytes()
    project.undo()
    project.add_map("bare")  # (the file only the redo step used: this room's again, so never released)
    assert project.map_path("bare") == map_rel and (root / map_rel).read_bytes() == made
    project.save()
    _every_listed_room_loads(root)
    assert _open(root).map_path("bare") == map_rel


def test_undo_history_trimming_keeps_a_map_still_used_and_reads_no_rooms(root: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    project = _bare_room(root)  # (a room never opened here: "bare")
    map_rel = project.map_path(project.add_room("Cellar"))
    reads: list[str] = []
    real = project._read_json
    monkeypatch.setattr(project, "_read_json", lambda rel: reads.append(rel) or real(rel))
    for n in range(studio_project.UNDO_LIMIT + 5):  # (the step from before Cellar is dropped, then later ones)
        project.edit_scene(lambda s, n=n: {**s, "name": f"Start {n}"}, "start")
    assert (root / map_rel).is_file() and len(project._undo) == studio_project.UNDO_LIMIT
    assert f"{SCENES}/bare.json" not in reads, "no room read from disk per edit"


def test_nested_transactions_remove_only_what_the_failed_one_made(root: Path) -> None:
    project = _open(root)
    with project.transaction():
        outer = project.map_path(project.add_room("Attic"))
        with pytest.raises(RuntimeError), project.transaction():
            inner = project.map_path(project.add_room("Vault"))
            raise RuntimeError("the inner batch fails")
    assert (root / outer).is_file() and not (root / inner).exists() and "attic" in project.world["scenes"]
    with pytest.raises(RuntimeError), project.transaction():
        both = [project.map_path(project.add_room(label)) for label in ("Cellar", "Loft")]
        raise RuntimeError("the outer batch fails")
    assert not any((root / rel).exists() for rel in both) and (root / outer).is_file()


def test_closing_after_a_save_that_needs_recovery_removes_nothing(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def half_done(root_: Path, documents: Any, *_args: Any) -> Any:
        err = refused("disk_full", "Half written.", [(rel, kind) for rel, kind, _doc in documents], root_)
        err.report["recovery_required"] = True
        raise err

    project = _open(root)
    map_rel = project.map_path(project.add_room("Vault"))
    monkeypatch.setattr(studio_project, "save_documents", half_done)
    with pytest.raises(ops.OpError):
        project.save()
    project.discard_unsaved_files()  # (Studio: Discard)
    assert (root / map_rel).is_file(), "the files on disk may use it now"
