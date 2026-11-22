"""R-1: replay digests cover each replay's relevant quests, not the whole catalogue.

ISOLATION: an unrelated, inactive, unreferenced catalogue quest must not move any digest.
DETECTION: relevant-quest behaviour, global state/gameplay and cross-scene carry-over still do.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

import mesh_cli
from engine.quest_runtime.runner import QuestRunner

REPO = Path(__file__).resolve().parents[1]
DIGESTS = ("expected_event_digest", "expected_world_digest", "expected_final_state_digest")
STUB = {
    "id": "zz_unrelated_stub",
    "title": "Unrelated",
    "description": "Inactive, referenced by no replay.",
    "stages": [{"id": "s1", "title": "s", "text": "t", "complete_on": {"type": "never_emitted_event"}}],
}


def _digests(tmp_path: Path, case: dict[str, Any], script: Path | None = None) -> dict[str, str]:
    case = dict(case, golden=str(tmp_path / "g.json"))
    if script is not None:
        case["script"] = str(script)
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps([case]), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    rc = mesh_cli.main(
        ["replays", "update-golden", "--suite", str(suite), "--out-dir", str(out), "--seed", "123",
         "--reason", "test", "--allow-no-reason", "--quiet"]
    )
    assert rc == 0
    golden = json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
    return {k: golden[k] for k in DIGESTS}


def _suite_case(case_id: str) -> dict[str, Any]:
    suite = json.loads((REPO / "replays" / "suite.json").read_text(encoding="utf-8"))
    case = next(c for c in suite if c["id"] == case_id)
    case = dict(case, script=str(REPO / case["script"]), scene=str(REPO / case["scene"]) if case.get("scene") else "")
    if not case["scene"]:
        del case["scene"]
    return case


def _mutated_script(tmp_path: Path, case: dict[str, Any], edit: Callable[[dict[str, Any]], None]) -> Path:
    payload = json.loads(Path(case["script"]).read_text(encoding="utf-8"))
    edit(payload)
    path = tmp_path / "script.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], dict[str, str]]:
    monkeypatch.chdir(REPO)

    def run(case_id: str) -> dict[str, str]:
        return _digests(tmp_path, _suite_case(case_id))

    return run


@pytest.mark.parametrize("case_id", ["campaign02", "ep01"])
def test_unrelated_inactive_quest_does_not_change_digests(
    case_id: str, base: Callable[[str], dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = base(case_id)
    original = QuestRunner.load_definitions

    def load(self: QuestRunner, source: Any, **kw: Any) -> Any:
        if isinstance(source, Path):
            source = json.loads(source.read_text(encoding="utf-8"))
            source["quests"] = [*source["quests"], STUB]
        return original(self, source, **kw)

    monkeypatch.setattr(QuestRunner, "load_definitions", load)
    assert base(case_id) == before


@pytest.mark.parametrize("case_id", ["campaign02", "ep01"])
def test_relevant_quest_not_advancing_changes_digests(
    case_id: str, base: Callable[[str], dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = base(case_id)
    monkeypatch.setattr(QuestRunner, "process_events", lambda self, events: [])
    after = base(case_id)
    assert after["expected_final_state_digest"] != before["expected_final_state_digest"]


def test_campaign_global_flag_changes_final_digest(tmp_path: Path, base: Callable[[str], dict[str, str]]) -> None:
    before = base("campaign02")
    case = _suite_case("campaign02")
    script = _mutated_script(tmp_path, case, lambda p: p.update(initial_flags=["extra.global_flag"]))
    after = _digests(tmp_path, case, script)
    assert after["expected_final_state_digest"] != before["expected_final_state_digest"]


def test_episode_gameplay_outcome_changes_digests(tmp_path: Path, base: Callable[[str], dict[str, str]]) -> None:
    before = base("ep01")
    case = _suite_case("ep01")
    drop = {"episode_01_exit_door", "ep01.complete"}
    script = _mutated_script(
        tmp_path, case, lambda p: p.update(actions=[a for a in p["actions"] if not drop & {a.get("entity"), a.get("flag")}])
    )
    after = _digests(tmp_path, case, script)
    assert after["expected_world_digest"] != before["expected_world_digest"]
    assert after["expected_final_state_digest"] != before["expected_final_state_digest"]


def test_campaign_cross_scene_carry_over_changes_final_digest(
    tmp_path: Path, base: Callable[[str], dict[str, str]]
) -> None:
    """Dropping the first scene's completion leaves later scenes with different carried quest/flag state."""
    before = base("campaign02")
    case = _suite_case("campaign02")

    def edit(p: dict[str, Any]) -> None:
        first = p["scenes"][0]
        first["steps"] = [s for s in first["steps"] if s.get("event_type") != "ep01_complete"]

    after = _digests(tmp_path, case, _mutated_script(tmp_path, case, edit))
    assert after["expected_final_state_digest"] != before["expected_final_state_digest"]
