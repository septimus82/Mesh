"""H1-F2: an unreadable or malformed prefab catalogue is never replaced when the shared player is saved.

``assets/prefabs.json`` holds the shared player and every other prefab. Saving a changed player rewrites it: the
player's entry replaced, every other entry kept as it was. An unreadable, malformed or wrong-shaped file used to read
as an empty list, so a save replaced it with the player alone (other prefabs gone; no backup if it was already broken
when the project opened). A missing file still starts a new catalogue; anything else unreadable refuses the save
before a file is written, keeps the creator's changes, and saving works again once the file is fixed.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.fast

CATALOGUE = "assets/prefabs.json"
LANTERN = {"id": "lantern", "display_name": "Lantern", "entity": {"name": "Lantern", "sprite": "assets/sprites/lantern.png"}}


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One blank project (its catalogue: the player, Person, Sign, and a Lantern of the creator's), copied per test."""
    root = tmp_path_factory.mktemp("f2") / "game"
    create_project(root, "Game", template_id="blank")
    prefabs = json.loads((root / CATALOGUE).read_text(encoding="utf-8"))
    (root / CATALOGUE).write_text(json.dumps([*prefabs, LANTERN], indent=2) + "\n", encoding="utf-8")
    return root


@pytest.fixture()
def root(made: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(made, tmp_path / "game"))


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


HERO = "assets/sprites/hero.png"


def _change_player(project: Project) -> None:
    """The shared player given a new picture in a room (as Studio does): the catalogue is what saves it."""
    entity = next(e for e in ops.entities(project.scene()) if e.get("tag") == "player")
    project.edit_scene(lambda scene: ops.set_picture(scene, entity["id"], HERO))


def _ids(root: Path) -> list[str]:
    return [p.get("id") for p in json.loads((root / CATALOGUE).read_text(encoding="utf-8")) if isinstance(p, dict)]


def test_a_valid_catalogue_keeps_every_other_prefab(root: Path) -> None:
    project = _open(root)
    _change_player(project)
    assert CATALOGUE in project.save()
    saved = json.loads((root / CATALOGUE).read_text(encoding="utf-8"))
    assert [p["id"] for p in saved] == ["player", "person", "sign", "lantern"]
    assert saved[-1] == LANTERN and saved[0]["entity"]["sprite"] == HERO


def test_a_missing_catalogue_starts_a_new_one(root: Path) -> None:
    project = _open(root)
    (root / CATALOGUE).unlink()  # (an older project: no catalogue yet)
    _change_player(project)
    assert CATALOGUE in project.save()
    assert _ids(root) == ["player"]


@pytest.mark.parametrize("damaged", [
    b'[{"id": "player", "entity": {"name": "Player"}},\n  {"id": "lantern"',  # (a hand edit cut short)
    b'{"prefabs": []}\n',  # (an object, not a list)
    b'"player"\n', b"null\n",
], ids=["malformed", "object", "string", "null"])
def test_an_unreadable_catalogue_refuses_the_save_and_stays_byte_for_byte(root: Path, damaged: bytes) -> None:
    project = _open(root)
    _change_player(project)
    room = root / project.path(project.current)
    room_before = room.read_bytes()
    undo_steps = len(project._undo)
    (root / CATALOGUE).write_bytes(damaged)
    with pytest.raises(ops.OpError, match=r"assets/prefabs\.json isn't a prefab list Studio can read .* nothing was written"):
        project.save()
    assert (root / CATALOGUE).read_bytes() == damaged, "the damaged catalogue is kept exactly as it is"
    assert room.read_bytes() == room_before, "nothing else was written either"
    assert not list((root / "assets").glob("prefabs.json*.bak"))
    assert project.is_dirty and project.player_dirty and project.player["sprite"] == HERO, "the change is kept"
    assert len(project._undo) == undo_steps and project.undo(), "and so is its undo history"


def test_a_catalogue_that_cant_be_read_refuses_the_save(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.studio_project as studio_project

    project = _open(root)
    _change_player(project)
    before = (root / CATALOGUE).read_bytes()

    def denied(path: Path) -> object:
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(studio_project, "read_json", denied)
    with pytest.raises(ops.OpError, match="can't be read: .*Permission denied"):
        project.save()
    assert (root / CATALOGUE).read_bytes() == before and project.player_dirty


def test_after_the_file_is_fixed_saving_works_and_nothing_had_to_be_rebuilt(root: Path) -> None:
    good = (root / CATALOGUE).read_bytes()
    project = _open(root)
    _change_player(project)
    (root / CATALOGUE).write_bytes(good[:-60])  # (damaged outside Studio)
    with pytest.raises(ops.OpError):
        project.save()
    (root / CATALOGUE).write_bytes(good)  # (fixed: restored from a backup)
    written = project.save()
    assert CATALOGUE in written and not project.is_dirty
    assert _ids(root) == ["player", "person", "sign", "lantern"]
    assert json.loads((root / CATALOGUE).read_text(encoding="utf-8"))[0]["entity"]["sprite"] == HERO


def test_a_catalogue_changed_outside_studio_is_still_backed_up_and_its_new_prefabs_kept(root: Path) -> None:
    project = _open(root)
    _change_player(project)
    outside = [*json.loads((root / CATALOGUE).read_text(encoding="utf-8")), {"id": "well", "entity": {"name": "Well"}}]
    (root / CATALOGUE).write_text(json.dumps(outside, indent=2) + "\n", encoding="utf-8")
    later = (root / CATALOGUE).stat().st_mtime + 2  # (a later time than Studio read it, however coarse the clock)
    import os

    os.utime(root / CATALOGUE, (later, later))
    project.save()
    assert project.last_save_backups == ["assets/prefabs.json.outside-change.bak"]
    assert json.loads((root / "assets/prefabs.json.outside-change.bak").read_text(encoding="utf-8")) == outside
    assert _ids(root) == ["player", "person", "sign", "lantern", "well"]


def test_studio_says_why_it_didnt_save_and_keeps_the_work(root: Path) -> None:
    from engine.studio import Studio

    project = _open(root)
    _change_player(project)
    (root / CATALOGUE).write_bytes(b"{not json")
    said: list[tuple[str, bool]] = []
    studio = SimpleNamespace(project=project, _flush_fields=lambda: True, _rebuild=lambda: None,
                             message="", _say=lambda text, ok=True: said.append((text, ok)))
    assert Studio.save(studio) is False  # type: ignore[arg-type]
    text, ok = said[-1]
    assert not ok and text.startswith("Couldn't save: assets/prefabs.json isn't a prefab list Studio can read")
    assert "Fix or restore that file, then save again" in text and project.is_dirty
    assert (root / CATALOGUE).read_bytes() == b"{not json"
