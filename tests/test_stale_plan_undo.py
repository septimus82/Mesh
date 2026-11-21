"""#462 P1: ``mesh undo-last-plan`` never erases work done after the plan.

The undo restored the newest backup wholesale: a room the plan changed was put back to before the plan, and anything
saved into it since (a person's NPC) went with it; the command said "Undo successful". Now a plan's manifest
(``version`` 2) records what the plan left at every file it created or modified (``after``: exists or not, and the
SHA-256 of its bytes), written by the plan itself while it holds the project. The undo first checks every file
against that record and refuses the whole undo, nothing changed, exit 1, if even one differs. A backup from before the
record (no ``version``) is never restored. Both run through the production CLI (``python -m mesh_cli``) in its own
process, in disposable scaffolded projects.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import authoring
from engine.editor import project_ownership
from engine.project_scaffold import create_project
from engine.studio_project import Project
from tests.test_studio_project_ownership import REPO, ROOM

pytestmark = pytest.mark.integration  # (F13-A: subprocesses)
WORLD = "packs/core_regions/worlds/main.json"
CELLAR = "packs/core_regions/scenes/cellar.json"
QUESTS = "assets/data/quests.json"
FERRYMAN = {"type": "add_npc", "description": "AI adds a Ferryman",
            "args": {"scene_path": ROOM, "role": "villager", "name": "Ferryman", "x": 96, "y": 96}}


def _npc(name: str, scene: str = ROOM) -> dict[str, Any]:
    return {"type": "add_npc", "description": f"AI adds {name}", "args": {"scene_path": scene, "role": "villager",
                                                                           "name": name}}


CELLAR_SCENE = {"type": "create_scene", "description": "AI makes a cellar", "args": {"path": CELLAR, "template": "empty"}}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _mesh(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "mesh_cli", *args], cwd=root, capture_output=True, text=True,
                          timeout=300, env={**os.environ, "PYTHONPATH": str(REPO)})


def _apply(root: Path, *actions: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    plan = root.parent / "plan.json"
    plan.write_text(json.dumps({"wizard": "p1", "version": 1, "inputs": {"pack": "core_regions"},
                                "actions": list(actions)}), encoding="utf-8")
    return _mesh(root, "apply-plan", "--no-lint", str(plan))


def _undo(root: Path) -> subprocess.CompletedProcess[str]:
    return _mesh(root, "undo-last-plan")


def _files(root: Path) -> dict[str, str]:
    """Every file of the project (its plan backups and history included) and its bytes' hash."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "owner.lock"}


def _names(root: Path, scene: str = ROOM) -> list[str]:
    return [str(e.get("name")) for e in json.loads((root / scene).read_text(encoding="utf-8"))["entities"]]


def _manifest_path(root: Path) -> Path:
    return sorted((root / ".mesh/plan_backups").glob("*/manifest.json"))[-1]


def _refused(root: Path, before: dict[str, str], *expected: str) -> str:
    ran = _undo(root)
    assert ran.returncode == 1, ran.stdout[-1500:]
    assert "Not restored: nothing was changed" in ran.stdout and "Undo successful" not in ran.stdout, ran.stdout[-1500:]
    for text in expected:
        assert text in ran.stdout, ran.stdout[-1500:]
    assert _files(root) == before  # every file byte-identical: nothing deleted, restored or replaced
    return ran.stdout


def _restored(root: Path) -> str:
    ran = _undo(root)
    assert ran.returncode == 0 and "Undo successful" in ran.stdout, ran.stdout[-1500:]
    return ran.stdout


# ------------------------------------------------------------------------------------------- the reproduction
def test_a_later_human_edit_refuses_the_undo_and_both_npcs_stay(root: Path) -> None:
    assert _apply(root, FERRYMAN).returncode == 0
    with project_ownership.acquire(root, project_ownership.STUDIO, wait=2.0) as held:  # (as Mesh Studio saves)
        project = Project(root, WORLD)
        authoring.apply(project, [{"op": "place_prefab", "prefab": "person", "x": 160, "y": 64},
                                  {"op": "rename_entity", "entity_id": "@0", "name": "Later human edit"}])
        assert project.save(owner=held) == [ROOM]
    assert project_ownership.owned(root) is None  # (nothing holds the project: the undo is the person's to run)
    out = _refused(root, _files(root), "files changed after the plan finished", "(its contents changed)")
    assert "start.json" in out
    assert _names(root) == ["None", "Ferryman", "Later human edit"]


# ------------------------------------------------------------------------------------------- successful undos
def test_an_undo_right_after_the_plan_restores_it(root: Path) -> None:
    room = (root / ROOM).read_bytes()
    assert _apply(root, FERRYMAN).returncode == 0
    manifest = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    key = manifest["modified"][0]
    assert manifest["version"] == 2 and manifest["completed"] is True and manifest["created"] == []
    assert manifest["after"] == {key: {"exists": True, "sha256": hashlib.sha256((root / ROOM).read_bytes()).hexdigest()}}
    _restored(root)
    assert (root / ROOM).read_bytes() == room


def test_an_unchanged_multi_file_plan_restores_every_file(root: Path) -> None:
    room = (root / ROOM).read_bytes()
    assert _apply(root, CELLAR_SCENE, _npc("Ferryman"), _npc("Keeper", CELLAR), _npc("Second", CELLAR)).returncode == 0
    assert _names(root, CELLAR) == ["Keeper", "Second"]
    manifest = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    assert len(manifest["created"]) == 1 and len(manifest["modified"]) == 1  # (the cellar created once, never "modified")
    _restored(root)
    assert (root / ROOM).read_bytes() == room and not (root / CELLAR).exists()  # the plan's own cellar gone with it


def test_two_actions_changing_one_file_restore_it_to_before_the_plan(root: Path) -> None:
    room = (root / ROOM).read_bytes()
    assert _apply(root, FERRYMAN, _npc("Boatman")).returncode == 0
    assert _names(root) == ["None", "Ferryman", "Boatman"]
    manifest = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    assert len(manifest["modified"]) == 1 and list(manifest["after"]) == manifest["modified"]  # its final state, once
    _restored(root)
    assert (root / ROOM).read_bytes() == room


# ------------------------------------------------------------------------------------------- conflicts
@pytest.mark.parametrize("since", ["edited", "deleted", "replaced"])
def test_a_created_file_changed_since_refuses_the_undo(root: Path, since: str) -> None:
    assert _apply(root, CELLAR_SCENE, _npc("Keeper", CELLAR)).returncode == 0
    cellar = root / CELLAR
    if since == "edited":
        cellar.write_text(cellar.read_text(encoding="utf-8").replace("Keeper", "Keeper (renamed by hand)"), encoding="utf-8")
        how = "(its contents changed)"
    elif since == "deleted":
        cellar.unlink()
        how = "(it is gone)"
    else:
        cellar.unlink()
        cellar.write_text('{"name": "A cellar someone made by hand"}', encoding="utf-8")
        how = "(its contents changed)"
    _refused(root, _files(root), "cellar.json " + how)


def test_a_modified_file_edited_by_hand_refuses_the_undo(root: Path) -> None:
    assert _apply(root, FERRYMAN).returncode == 0
    (root / ROOM).write_text((root / ROOM).read_text(encoding="utf-8").replace("Ferryman", "Old Ferryman"), encoding="utf-8")
    _refused(root, _files(root), "start.json (its contents changed)")


def test_a_file_the_plan_left_absent_that_exists_now_refuses_the_undo(root: Path) -> None:
    assert _apply(root, CELLAR_SCENE, _npc("Keeper", CELLAR)).returncode == 0
    manifest_path = _manifest_path(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    (root / CELLAR).unlink()  # (a plan that deleted what it made: recorded absent)
    manifest["after"][manifest["created"][0]] = {"exists": False}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (root / CELLAR).write_text('{"name": "made by hand since"}', encoding="utf-8")
    _refused(root, _files(root), "something is there now; the plan left nothing")


def test_one_changed_file_in_a_multi_file_plan_refuses_every_file(root: Path) -> None:
    assert _apply(root, CELLAR_SCENE, _npc("Ferryman"), _npc("Keeper", CELLAR)).returncode == 0
    (root / CELLAR).write_text((root / CELLAR).read_text(encoding="utf-8").replace("Keeper", "Hand-edited"), encoding="utf-8")
    _refused(root, _files(root), "cellar.json (its contents changed)")
    assert "Ferryman" in _names(root) and _names(root, CELLAR) == ["Hand-edited"]  # the untouched room not restored either


def test_an_undo_already_done_or_followed_by_an_edit_never_runs_again(root: Path) -> None:
    room = (root / ROOM).read_bytes()
    assert _apply(root, CELLAR_SCENE, _npc("Ferryman")).returncode == 0
    _restored(root)
    assert (root / ROOM).read_bytes() == room and not (root / CELLAR).exists()
    _refused(root, _files(root), "this plan was undone already")  # the same backup again: everything differs now
    (root / ROOM).write_text((root / ROOM).read_text(encoding="utf-8").replace("{", '{"edited_after_undo": 1, ', 1),
                             encoding="utf-8")
    _refused(root, _files(root))
    assert "edited_after_undo" in (root / ROOM).read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------- a plan that stopped
def test_a_plan_that_stopped_is_undone_only_while_what_it_left_is_unchanged(root: Path) -> None:
    room = (root / ROOM).read_bytes()
    failed = _apply(root, FERRYMAN, _npc("Nobody", "packs/core_regions/scenes/missing.json"))
    assert failed.returncode != 0 and _names(root) == ["None", "Ferryman"], failed.stdout[-1500:]
    manifest = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    assert manifest["completed"] is False and set(manifest["after"]) == {*manifest["created"], *manifest["modified"]}
    assert manifest["after"][manifest["created"][0]] == {"exists": False}  # (the scene it never made)

    left = (root / ROOM).read_bytes()
    (root / ROOM).write_bytes(left.replace(b"Ferryman", b"Kept"))
    _refused(root, _files(root), "start.json (its contents changed)")  # changed since it stopped: refused
    (root / ROOM).write_bytes(left)  # (back to exactly what it left)
    out = _restored(root)  # as it stopped: what it changed before it stopped is undone
    assert "That plan stopped with an error" in out and (root / ROOM).read_bytes() == room


# ------------------------------------------------------------------------------------------- unverifiable backups
def test_a_backup_from_before_the_record_is_never_restored(root: Path) -> None:
    assert _apply(root, FERRYMAN).returncode == 0
    manifest_path = _manifest_path(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    legacy = {"modified": manifest["modified"], "created": manifest["created"]}  # (the manifest as it was before #462 P1)
    manifest_path.write_text(json.dumps(legacy), encoding="utf-8")
    out = _refused(root, _files(root), "this backup was made before Mesh recorded what a plan leaves behind",
                   "To undo it by hand, the files as they were before the plan are in")
    assert "start.json" in out and _names(root) == ["None", "Ferryman"]  # even unchanged since: never restored


@pytest.mark.parametrize("damage", [
    "no_after", "after_not_an_object", "an_entry_missing", "bad_sha256", "exists_not_a_bool", "extra_key",
    "unknown_version", "no_completed", "not_json", "a_list"])
def test_missing_malformed_or_incomplete_records_refuse_the_undo(root: Path, damage: str) -> None:
    assert _apply(root, CELLAR_SCENE, _npc("Ferryman")).returncode == 0
    manifest_path = _manifest_path(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    room_key, cellar_key = manifest["modified"][0], manifest["created"][0]
    text: str | None = None
    if damage == "no_after":
        del manifest["after"]
    elif damage == "after_not_an_object":
        manifest["after"] = [room_key]
    elif damage == "an_entry_missing":
        del manifest["after"][cellar_key]
    elif damage == "bad_sha256":
        manifest["after"][room_key]["sha256"] = "not-a-hash"
    elif damage == "exists_not_a_bool":
        manifest["after"][room_key]["exists"] = "yes"
    elif damage == "extra_key":
        manifest["after"][room_key]["trust_me"] = True
    elif damage == "unknown_version":
        manifest["version"] = 3
    elif damage == "no_completed":
        del manifest["completed"]
    elif damage == "not_json":
        text = "{not json"
    else:
        text = json.dumps([manifest])
    manifest_path.write_text(text if text is not None else json.dumps(manifest), encoding="utf-8")
    _refused(root, _files(root))
    assert "Ferryman" in _names(root) and (root / CELLAR).exists()
