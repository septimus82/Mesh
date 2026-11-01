"""F15 + F14 (#422): a new room never takes over a file it didn't make; an AI is told when a scene wasn't created.

F15: a new room's file name came from the world's room keys alone, so ``add_room("Cellar")`` picked
``scenes/cellar.json`` even when such a file was on disk unlisted (made by hand, or by ``create_scene``), and Save
overwrote it with no backup. Now a room's scene and map paths must be free when it is made (no file, folder or link
there, no other room's), refused before anything changes; and Save refuses to write a room file the project never read
or wrote over anything that appeared there since (``path_taken``, through F3's transactional save).

F14: ``AIOps.create_scene`` said "Created" whatever happened. It now returns ``ok: false`` naming the path and why.

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

from engine import authoring_session
from engine import project_ops as ops
from engine.ai_ops import AIOps
from engine.project_save import SaveError
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.integration

SCENES = "packs/core_regions/scenes"
CELLAR = f"{SCENES}/cellar.json"
MINE = b'{"name": "My hand-made cellar", "entities": []}\n'


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("f15") / "game"
    create_project(root, "Game", template_id="blank")
    return root


@pytest.fixture()
def root(made: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(made, tmp_path / "game", copy_function=shutil.copy2))


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _tree(root: Path) -> dict[str, Any]:
    """Every file and folder in the project, files with their bytes and modification time."""
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() and not p.is_symlink()
            else "link" if p.is_symlink() else "folder" for p in sorted(root.rglob("*"))}


def _memory(project: Project) -> tuple[Any, ...]:
    return (json.dumps(project.world, sort_keys=True), json.dumps(project.scenes, sort_keys=True, default=str),
            sorted(project.dirty), project.world_dirty, project.player_dirty, project.revision, len(project._undo),
            len(project._redo))


def _new_room_map(project: Project, label: str, *, hd2d: bool = False) -> str:
    """Where a new room's map file would go (worked out on a copy that writes nothing)."""
    trial = project.clone()
    key = trial.add_hd2d_room(label, 32, 24)[0] if hd2d else trial.add_room(label)
    map_rel = trial.map_path(key)
    assert map_rel is not None
    return map_rel


def _symlink(target: Path, to: Path, *, folder: bool = False) -> None:
    try:
        os.symlink(to, target, target_is_directory=folder)
    except (OSError, NotImplementedError) as exc:  # (Windows without the privilege)
        pytest.skip(f"symbolic links can't be made here: {exc}")


OCCUPANTS = {
    "a_creators_scene": ("a file", lambda p: p.write_bytes(MINE)),
    "malformed_json": ("a file", lambda p: p.write_bytes(b'{"name": "half a scene", "entities": [')),
    "a_folder": ("a folder", lambda p: p.mkdir()),
    "a_link": ("a link", lambda p: _symlink(p, p.with_name("elsewhere.json"))),
}


# --- refused when the room is made ------------------------------------------------------------------------------------
def test_the_destructive_case_now_keeps_the_creators_file(root: Path) -> None:
    """The checkpoint's reproduction: an unlisted scenes/cellar.json, Add room "Cellar", Save. It was overwritten."""
    (root / CELLAR).write_bytes(MINE)
    project = _open(root)
    disk, memory = _tree(root), _memory(project)
    with pytest.raises(ops.OpError, match=r"There is already a file at packs/core_regions/scenes/cellar\.json that "
                                          r"isn't one of this project's rooms, so the room 'Cellar' wasn't added"):
        project.add_room("Cellar")
    project.save()
    assert (root / CELLAR).read_bytes() == MINE
    assert _tree(root) == disk and _memory(project) == memory


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
@pytest.mark.parametrize("occupant", list(OCCUPANTS))
def test_any_occupant_of_the_scene_path_refuses_the_room_and_changes_nothing(root: Path, occupant: str,
                                                                            kind: str) -> None:
    what, put = OCCUPANTS[occupant]
    put(root / CELLAR)
    project = _open(root)
    disk, memory = _tree(root), _memory(project)
    with pytest.raises(ops.OpError, match=rf"There is already {what} at packs/core_regions/scenes/cellar\.json"):
        project.add_hd2d_room("Cellar", 32, 24) if kind == "hd2d" else project.add_room("Cellar")
    assert _tree(root) == disk, "the occupant as it was; no map file, no HD-2D kit, nothing else written"
    assert _memory(project) == memory, "no room registered, nothing dirty, undo and revision as they were"
    assert "cellar" not in project.world["scenes"] and not project.can_undo()


@pytest.mark.parametrize("kind", ["2d", "hd2d"])
def test_an_occupied_map_path_refuses_the_room_too(root: Path, kind: str) -> None:
    project = _open(root)
    map_rel = _new_room_map(project, "Cellar", hd2d=kind == "hd2d")
    (root / map_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / map_rel).write_bytes(b'{"a creator\'s": "map"}\n')
    disk, memory = _tree(root), _memory(project)
    with pytest.raises(ops.OpError, match=rf"There is already a file at {map_rel}"):
        project.add_hd2d_room("Cellar", 32, 24) if kind == "hd2d" else project.add_room("Cellar")
    assert _tree(root) == disk and _memory(project) == memory


def test_another_rooms_file_is_never_shared(root: Path) -> None:
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    world = json.loads((root / world_file).read_text(encoding="utf-8"))
    world["scenes"]["basement"] = {"label": "Basement", "path": CELLAR, "tags": []}  # (listed; its file not made yet)
    (root / world_file).write_text(json.dumps(world, indent=2), encoding="utf-8")
    project = _open(root)
    with pytest.raises(ops.OpError, match=r"cellar\.json is already the file of the room 'Basement'"):
        project.add_room("Cellar")


# --- refused when it is saved: something appeared after the room was made -------------------------------------------
@pytest.mark.parametrize("occupant", ["a_creators_scene", "a_folder"])
def test_a_file_that_appears_before_save_is_never_overwritten(root: Path, occupant: str) -> None:
    project = _open(root)
    key = project.add_room("Cellar")  # (free now)
    project.edit_scene(lambda s: {**s, "name": "Start (edited)"}, "start")
    OCCUPANTS[occupant][1](root / CELLAR)  # (another tool makes it meanwhile)
    disk, memory = _tree(root), _memory(project)
    with pytest.raises(SaveError) as caught:
        project.save()
    report = caught.value.report
    assert (report["stage"], report["reason"]) == ("stage", "path_taken")
    assert f"{CELLAR} is on disk now, but this project never read or wrote it" in report["message"]
    assert not report["committed"] and not report["recovery_required"]
    assert {d["path"]: d["result"] for d in report["documents"]}[CELLAR] == "not_written"
    assert _tree(root) == disk, "the newcomer as it was, and the edited room not written either (all or nothing)"
    assert _memory(project) == memory and key in project.dirty, "the work kept, unsaved"
    if occupant == "a_folder":
        (root / CELLAR).rmdir()
    else:
        (root / CELLAR).rename(root / f"{SCENES}/moved_away.json")
    assert CELLAR in project.save(), "moved out of the way: it saves"
    assert not project.is_dirty


# --- what was always allowed still is -------------------------------------------------------------------------------
def test_a_normal_new_room_saves_and_reopens(root: Path) -> None:
    project = _open(root)
    key = project.add_room("Cellar")
    written = project.save()
    assert CELLAR in written and project.last_save_report["ok"]
    reopened = _open(root)
    assert reopened.label(key) == "Cellar" and reopened.scene(key)["name"] == "Cellar"
    project.edit_scene(lambda s: {**s, "name": "Cellar (edited)"}, key)  # (its own room now: edits save as ever)
    assert CELLAR in project.save()


def test_a_normal_new_hd2d_room_saves(root: Path) -> None:
    project = _open(root)
    key, installed = project.add_hd2d_room("Meadow", 32, 24)
    assert installed and project.path(key) in project.save()
    assert (root / project.path(key)).is_file()


def test_a_listed_room_whose_file_is_missing_is_still_written(root: Path) -> None:
    project = _open(root)
    key = project.add_room("Cellar")
    project.save()
    (root / CELLAR).unlink()  # (deleted outside Studio after it was saved once: the project wrote it before)
    reopened = _open(root)
    reopened.edit_scene(lambda s: {**s, "name": "Cellar again"}, key)  # (read as missing: never seen on disk)
    assert CELLAR in reopened.save()
    assert json.loads((root / CELLAR).read_text(encoding="utf-8"))["name"] == "Cellar again"


# --- the AI paths: direct authoring, dry run, Studio proposals ------------------------------------------------------
def test_direct_ai_authoring_is_refused_with_the_path_and_writes_nothing(root: Path, tmp_path: Path, capsys) -> None:
    from engine.mcp_server import tools
    from mesh_cli import author

    (root / CELLAR).write_bytes(MINE)
    disk = _tree(root)
    change = [{"op": "add_room", "label": "Cellar"}]
    for result in (authoring_session.apply(root, change, dry_run=True), authoring_session.apply(root, change),
                   tools.apply_changes(change, root=str(root))):
        assert (result["ok"], result["reason"], result["op"], result["index"]) == (False, "invalid_change", "add_room", 0)
        assert "There is already a file at packs/core_regions/scenes/cellar.json" in result["message"]
    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps(change), encoding="utf-8")
    assert author.handle(SimpleNamespace(author_command="apply", project=str(root), changes=str(changes),
                                         dry_run=False)) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "invalid_change"
    assert _tree(root) == disk


class _FakeStudio:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=f"{SCENES}/start.json"))

    def on_ai_proposal(self, _proposal: Any) -> None:
        pass

    def on_ai_decided(self, _proposal: Any) -> None:
        pass


def test_a_studio_proposal_is_refused_when_staged_and_again_when_accepted(root: Path) -> None:
    from engine.studio_ai import StudioAIHost

    project = _open(root)
    host = StudioAIHost(_FakeStudio(project))
    (root / CELLAR).write_bytes(MINE)
    staged = host.stage_proposal_payload({"changes": [{"op": "add_room", "label": "Cellar"}], "source": "test"})
    assert isinstance(staged, dict) and staged["ok"] is False and "cellar.json" in staged["message"]
    assert host.proposals == []

    (root / CELLAR).unlink()  # (free when staged...)
    proposal = host.stage_proposal_payload({"changes": [{"op": "add_room", "label": "Cellar"}], "source": "test"})
    assert getattr(proposal, "status", None) == "pending"
    (root / CELLAR).write_bytes(MINE)  # (...taken before the person accepts)
    memory = _memory(project)
    decided = host.accept(proposal)
    assert decided["ok"] is False and "cellar.json" in json.dumps(decided)
    assert (root / CELLAR).read_bytes() == MINE and _memory(project) == memory


# --- F14: AIOps.create_scene says what happened ------------------------------------------------------------------------
def test_create_scene_creates_a_new_scene_as_before(root: Path) -> None:
    result = AIOps(base_dir=root).create_scene(f"{SCENES}/attic", template="empty")
    assert result.ok and result.message == f"Created scene '{SCENES}/attic.json'"
    assert json.loads((root / f"{SCENES}/attic.json").read_text(encoding="utf-8"))["description"] == "A minimal empty scene."


@pytest.mark.parametrize("occupant", ["a_creators_scene", "a_folder"])
def test_create_scene_never_reports_an_existing_target_as_created(root: Path, occupant: str) -> None:
    OCCUPANTS[occupant][1](root / CELLAR)
    disk = _tree(root)
    result = AIOps(base_dir=root).create_scene(f"{SCENES}/cellar")
    assert result.ok is False and result.data["reason"] == "already_exists" and "wasn't created" in result.message
    assert str(root / CELLAR) in result.message and _tree(root) == disk


def test_create_scene_reports_an_unknown_template_and_a_failed_write(root: Path, monkeypatch) -> None:
    from engine.mcp_server import tools
    from engine.tooling import scaffold

    unknown = AIOps(base_dir=root).create_scene(f"{SCENES}/attic", template="no_such_template")
    assert unknown.ok is False and unknown.data["reason"] == "unknown_template" and "empty" in unknown.message

    def disk_full(*_args: Any, **_kwargs: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(scaffold.json_io, "write_json_new", disk_full)  # (the write a new scene uses)
    failed = tools.create_scene(f"{SCENES}/attic", root=str(root))  # (the MCP tool: the same result)
    assert failed["ok"] is False and failed["data"]["reason"] == "write_failed"
    assert not (root / f"{SCENES}/attic.json").exists()


# --- publication itself never replaces: something put there at the very last moment survives ----------------------
ZOO = f"{SCENES}/zoo.json"  # (a new room saved after the start room: one file is already written when it fails)


def _competitor(kind: str, path: Path) -> Any:
    if kind == "a_file":
        path.write_bytes(MINE)
        return MINE
    if kind == "a_folder":
        path.mkdir()
        return "folder"
    _symlink(path, path.with_name("nowhere.json"))  # (a broken link, pointing inside the project)
    return "link"


def _still(kind: str, path: Path, expected: Any) -> bool:
    if kind == "a_file":
        return path.read_bytes() == expected and not path.is_symlink()
    if kind == "a_folder":
        return path.is_dir() and not any(path.iterdir())
    return path.is_symlink() and not path.with_name("nowhere.json").exists()


@pytest.mark.parametrize("kind", ["a_file", "a_folder", "a_broken_link"])
def test_something_put_there_at_the_moment_of_publication_survives(root: Path, monkeypatch, kind: str) -> None:
    from engine import project_save

    project = _open(root)
    key = project.add_room("Zoo")
    project.edit_scene(lambda s: {**s, "name": "Start (edited)"}, "start")
    disk, memory = _tree(root), _memory(project)
    real, put = project_save._publish_new, {}

    def raced(src: Path, dst: Path) -> None:
        put["it"] = _competitor(kind, Path(dst))  # (after every check: right before the publication itself)
        real(src, dst)

    monkeypatch.setattr(project_save, "_publish_new", raced)
    with pytest.raises(SaveError) as caught:
        project.save()
    report = caught.value.report
    assert (report["stage"], report["reason"]) == ("commit", "path_taken")
    assert "something was put at packs/core_regions/scenes/zoo.json just as it was saved" in report["message"]
    assert report["restored"] == [f"{SCENES}/start.json"] and not report["committed"] and not report["recovery_required"]
    assert _still(kind, root / ZOO, put["it"]), "the newcomer exactly as it was put there"
    after = {k: v for k, v in _tree(root).items() if not k.startswith(ZOO)}
    assert after == disk, "the start room put back to the byte and the time; nothing else written or left"
    assert _memory(project) == memory and key in project.dirty
    monkeypatch.undo()
    if kind == "a_folder":
        (root / ZOO).rmdir()
    else:
        (root / ZOO).unlink()
    assert ZOO in project.save() and not project.is_dirty


def test_a_file_system_that_cant_publish_without_replacing_fails_closed(root: Path, monkeypatch) -> None:
    import errno

    from engine import project_save

    project = _open(root)
    project.add_room("Zoo")
    project.edit_scene(lambda s: {**s, "name": "Start (edited)"}, "start")
    disk = _tree(root)

    def unsupported(_src: Path, dst: Path) -> None:  # (no hard links here: publish_new refuses rather than replace)
        raise OSError(errno.EPERM, "Operation not permitted", str(dst))

    monkeypatch.setattr(project_save, "_publish_new", unsupported)
    with pytest.raises(SaveError) as caught:
        project.save()
    assert (caught.value.report["stage"], caught.value.report["reason"]) == ("commit", "commit_failed")
    assert _tree(root) == disk and not (root / ZOO).exists() and project.is_dirty


@pytest.mark.parametrize("kind", ["a_file", "a_folder", "a_broken_link"])
def test_publish_new_never_replaces_anything(tmp_path: Path, kind: str) -> None:
    from engine.json_io import publish_new

    src, dst = tmp_path / "staged.json", tmp_path / "scene.json"
    src.write_bytes(b"new\n")
    it = _competitor(kind, dst)
    with pytest.raises(FileExistsError):
        publish_new(src, dst)
    assert _still(kind, dst, it) and src.read_bytes() == b"new\n"
    free = tmp_path / "free.json"
    publish_new(src, free)
    assert free.read_bytes() == b"new\n" and not src.exists()


# --- F14: scaffolding never replaces either -----------------------------------------------------------------------
def test_create_scene_over_a_broken_link_inside_the_project_is_refused(root: Path) -> None:
    from engine.tooling import scaffold

    link = root / CELLAR
    _competitor("a_broken_link", link)
    destination = link.with_name("nowhere.json")
    result = AIOps(base_dir=root).create_scene(f"{SCENES}/cellar")
    assert result.ok is False and result.data["reason"] == "already_exists" and "a link" in result.message
    assert scaffold.create_scene(str(link)) is False, "the scaffold itself refuses it too (no AIOps check needed)"
    assert link.is_symlink() and not destination.exists(), "the link untouched, nothing made where it points"


def test_a_scene_put_there_while_it_is_being_created_survives(root: Path, monkeypatch) -> None:
    from engine import json_io

    target = root / f"{SCENES}/attic.json"
    real = json_io.publish_new

    def raced(src: Any, dst: Any) -> None:
        Path(dst).write_bytes(MINE)  # (after AIOps' and the scaffold's checks: right before the publication)
        real(src, dst)

    monkeypatch.setattr(json_io, "publish_new", raced)
    result = AIOps(base_dir=root).create_scene(f"{SCENES}/attic")
    assert result.ok is False and result.data["reason"] == "already_exists" and "while it was being created" in result.message
    assert target.read_bytes() == MINE
    assert not [p for p in target.parent.iterdir() if p.name.startswith(".attic.json.")], "no temporary file left"


def test_scaffold_force_still_overwrites_for_the_callers_that_ask(root: Path) -> None:
    from engine.tooling import scaffold

    (root / CELLAR).write_bytes(MINE)
    assert scaffold.create_scene(str(root / CELLAR)) is False and (root / CELLAR).read_bytes() == MINE
    assert scaffold.create_scene(str(root / CELLAR), force=True) is True
    assert (root / CELLAR).read_bytes() != MINE
