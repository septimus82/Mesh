"""A-02: add_quest_definition (and edit/delete) keep the quests.json form the runtime loads; they never erase quests.

Before: a list-form ``{"quests": [...]}`` was replaced by ``{"quests": {new}}`` -- every existing quest lost.
Reached through ``AIOps.apply_job`` (console ``ai_job``) and ``tools.apply_ops`` (MCP).
"""

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from engine.ai_ops import AIOps
from engine.mcp_server import tools
from engine.project_scaffold import create_project

pytestmark = pytest.mark.integration  # (F13-A: scaffolds a project, takes the OS lock)
A = {"id": "a", "title": "A", "stages": [{"id": "s1"}]}
B = {"id": "b", "title": "B"}


def _job(root: Path, ops: list[dict[str, Any]]) -> dict[str, Any]:
    return AIOps(root).apply_job({"operations": ops})


def _mcp(root: Path, ops: list[dict[str, Any]]) -> dict[str, Any]:
    return tools.apply_ops(ops, root=str(root), validate=False)


PATHS = [pytest.param(_job, id="apply_job"), pytest.param(_mcp, id="mcp")]


@pytest.fixture
def quests(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    path = root / "assets/data/quests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _put(path: Path, text: str) -> bytes:
    path.write_bytes(text.encode("utf-8"))
    return path.read_bytes()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _add(quest_id: str, quest: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"type": "add_quest_definition", "quest_id": quest_id, "quest": quest}]


@pytest.mark.parametrize("run", PATHS)
def test_list_form_stays_a_list_and_keeps_every_quest(quests: Path, run: Callable[..., Any]) -> None:
    _put(quests, json.dumps({"quests": [A, B], "extra": 1}))
    assert run(quests.parents[2], _add("c", {"title": "C"}))["ok"] is True
    data = _read(quests)
    assert data["quests"] == [A, B, {"id": "c", "title": "C"}] and data["extra"] == 1


@pytest.mark.parametrize("run", PATHS)
def test_list_form_update_merges_the_matching_entry_in_place(quests: Path, run: Callable[..., Any]) -> None:
    _put(quests, json.dumps({"quests": [A, B]}))
    assert run(quests.parents[2], _add("a", {"title": "A2", "id": "ignored"}))["ok"] is True
    assert _read(quests)["quests"] == [{**A, "title": "A2"}, B]


@pytest.mark.parametrize("run", PATHS)
def test_dict_form_is_unchanged(quests: Path, run: Callable[..., Any]) -> None:
    _put(quests, json.dumps({"quests": {"a": A}}))
    assert run(quests.parents[2], _add("b", {"title": "B"}))["ok"] is True
    assert run(quests.parents[2], _add("a", {"title": "A2"}))["ok"] is True
    assert _read(quests)["quests"] == {"a": {**A, "title": "A2"}, "b": {"title": "B"}}


@pytest.mark.parametrize("run", PATHS)
def test_missing_quests_key_creates_the_object_form(quests: Path, run: Callable[..., Any]) -> None:
    _put(quests, "{}")
    assert run(quests.parents[2], _add("c", {"title": "C"}))["ok"] is True
    assert _read(quests) == {"quests": {"c": {"title": "C"}}}


MALFORMED = {
    "root_list": '[{"id": "a"}]',
    "root_string": '"quests"',
    "quests_string": '{"quests": "oops"}',
    "quests_number": '{"quests": 3}',
    "quests_null": '{"quests": null}',
    "entry_without_id": '{"quests": [{"id": "a"}, {"title": "no id"}]}',
    "entry_blank_id": '{"quests": [{"id": "  "}]}',
    "entry_not_object": '{"quests": [{"id": "a"}, 7]}',
    "duplicate_ids": '{"quests": [{"id": "a"}, {"id": "a", "title": "again"}]}',
}
OPS = {
    "add": _add("c", {"title": "C"}),
    "edit": [{"type": "edit_quest", "quest_id": "a", "patch": {"title": "X"}}],
    "delete": [{"type": "delete_quest_definition", "quest_id": "a"}],
}


@pytest.mark.parametrize("run", PATHS)
@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("shape", MALFORMED)
def test_malformed_files_are_refused_byte_identical(quests: Path, run: Callable[..., Any], op: str, shape: str) -> None:
    before = _put(quests, MALFORMED[shape])
    result = run(quests.parents[2], OPS[op])
    assert result["ok"] is False and result["results"][0]["ok"] is False and result["results"][0]["message"]
    assert quests.read_bytes() == before


@pytest.mark.parametrize("run", PATHS)
def test_edit_and_delete_work_on_a_list(quests: Path, run: Callable[..., Any]) -> None:
    _put(quests, json.dumps({"quests": [A, B]}))
    root = quests.parents[2]
    assert run(root, [{"type": "edit_quest", "quest_id": "b", "patch": {"title": "B2"}}])["ok"] is True
    assert _read(quests)["quests"] == [A, {**B, "title": "B2"}]
    assert run(root, [{"type": "delete_quest_definition", "quest_id": "b"}])["ok"] is True
    assert _read(quests)["quests"] == [A]
    before = quests.read_bytes()
    assert run(root, [{"type": "delete_quest_definition", "quest_id": "zzz"}])["ok"] is False
    assert quests.read_bytes() == before
