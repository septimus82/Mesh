"""A-02b: a dict-form ``{"quests": {"<key>": {...}}}`` entry without its own "id" loads with its key as id.

Before: the loader ignored the key, ``normalize_quest`` returned None for an id-less value, and the quest was silently
dropped -- including every quest ``AIOps.add_quest_definition`` wrote into a dict-form file (it writes no "id").
Reached through the production loader: ``engine.quests.QuestManager(window)`` as ``GameWindow`` constructs it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest

from engine.ai_ops import AIOps
from engine.game_state_controller import GameStateController
from engine.paths import reset_path_caches, set_content_roots
from engine.project_scaffold import create_project
from engine.quests import QuestManager

pytestmark = pytest.mark.integration  # (F13-A: scaffolds a project)


class _Window:
    def __init__(self) -> None:
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = None

    def emit_signal(self, event_name: str, **payload: Any) -> None:
        pass


def _q(title: str) -> dict[str, Any]:
    return {"title": title, "stages": [{"id": "s1", "text": title}]}


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


def _write(path: Path, quests: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps({"quests": quests}).encode("utf-8"))


def _load(root: Path) -> dict[str, dict[str, Any]]:
    qm = QuestManager(_Window())
    return qm._definitions


def test_keyed_entries_without_id_load_with_key_as_id(root: Path) -> None:
    _write(root / "assets/data/quests.json", {"a": _q("A"), "b": _q("B")})
    defs = _load(root)
    assert sorted(defs) == ["a", "b"] and defs["a"]["title"] == "A"


def test_the_file_is_not_mutated(root: Path) -> None:
    path = root / "assets/data/quests.json"
    _write(path, {"a": _q("A")})
    before = path.read_bytes()
    _load(root)
    assert path.read_bytes() == before


def test_id_equal_to_key_is_unchanged(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(root / "assets/data/quests.json", {"a": {"id": "a", **_q("A")}})
    assert sorted(_load(root)) == ["a"]
    assert "differs" not in capsys.readouterr().out


def test_id_differing_from_key_keeps_inner_id_and_reports(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(root / "assets/data/quests.json", {"key1": {"id": "inner", **_q("X")}})
    assert sorted(_load(root)) == ["inner"]
    out = capsys.readouterr().out
    assert "key1" in out and "inner" in out and "differs" in out


def test_list_form_is_unchanged(root: Path) -> None:
    _write(root / "assets/data/quests.json", [{"id": "a", **_q("A")}, _q("no id: still skipped")])
    assert sorted(_load(root)) == ["a"]


def test_non_dict_values_are_still_skipped(root: Path) -> None:
    _write(root / "assets/data/quests.json", {"a": _q("A"), "bad": "text", "worse": 3, "none": None})
    assert sorted(_load(root)) == ["a"]


def test_pack_quests_load_by_key_and_pack_wins_a_collision(root: Path) -> None:
    _write(root / "assets/data/quests.json", {"core": _q("Core"), "shared": _q("core copy")})
    _write(root / "packs/p1/assets/data/quests.json", {"pk": _q("Pack"), "shared": _q("pack copy")})
    defs = _load(root)
    assert sorted(defs) == ["core", "pk", "shared"]
    assert defs["shared"]["title"] == "pack copy"  # existing precedence: packs load after core and overwrite


def test_ai_added_quest_in_dict_form_file_loads(root: Path) -> None:
    path = root / "assets/data/quests.json"
    _write(path, {"a": _q("A")})
    res = AIOps(root).apply_job(
        {"operations": [{"type": "add_quest_definition", "quest_id": "ai", "quest": _q("AI")}]}
    )
    assert res["ok"] is True
    assert "id" not in json.loads(path.read_text(encoding="utf-8"))["quests"]["ai"]  # on-disk form unchanged
    assert sorted(_load(root)) == ["a", "ai"]
