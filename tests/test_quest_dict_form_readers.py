"""A-02c: every quests.json reader understands dict-form quests with the loader's identity rule.

Dict form is ``{"quests": {"<key>": {...}}}``: an entry without its own "id" has its key as id; an inner "id" wins.
Each reader is reached through its real entry point: the MCP tools, PlanTester.run_tests, QuestEditorModel (and
save_quests), the AI context exporter and the AI audit. The editor never converts a dict-form file to a list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

from engine.ai_audit import build_audit_report
from engine.editor.quest_editor_model import QuestEditorModel, save_quests
from engine.mcp_server.tools import inspect_quest, list_quests
from engine.paths import reset_path_caches, set_content_roots
from engine.project_scaffold import create_project
from engine.tooling.ai_context_exporter import _load_quest_definitions
from engine.tooling.plan_tester import PlanTester, TestSpec

pytestmark = pytest.mark.integration  # (F13-A: scaffolds a project)


def _q(title: str) -> dict[str, Any]:
    return {"title": title, "stages": [{"id": "s1", "title": title, "text": title}]}


# no id / id == key / id != key
DICT_FORM = {"plain": _q("Plain"), "same": {"id": "same", **_q("Same")}, "key1": {"id": "inner", **_q("Inner")}}
EXPECTED_IDS = ["inner", "plain", "same"]


@pytest.fixture
def root(tmp_path: Path) -> Iterator[Path]:
    game = tmp_path / "game"
    create_project(game, "Game", template_id="blank")
    (game / "assets/data").mkdir(parents=True, exist_ok=True)
    set_content_roots([game])
    try:
        yield game
    finally:
        reset_path_caches()


def _write(root: Path, quests: Any) -> Path:
    path = root / "assets/data/quests.json"
    path.write_bytes(json.dumps({"quests": quests}).encode("utf-8"))
    return path


def test_mcp_list_and_inspect_use_dict_keys_as_ids(root: Path) -> None:
    _write(root, DICT_FORM)
    result = list_quests(str(root))
    assert [q["id"] for q in result["quests"]] == EXPECTED_IDS
    assert inspect_quest("plain", str(root))["ok"] is True
    assert inspect_quest("inner", str(root))["title"] == "Inner"
    assert inspect_quest("key1", str(root))["ok"] is False  # inner id wins, as in the loader


def test_mcp_list_form_unchanged(root: Path) -> None:
    _write(root, [{"id": "a", **_q("A")}, _q("no id: still skipped")])
    assert [q["id"] for q in list_quests(str(root))["quests"]] == ["a"]


def test_plan_tester_sees_dict_form_quests(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(root, DICT_FORM)
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(PlanTester, "_run_quest_test", lambda self, test, data: seen.append(data))
    report = PlanTester(root).run_tests([TestSpec(name="t", type="quest")])
    assert report.passed
    assert sorted(seen[0]) == EXPECTED_IDS


def test_plan_tester_list_form_unchanged(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(root, [{"id": "a", **_q("A")}, _q("no id")])
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(PlanTester, "_run_quest_test", lambda self, test, data: seen.append(data))
    PlanTester(root).run_tests([TestSpec(name="t", type="quest")])
    assert sorted(seen[0]) == ["a"]


def test_editor_model_reads_dict_form(root: Path) -> None:
    path = _write(root, DICT_FORM)
    model = QuestEditorModel.load(path)
    assert sorted(q["id"] for q in model.quests()) == EXPECTED_IDS


def test_editor_model_list_form_unchanged(root: Path) -> None:
    path = _write(root, [{"id": "a", **_q("A")}])
    assert [q["id"] for q in QuestEditorModel.load(path).quests()] == ["a"]


def test_editor_never_converts_dict_form_to_list(root: Path) -> None:
    path = _write(root, DICT_FORM)
    before = path.read_bytes()
    entries = QuestEditorModel.load(path).quests()
    with pytest.raises(ValueError, match="dict form"):
        save_quests(entries, path)
    assert path.read_bytes() == before


def test_editor_still_saves_list_form(root: Path) -> None:
    path = _write(root, [{"id": "a", **_q("A")}])
    save_quests([{"id": "a", **_q("A2")}], path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(saved["quests"], list) and saved["quests"][0]["title"] == "A2"


def test_context_exporter_titles_dict_form_quests(root: Path) -> None:
    _write(root, DICT_FORM)
    assert _load_quest_definitions() == {"plain": "Plain", "same": "Same", "inner": "Inner"}


def test_ai_audit_lists_dict_form_quest_ids(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(root, DICT_FORM)
    monkeypatch.setattr("engine.ai_audit.find_repo_root", lambda: root)
    report = build_audit_report()
    ids = sorted(q.id for q in report.quests)
    assert ids == EXPECTED_IDS
    assert "quests" not in ids
