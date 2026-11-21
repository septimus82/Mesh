"""A stopped plan's own error is never masked by a failure to record it; a manifest's ``exists`` is checked strictly
(#462 reliability A-00 F1/F2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.project_scaffold import create_project
from engine.tooling.plan_executor import BackupManager, PlanExecutor
from engine.tooling.plan_types import Action, Plan

pytestmark = pytest.mark.integration  # (filesystem, cwd)

ROOM = "packs/core_regions/scenes/start.json"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    monkeypatch.chdir(path)
    return path


def _plan(*actions: Action) -> Plan:
    return Plan(wizard="a00", version=1, inputs={}, actions=list(actions))


def _npc(name: str) -> Action:
    return Action("add_npc", {"scene_path": ROOM, "role": "villager", "name": name}, f"adds {name}")


def _bytes(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_a_failing_plan_and_a_failing_manifest_write_raise_the_plans_error(
        root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def boom(self: Any, completed: bool = True) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(BackupManager, "finish_backup", boom)
    with pytest.raises(FileNotFoundError) as caught:  # (an action the plan can't do: a scene that isn't there)
        PlanExecutor().execute(_plan(_npc("Ferryman"), Action("add_npc", {"scene_path": "nope.json"}, "bad")))
    assert "nope.json" in str(caught.value) and "disk full" not in str(caught.value)
    assert "manifest couldn't be written (disk full)" in capsys.readouterr().out
    monkeypatch.undo()
    before = _bytes(root)
    assert PlanExecutor().undo_last() is False  # no manifest: refused
    assert _bytes(root) == before


@pytest.mark.parametrize("exists", [0, "", None])
def test_an_after_record_whose_exists_isnt_false_refuses_the_undo(root: Path, exists: Any) -> None:
    (root / "made.json").write_text("{}", encoding="utf-8")
    backup = root / ".mesh/plan_backups/2000_manual"
    (backup / "files").mkdir(parents=True)
    (root / "made.json").unlink()  # the plan's creation is gone, and the manifest says "absent" loosely
    (backup / "manifest.json").write_text(json.dumps({
        "version": 2, "completed": True, "created": ["made.json"], "modified": [],
        "after": {"made.json": {"exists": exists}}}), encoding="utf-8")
    before = _bytes(root)
    assert PlanExecutor().undo_last() is False
    assert _bytes(root) == before


def test_a_normal_plan_still_undoes(root: Path) -> None:
    original = (root / ROOM).read_bytes()
    PlanExecutor().execute(_plan(_npc("Ferryman")))
    assert (root / ROOM).read_bytes() != original
    assert PlanExecutor().undo_last() is True
    assert (root / ROOM).read_bytes() == original
